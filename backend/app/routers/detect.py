"""Research CADe endpoint — disease-CANDIDATE detection on CT (UNVALIDATED, opt-in).

POST /api/ct-detect        — CT only, header-guarded, default OFF (CT_DETECT_ENABLED)
GET  /api/ct-detect/{id}   — poll the async job

Surfaces disease-shaped CANDIDATE regions for a radiologist to confirm, with a hard
RESEARCH-ONLY disclaimer and an abstain gate. Reuses the segmentation ingest spine
(de-ID, quarantine, bounds, the async job store) verbatim. Scores are detector
confidence, never a validated probability of disease.
"""
import hashlib
import json
import logging
import re
import secrets

import numpy as np
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image

from .. import config
from ..models.detect import CandidateFinding, CandidateRegion, CandidateResponse
from ..security import client_ip
from ..services import audit, ct_cade, dicom_utils, mr_cade, seg_store, upload_guard
from .segment import _read_blobs
from .viewer import _looks_dicom  # noqa: F401  (ingest parity)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["detect"])

_JOB_RE = re.compile(r"^[0-9a-f]{32}$")


def _competence(volume: dict) -> tuple[str, list[str]]:
    """Light abstain gate: is this a plausible CT volume for the detectors? (The
    modality guard already ensured CT; this catches a degenerate/non-CT-like volume.)"""
    hu = np.asarray(volume["hu"])
    lo, hi = float(hu.min()), float(hu.max())
    if hi - lo < 200:
        return "abstain", ["intensity range too narrow to be a CT volume"]
    if lo > -300:
        return "down-weight", ["no air density present — unusual for a chest/body CT"]
    return "read", []


def _mr_competence(volume: dict) -> tuple[str, list[str]]:
    """#9 — conservative MR abstain gate, analogous to the CT one. MR intensity is
    arbitrary (a.u.), so we can only sanity-check STRUCTURE, not density: a real MR
    volume must be 3-D, have a non-degenerate dynamic range, and contain a plausible
    amount of imaged tissue against background. Anything clearly inappropriate ABSTAINS
    (emits no candidates) rather than manufacturing focal-signal candidates. Kept
    deliberately conservative — it never up-weights, only refuses/cautions."""
    vol = np.asarray(volume["hu"]).astype(np.float32)
    if vol.ndim != 3 or vol.size == 0:
        return "abstain", ["not a 3-D MR volume"]
    p1, p99 = (float(x) for x in np.percentile(vol, [1, 99]))
    span = p99 - p1
    if span < 1e-3:
        return "abstain", ["intensity range too narrow to be an MR volume"]
    # Foreground = above a robust low threshold. Too little imaged tissue, or no
    # background at all, is atypical for an anatomical MR series -> abstain.
    thr = p1 + 0.1 * span
    fg_frac = float((vol > thr).mean())
    if fg_frac < 0.02:
        return "abstain", ["almost no imaged tissue — not a usable MR volume"]
    if fg_frac > 0.98:
        return "abstain", ["no background present — atypical for an MR volume"]
    return "read", []


def _salience_band(s: float) -> str:
    """Bucket the non-probabilistic detector salience into a coarse band the UI can
    render WITHOUT a percentage (a bare % beside a disease name reads as a calibrated
    probability). Buckets are presentation-only; they are NOT calibrated cut-points."""
    if s >= 0.75:
        return "high"
    if s >= 0.5:
        return "medium"
    return "low"


def _render_review_slices(hu: np.ndarray, view_id: str, window=(-500.0, 1600.0)) -> list[str]:
    """Render each slice to an 8-bit windowed PNG for review context. CT: a fixed wide
    HU window (lung + soft tissue). MR (window=None): a robust percentile window over
    the arbitrary a.u. volume. Opaque filenames under /static/segments."""
    if window is None:
        step = max(1, hu.shape[0] // 8)
        sample = hu[::step].ravel().astype(np.float32)
        lo_p, hi_p = np.percentile(sample, [1, 99])
        c, w = (float(lo_p) + float(hi_p)) / 2.0, max(float(hi_p) - float(lo_p), 1.0)
    else:
        c, w = window
    lo, span = c - w / 2.0, max(w, 1.0)
    urls = []
    for i in range(hu.shape[0]):
        a = np.clip((hu[i].astype(np.float32) - lo) / span, 0.0, 1.0) * 255.0
        fn = f"det_{view_id}_{i:03d}.png"
        Image.fromarray(a.astype(np.uint8), mode="L").save(config.SEGMENTS_DIR / fn)
        urls.append(f"/static/segments/{fn}")
    return urls


def _make_work(blobs: list[bytes], series_id, modality: str):
    def work():
        volume = dicom_utils.build_seg_volume(blobs, series_id=series_id)
        if modality == "CT" and not volume["is_ct"]:
            raise ValueError("CT detector received a non-CT volume")
        if modality == "MR" and volume["is_ct"]:
            raise ValueError("MR detector received a non-MR volume")
        competence, reasons = _competence(volume) if modality == "CT" else _mr_competence(volume)
        if competence == "abstain":
            cands = []
        elif modality == "CT":
            cands = ct_cade.detect(volume)
        else:
            cands = mr_cade.detect(volume)
        view_id = secrets.token_hex(6)
        # CT: wide window so lung + soft tissue show. MR: percentile window (a.u.).
        window = (-500.0, 1600.0) if modality == "CT" else None
        urls = _render_review_slices(np.asarray(volume["hu"]), view_id, window=window)
        return {
            "candidates": cands, "competence": competence, "reasons": reasons,
            "n_slices": volume["n_slices"], "slice_urls": urls,
            "slice_positions": volume["slice_positions"], "series_id": volume["series_id"],
            "identifiers_removed": volume["identifiers_removed"],
            "n_quarantined": volume["n_quarantined"], "burned_in": volume["burned_in"],
        }
    return work


def _to_candidate(c: dict, positions) -> CandidateFinding:
    r = c.get("region") or {}
    idx = int(r.get("slice_index", 0))
    pos = positions[idx] if (positions and 0 <= idx < len(positions)) else None
    region = CandidateRegion(slice_index=idx, slice_position=pos,
                             bbox=r.get("bbox"), centroid=r.get("centroid"))
    sal = float(c["score"])
    return CandidateFinding(
        label=c["label"], kind=c["kind"], salience=sal, salience_band=_salience_band(sal),
        detected=True, is_probability=False, validated=False,
        region=region, est_max_mm=c.get("est_max_mm"), mean_hu=c.get("mean_hu"),
        disposition=config.CT_DETECT_CANDIDATE_CAPTION, method="classical-cade-v1",
        model=c.get("model", ""), license=c.get("license", ct_cade.LICENSE))


def _response(job_id: str, modality: str, st: dict) -> CandidateResponse:
    disclaimer = config.CT_DETECT_DISCLAIMER if modality == "CT" else config.MR_DETECT_DISCLAIMER
    lic = ct_cade.LICENSE if modality == "CT" else mr_cade.LICENSE
    base = dict(job_id=job_id, modality=modality, disclaimer=disclaimer,
                status="queued", research_only=True, validated=False,
                not_a_normal_result=True,
                not_a_normal_result_message=config.DETECT_NOT_NORMAL_MESSAGE,
                model="classical-cade-v1", method="classical-cade-v1", license=lic)
    base["content_sha256"] = (st.get("meta") or {}).get("content_sha256")
    state, result = st.get("state"), st.get("result")
    if state == "done" and result:
        positions = result.get("slice_positions")
        cands = [_to_candidate(c, positions) for c in result["candidates"]]
        base.update(status="done", competence=result["competence"], reasons=result["reasons"],
                    candidates=cands, candidate_count=len(cands),
                    n_slices=result["n_slices"], slice_urls=result["slice_urls"],
                    slice_positions=positions, series_id=result.get("series_id"),
                    identifiers_removed=result["identifiers_removed"],
                    n_quarantined=result["n_quarantined"], burned_in=result["burned_in"])
    elif state == "error":
        base.update(status="error", detail=st.get("detail") or "detection failed")
    elif state in (None, "unknown"):
        base.update(status="unknown", detail="no such job")
    else:
        base.update(status=state)
    resp = CandidateResponse(**base)
    # #9 belt-and-suspenders: re-assert the honesty invariants at the response
    # boundary. These can never be flipped by a detector or a job result.
    assert resp.validated is False and resp.research_only is True
    assert resp.not_a_normal_result is True and resp.not_a_normal_result_message
    assert all((not c.validated) and (not c.is_probability) for c in resp.candidates)
    return resp


async def _launch(request, background_tasks, files, series_id, modality, enabled, allowed):
    upload_guard.reject_oversize_early(request, config.SEGMENT_MAX_TOTAL_BYTES)
    ip = client_ip(request)
    if not enabled:
        audit.log_event(None, "detect", request.url.path, ip, 503)
        raise HTTPException(503, "Research candidate detection is disabled on this deployment.")
    if series_id is not None and not re.fullmatch(r"[0-9a-f]{1,64}", series_id or ""):
        raise HTTPException(422, "Bad series id.")
    blobs = await _read_blobs(files)
    mod, mixed = await run_in_threadpool(dicom_utils.consensus_modality, blobs)
    if mixed or mod not in allowed:
        raise HTTPException(422, f"Candidate detection runs on {modality} only (uploaded: {mod or 'unknown'}).")
    params = {"series": series_id, "modality": modality, "min_score": config.DETECT_MIN_SCORE,
              "edge": config.SEGMENT_MAX_EDGE, "slices": config.SEGMENT_MAX_SLICES, "v": "cade-v1"}
    content_hash = hashlib.sha256(b"".join(blobs)).hexdigest()
    job_id = hashlib.sha256((content_hash + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:32]
    try:
        job_id, is_new = seg_store.submit(
            job_id, _make_work(blobs, series_id, modality),
            meta={"modality": modality, "kind": "detect", "content_sha256": content_hash})
    except seg_store.QueueFull:
        raise HTTPException(429, "Detection queue is busy — retry shortly.")
    if is_new:
        background_tasks.add_task(seg_store.run, job_id)
    audit.log_event(None, "detect", request.url.path, ip, 200)
    return _response(job_id, modality, seg_store.status(job_id))


def _poll(job_id: str, default_modality: str) -> CandidateResponse:
    if not _JOB_RE.match(job_id):
        raise HTTPException(400, "Bad job id.")
    st = seg_store.status(job_id)
    # Shared job store: never render a segment/anatomy job through the CADe builder.
    if (st.get("meta") or {}).get("kind") not in (None, "detect"):
        st = {"state": "unknown", "result": None, "detail": None, "meta": {}}
    modality = (st.get("meta") or {}).get("modality", default_modality)
    return _response(job_id, modality, st)


@router.post("/ct-detect", response_model=CandidateResponse)
async def ct_detect(request: Request, background_tasks: BackgroundTasks,
                    files: list[UploadFile] = File(...), series_id: str | None = Form(default=None)):
    return await _launch(request, background_tasks, files, series_id, "CT",
                         config.CT_DETECT_ENABLED, config.SEGMENT_MODALITIES)


@router.post("/mr-detect", response_model=CandidateResponse)
async def mr_detect(request: Request, background_tasks: BackgroundTasks,
                    files: list[UploadFile] = File(...), series_id: str | None = Form(default=None)):
    return await _launch(request, background_tasks, files, series_id, "MR",
                         config.MR_DETECT_ENABLED, config.MR_SEGMENT_MODALITIES)


@router.get("/ct-detect/{job_id}", response_model=CandidateResponse)
async def ct_detect_poll(job_id: str):
    return _poll(job_id, "CT")


@router.get("/mr-detect/{job_id}", response_model=CandidateResponse)
async def mr_detect_poll(job_id: str):
    return _poll(job_id, "MR")
