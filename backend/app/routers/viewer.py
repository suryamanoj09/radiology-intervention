"""CT / MRI DICOM viewer — an HONEST, model-free image viewer.

This path performs NO AI: no classifier, no Grad-CAM, no findings, no triage, no
abstain gate. It exists so a clinician can open a CT/MR series with correct
windowing and slice navigation — and is model-free BY CONSTRUCTION (it never calls
vision_xray), so a head CT can never be silently scored by the chest model.

The response deliberately contains NO field named or shaped like a diagnosis
(`finding`, `probability`, `impression`); only rendered slice URLs + technical
metadata + a persistent "not a medical device" disclaimer.
"""
import logging
import re
import secrets

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image

from .. import config
from ..services import decode_limit, dicom_utils, upload_guard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["viewer"])

VIEWER_DISCLAIMER = (
    "This image view is model-free — no AI is applied to the pixels shown. Windowing, "
    "slice navigation, and measurements are manual tools. Any AI on this modality (an "
    "anatomy overlay, a research candidate detector) is opt-in, off by default, shown "
    "separately, and never a diagnosis. Not a medical device; not for diagnostic use. "
    "Windowing presets are starting points; 8-bit rendering loses precision; burned-in "
    "pixel text (if any) is not removed."
)


def _looks_dicom(data: bytes, filename: str) -> bool:
    name = (filename or "").lower()
    return name.endswith((".dcm", ".dicom")) or (len(data) > 132 and data[128:132] == b"DICM")


@router.post("/dicom-view")
async def dicom_view(
    files: list[UploadFile] = File(...),
    window: str | None = Form(default=None),
):
    if not files:
        raise HTTPException(400, "No files uploaded.")
    if len(files) > config.VIEW_MAX_FILES:
        raise HTTPException(413, f"Too many files (max {config.VIEW_MAX_FILES} per series).")

    blobs: list[bytes] = []
    used = 0
    for f in files:
        data = await upload_guard.read_capped(f, config.VIEW_MAX_TOTAL_BYTES - used)
        if not data:
            continue
        used += len(data)
        if not _looks_dicom(data, f.filename or ""):
            raise HTTPException(422, "The CT/MRI viewer accepts DICOM (.dcm) files only.")
        blobs.append(data)

    if not blobs:
        raise HTTPException(400, "No readable DICOM files.")

    try:
        view = await decode_limit.heavy(dicom_utils.render_view, blobs, window)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        logger.exception("dicom-view: render failed")
        raise HTTPException(400, "Could not render this DICOM. Check it is a valid CT/MR series.")

    images = view.pop("images")  # already capped at VIEW_MAX_SLICES inside render_view

    view_id = secrets.token_hex(6)
    urls: list[str] = []
    for i, img8 in enumerate(images):
        fn = f"{view_id}_{i:03d}.png"
        Image.fromarray(img8).save(config.UPLOADS_DIR / fn)
        urls.append(f"/static/uploads/{fn}")

    return {
        "view_id": view_id,
        "modality": view["modality"],
        "is_ct": view["is_ct"],
        "is_mr": view["is_mr"],
        "slice_urls": urls,
        "n_slices_shown": len(urls),
        "n_slices_total": view["n_slices_total"],
        "truncated": view["truncated"],
        "slice_positions": view.get("slice_positions"),  # for anatomy-overlay alignment
        "spacing_mm": view["spacing_mm"],
        "spacing_col_mm": view["spacing_col_mm"],
        "slice_thickness_mm": view["slice_thickness_mm"],
        "spacing_between_mm": view["spacing_between_mm"],
        "identifiers_removed": view["identifiers_removed"],
        "burned_in": view["burned_in"],
        "window": view["window"],
        "presets": list(dicom_utils.CT_PRESETS.keys()) if view["is_ct"] else [],
        "sequence_label": view["sequence_label"],
        "body_part": view["body_part"],
        "disclaimer": VIEWER_DISCLAIMER,
    }


@router.post("/dicom-view-series")
async def dicom_view_series(
    files: list[UploadFile] = File(...),
    window: str | None = Form(default=None),
):
    """MRI/CT SERIES viewer: groups files into series (by pre-de-ID UID), classifies
    each by coded tags, detects plane, pairs DWI/ADC, and returns a series[] array
    for the series rail. Model-free; no diagnosis field. Same bounds as /dicom-view."""
    if not files:
        raise HTTPException(400, "No files uploaded.")
    if len(files) > config.VIEW_MAX_FILES:
        raise HTTPException(413, f"Too many files (max {config.VIEW_MAX_FILES}).")
    blobs, used = [], 0
    for f in files:
        data = await upload_guard.read_capped(f, config.VIEW_MAX_TOTAL_BYTES - used)
        if not data:
            continue
        used += len(data)
        if not _looks_dicom(data, f.filename or ""):
            raise HTTPException(422, "The viewer accepts DICOM (.dcm) files only.")
        blobs.append(data)
    if not blobs:
        raise HTTPException(400, "No readable DICOM files.")
    try:
        view = await decode_limit.heavy(dicom_utils.render_series_view, blobs, window)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        logger.exception("dicom-view-series render failed")
        raise HTTPException(400, "Could not render this DICOM series.")

    view_id = secrets.token_hex(6)
    for si, s in enumerate(view["series"]):
        imgs = s.pop("_images")
        urls = []
        for i, img8 in enumerate(imgs):
            fn = f"{view_id}_{si:02d}_{i:03d}.png"
            Image.fromarray(img8).save(config.UPLOADS_DIR / fn)
            urls.append(f"/static/uploads/{fn}")
        s["slice_urls"] = urls
    return {
        "view_id": view_id,
        "series": view["series"],
        "pairs": view["pairs"],
        "identifiers_removed": view["identifiers_removed"],
        "burned_in": view["burned_in"],
        "n_quarantined": view["n_quarantined"],
        "disclaimer": VIEWER_DISCLAIMER,
    }


@router.post("/dicom-raw")
async def dicom_raw(files: list[UploadFile] = File(...)):
    """VOLUME-PIVOT: return a series' middle slice as RAW int16 intensity + manifest,
    so the browser does true window/level on a canvas LUT (not a baked 8-bit PNG)."""
    if not files:
        raise HTTPException(400, "No files uploaded.")
    if len(files) > config.VIEW_MAX_FILES:
        raise HTTPException(413, "Too many files.")
    blobs, used = [], 0
    for f in files:
        data = await upload_guard.read_capped(f, config.VIEW_MAX_TOTAL_BYTES - used)
        if not data:
            continue
        used += len(data)
        if not _looks_dicom(data, f.filename or ""):
            raise HTTPException(422, "DICOM only.")
        blobs.append(data)
    if not blobs:
        raise HTTPException(400, "No readable DICOM files.")
    try:
        payload = await decode_limit.heavy(dicom_utils.raw_slice_payload, blobs)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        logger.exception("dicom-raw failed")
        raise HTTPException(400, "Could not extract raw intensity.")
    payload["disclaimer"] = VIEWER_DISCLAIMER
    return payload


@router.post("/dicom-roi")
async def dicom_roi(files: list[UploadFile] = File(...), shape: str = Form(...),
                    series_id: str | None = Form(default=None),
                    slice_position: str | None = Form(default=None)):
    """Region statistics (mean/SD/min/max/area) computed on the 16-bit intensity — HU
    for CT, a.u. for MR — never the window-clipped 8-bit display. `shape` is a JSON
    rect/ellipse in normalised [0,1] coords."""
    import json as _json
    if series_id is not None and not re.fullmatch(r"[0-9a-f]{1,64}", series_id or ""):
        raise HTTPException(422, "Bad series id.")
    if not files:
        raise HTTPException(400, "No files uploaded.")
    if len(files) > config.VIEW_MAX_FILES:
        raise HTTPException(413, "Too many files.")
    blobs, used = [], 0
    for f in files:
        data = await upload_guard.read_capped(f, config.VIEW_MAX_TOTAL_BYTES - used)
        if not data:
            continue
        used += len(data)
        if not _looks_dicom(data, f.filename or ""):
            raise HTTPException(422, "DICOM only.")
        blobs.append(data)
    if not blobs:
        raise HTTPException(400, "No readable DICOM files.")
    if not isinstance(shape, str) or len(shape) > 2048:
        raise HTTPException(422, "Bad ROI shape.")   # bound length before parsing
    try:
        shp = _json.loads(shape)
        sp = float(slice_position) if slice_position not in (None, "") else None
        if not isinstance(shp, dict):
            raise ValueError
    except (ValueError, TypeError, RecursionError):   # deeply-nested JSON -> RecursionError
        raise HTTPException(422, "Bad ROI shape.")
    try:
        payload = await decode_limit.heavy(dicom_utils.roi_stats, blobs, series_id, sp, shp)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        logger.exception("dicom-roi failed")
        raise HTTPException(400, "Could not compute the ROI.")
    payload["disclaimer"] = ("Region statistics measured on the 16-bit intensity (not the "
                             "8-bit display). Approximate; verify. Not a diagnosis.")
    return payload
