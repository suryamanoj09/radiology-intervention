import logging
import re

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from .. import config
from ..models.schemas import AnalyzeResponse
from ..services import dicom_utils, self_audit, upload_guard, vision_xray

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["analyze"])
_ID_RE = re.compile(r"^[0-9a-f]{12}$")


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: Request, background_tasks: BackgroundTasks,
                  file: UploadFile = File(...), window: str | None = Form(default=None)):
    upload_guard.reject_oversize_early(request)
    # Bounded read: a chunked-transfer body (no Content-Length) can't slip past the
    # early reject, so cap it here too.
    data = await upload_guard.read_capped(file, config.MAX_UPLOAD_BYTES)
    if not data:
        raise HTTPException(400, "Empty file.")
    import hashlib
    content_sha256 = hashlib.sha256(data).hexdigest()  # identifies a (public) source image

    try:
        img8, spacing, modality, source_format, _meta = dicom_utils.load_any(
            data, file.filename or "", window)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        logger.exception("Failed to read upload")
        raise HTTPException(400, "Could not read this file. Upload a PNG, JPG, or DICOM (.dcm).")

    # Modality routing: the chest model must not silently score CT/MR/other studies.
    if source_format == "dicom" and modality.upper() not in config.CXR_MODALITIES:
        raise HTTPException(
            422,
            f"This looks like a {modality} study. The chest X-ray analyzer only accepts "
            f"chest radiographs — please open this image in the CT/MRI Viewer tab instead "
            f"(windowing, measurements, and the opt-in anatomy/candidate tools live there).",
        )

    meta = _meta if isinstance(_meta, dict) else {}
    identifiers_removed = meta.get("identifiers_removed", 0)

    # Self-audit gate: decide BEFORE scoring. Refuse clearly-non-CXR input.
    try:
        audit = await run_in_threadpool(
            self_audit.assess, img8, meta.get("color_saturation", 0.0))
    except Exception:
        logger.exception("Self-audit failed; proceeding as READ")
        audit = {"competence": "read", "ood_score": 0.0, "reasons": []}

    # The chest model is trained on FRONTAL radiographs. A DICOM-declared lateral
    # view is out-of-distribution — down-weight and warn (never silently score it
    # as if frontal, which is what produced spurious flags on the lateral film).
    view = (meta.get("view_position") or "").upper()
    if view in ("LL", "RL", "LATERAL", "LAT") and audit.get("competence") == "read":
        audit["competence"] = "down-weight"
        audit.setdefault("reasons", []).append(
            "Lateral view — the model is trained on frontal chest radiographs, so "
            "findings on this projection are unreliable.")

    try:
        if audit.get("competence") == "abstain":
            return await run_in_threadpool(
                vision_xray.abstain_response, img8, modality, source_format,
                audit, identifiers_removed, meta.get("view_position"))
        resp = await run_in_threadpool(
            vision_xray.analyze_xray, img8, spacing, modality, source_format,
            identifiers_removed, audit, meta.get("spacing_col"),
            meta.get("view_position"))
    except Exception:
        logger.exception("Analysis failed")
        raise HTTPException(500, "Image analysis failed. Check server logs.")

    # Progressive enhancement (T7): ship the fast 224 result NOW; if the res512
    # localizer is enabled, compute the sharper 16x16 maps in the background and let
    # the frontend swap them in. No-op (dormant) when LOCALIZER_WEIGHTS is unset.
    resp.content_sha256 = content_sha256
    from ..services import localizer
    flagged_labels = [f.label for f in resp.findings if f.flagged][:config.LOCALIZER_MAX_FINDINGS]
    if localizer.available() and flagged_labels:
        resp.hires_pending = True
        background_tasks.add_task(localizer.compute_hires, resp.image_id, flagged_labels)
    return resp


@router.get("/localize-hires/{image_id}")
def localize_hires(image_id: str):
    """Poll target for the background res512 job: {status, findings:[{label, heatmap_url}]}."""
    from ..services import localizer
    if not _ID_RE.match(image_id or ""):
        raise HTTPException(422, "bad id")
    return localizer.hires_result(image_id)


@router.get("/analysis/{image_id}", response_model=AnalyzeResponse)
def get_analysis(image_id: str):
    saved = vision_xray.load_saved(image_id)
    if not saved:
        raise HTTPException(404, "No analysis found for this image id.")
    return saved
