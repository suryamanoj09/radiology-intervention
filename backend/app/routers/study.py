"""Real-time multi-image study endpoint.

Accepts MULTIPLE current chest radiographs at once (e.g. PA + lateral, or a small
serial burst), runs EACH through the same pipeline as /api/analyze — de-identify,
self-audit abstention gate, then the pretrained ensemble + per-finding Grad-CAM —
and returns a StudyResponse: the list of per-image AnalyzeResponse objects plus a
FUSED block (per-label max banded confidence across views, tagged with which view).

Per-image Grad-CAM is preserved: each image is scored and localized independently,
so every projection keeps its own attention overlays / contours / measurements.

Safety parity with /api/analyze is intentional and per-image:
  * size / rate caps are enforced per file AND on the image count (config.STUDY_MAX_IMAGES);
  * a non-chest DICOM (CT/MR/other) or an unreadable file degrades to a single
    ABSTAINED slot rather than failing the whole batch — one bad view never
    discards the good ones, and it is never silently scored by the chest model.
"""
import hashlib
import logging
import secrets

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from .. import config
from ..models.schemas import AnalyzeResponse
from ..services import dicom_utils, fusion, self_audit, upload_guard, vision_xray

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["study"])

# Canonical view tags. Client may send one per file (parallel to `files`); DICOM
# ViewPosition auto-fills when the client sends nothing / "auto".
_VIEW_CANON = {
    "pa": "PA", "ap": "AP", "lateral": "Lateral", "lat": "Lateral",
    "frontal": "Frontal", "other": "Other",
}


def _norm_view(v: str | None) -> str | None:
    if not v:
        return None
    key = v.strip().lower()
    if key in ("", "auto"):
        return None
    return _VIEW_CANON.get(key)


def _map_view_position(vp: str) -> str:
    """DICOM (0018,5101) ViewPosition -> canonical tag. Unknown non-empty => Other;
    empty => Frontal (a plain PNG/JPG chest film is assumed frontal)."""
    vp = (vp or "").strip().upper()
    if not vp:
        return "Frontal"
    if vp == "PA":
        return "PA"
    if vp.startswith("AP"):
        return "AP"
    if vp in ("LL", "RL", "LAT", "LATERAL", "LLD", "RLD") or "LAT" in vp:
        return "Lateral"
    return "Other"


def _resolve_view(override: str | None, meta: dict) -> str:
    v = _norm_view(override)
    if v:
        return v
    return _map_view_position((meta or {}).get("view_position", ""))


def _error_slot(reason: str, view: str, modality: str, source_format: str) -> AnalyzeResponse:
    """A file that could not be analyzed (unreadable, or a non-chest modality) is
    surfaced as an abstained slot so the rest of the study still returns."""
    return AnalyzeResponse(
        image_id=secrets.token_hex(6),
        image_url="",
        heatmap_url=None,
        top_finding=None,
        findings=[],
        competence="abstain",
        ood_score=1.0,
        audit_reasons=[reason],
        triage="routine",
        triage_reasons=[],
        modality=modality,
        source_format=source_format,
        view=view,
        disclaimer=config.DISCLAIMER,
    )


async def _analyze_one(data: bytes, filename: str, window: str | None,
                       view_override: str | None) -> AnalyzeResponse:
    """Mirror of /api/analyze for a single file, returning an AnalyzeResponse with
    its resolved `view` set. Never raises for per-image content problems — those
    become an abstained slot so one bad view cannot fail the whole study."""
    if not data:
        return _error_slot("Empty file — nothing to analyze.",
                           _norm_view(view_override) or "Other", "CR", "image")
    if len(data) > config.MAX_UPLOAD_BYTES:
        return _error_slot(
            f"File too large (max {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
            _norm_view(view_override) or "Other", "CR", "image")

    try:
        img8, spacing, modality, source_format, _meta = dicom_utils.load_any(
            data, filename or "", window)
    except Exception:
        logger.exception("Study: failed to read one upload")
        return _error_slot(
            "Could not read this file. Upload a PNG, JPG, or DICOM (.dcm).",
            _norm_view(view_override) or "Other", "CR", "image")

    meta = _meta if isinstance(_meta, dict) else {}
    view = _resolve_view(view_override, meta)
    identifiers_removed = meta.get("identifiers_removed", 0)

    # Modality routing: the chest model must not silently score CT/MR/other.
    if source_format == "dicom" and modality.upper() not in config.CXR_MODALITIES:
        return _error_slot(
            f"This is a {modality} study; only chest radiographs are analyzed here.",
            view, modality, source_format)

    try:
        audit = await run_in_threadpool(
            self_audit.assess, img8, meta.get("color_saturation", 0.0))
    except Exception:
        logger.exception("Study: self-audit failed; proceeding as READ")
        audit = {"competence": "read", "ood_score": 0.0, "reasons": []}

    try:
        if audit.get("competence") == "abstain":
            resp = await run_in_threadpool(
                vision_xray.abstain_response, img8, modality, source_format,
                audit, identifiers_removed, meta.get("view_position"))
        else:
            resp = await run_in_threadpool(
                vision_xray.analyze_xray, img8, spacing, modality, source_format,
                identifiers_removed, audit, meta.get("spacing_col"),
                meta.get("view_position"))
    except Exception:
        logger.exception("Study: analysis failed for one image")
        return _error_slot("Image analysis failed for this view.",
                           view, modality, source_format)

    resp.view = view
    # Re-persist so the stored JSON (used by /api/compare, /api/analysis/{id})
    # carries the resolved view too.
    try:
        (config.ANALYSIS_DIR / f"{resp.image_id}.json").write_text(
            resp.model_dump_json(), encoding="utf-8")
    except Exception:
        logger.exception("Study: could not persist view for %s", resp.image_id)
    return resp


@router.post("/analyze-study")
async def analyze_study(
    request: Request,
    files: list[UploadFile] = File(...),
    views: list[str] = Form(default=[]),
    window: str | None = Form(default=None),
):
    if not files:
        raise HTTPException(400, "No files uploaded.")
    if len(files) > config.STUDY_MAX_IMAGES:
        raise HTTPException(
            413, f"Too many images (max {config.STUDY_MAX_IMAGES} per study).")

    # Early reject + bounded reads with an AGGREGATE cap, so an oversized or
    # chunked (no Content-Length) body can't spool/materialize before the check.
    agg_cap = config.STUDY_MAX_IMAGES * config.MAX_UPLOAD_BYTES
    upload_guard.reject_oversize_early(request, limit=agg_cap)

    images: list[AnalyzeResponse] = []
    seen_hashes: set[str] = set()
    n_duplicates = 0
    used = 0
    for idx, f in enumerate(files):
        data = await upload_guard.read_capped(f, config.MAX_UPLOAD_BYTES)
        used += len(data)
        if used > agg_cap:
            raise HTTPException(413, "Study upload too large.")
        # De-duplicate BYTE-IDENTICAL uploads within one study: the same X-ray sent
        # twice must not be counted as two views (it would inflate the fused max /
        # per-view table). A distinct md5 is required to analyze; hashing is for
        # dedup only, not security.
        digest = hashlib.md5(data, usedforsecurity=False).hexdigest() if data else None
        if digest and digest in seen_hashes:
            n_duplicates += 1
            continue
        if digest:
            seen_hashes.add(digest)
        override = views[idx] if idx < len(views) else None
        images.append(await _analyze_one(data, f.filename or "", window, override))

    if n_duplicates:
        logger.info("Study: dropped %d duplicate (byte-identical) upload(s).", n_duplicates)
    if not images:
        raise HTTPException(400, "No analyzable images (all uploads were empty or duplicates).")

    study_id = secrets.token_hex(6)
    return fusion.build_study_response(images, study_id, config.DISCLAIMER)
