"""Anatomy-overlay segmentation endpoints (opt-in, NON-DIAGNOSTIC AI) — CT & MRI.

POST /api/segment       — CT only  (header-guarded)
POST /api/mr-segment    — MR only  (header-guarded)
GET  /api/segment/{id}  — poll an async job

The overlay LABELS/SEGMENTS anatomy and MEASURES regions ONLY; it never detects,
characterizes, or excludes disease. This router is separate from viewer.py so the
viewer stays model-free-by-construction (VIEWER_DISCLAIMER stays true). It reuses the
viewer's ingest spine verbatim (upload bounds, _looks_dicom, de-ID, quarantine) via
dicom_utils.build_seg_volume, enforces the license/anatomy whitelist BEFORE any model
runs, and returns the taboo-free SegmentResponse (response_model drops any stray key).
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

from .. import auth, config
from ..models.segment import SegmentResponse
from ..services import audit, dicom_utils, seg_store, segmentation, upload_guard
from ..security import client_ip
from .viewer import _looks_dicom

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["segment"])

_JOB_RE = re.compile(r"^[0-9a-f]{32}$")


def _disclaimer(modality: str) -> str:
    return config.CT_OVERLAY_DISCLAIMER if modality == "CT" else config.MR_OVERLAY_DISCLAIMER


async def _read_blobs(files: list[UploadFile]) -> list[bytes]:
    if not files:
        raise HTTPException(400, "No files uploaded.")
    if len(files) > config.SEGMENT_MAX_FILES:
        raise HTTPException(413, f"Too many files (max {config.SEGMENT_MAX_FILES}).")
    blobs, used = [], 0
    for f in files:
        data = await upload_guard.read_capped(f, config.SEGMENT_MAX_TOTAL_BYTES - used)
        if not data:
            continue
        used += len(data)
        if not _looks_dicom(data, f.filename or ""):
            raise HTTPException(422, "Segmentation accepts DICOM (.dcm) files only.")
        blobs.append(data)
    if not blobs:
        raise HTTPException(400, "No readable DICOM files.")
    return blobs


def _save_masks(label_vol: np.ndarray, view_id: str) -> tuple[list[str], int]:
    """Save one INDEXED label PNG per slice (mode L; pixel value == structure_id,
    0 = unlabeled) under SEGMENTS_DIR with opaque filenames. The frontend recolors
    it through the categorical legend."""
    urls = []
    for i in range(label_vol.shape[0]):
        fn = f"{view_id}_{i:03d}.png"
        Image.fromarray(label_vol[i].astype(np.uint8), mode="L").save(config.SEGMENTS_DIR / fn)
        urls.append(f"/static/segments/{fn}")
    edge = int(max(label_vol.shape[1], label_vol.shape[2])) if label_vol.ndim == 3 else 0
    return urls, edge


def _make_work(blobs: list[bytes], modality: str, task, roi_subset, series_id):
    """Closure run in the background: extract the HU/a.u. volume (de-ID + quarantine),
    run the active provider, save masks, and return a plain-dict result."""
    def work():
        volume = dicom_utils.build_seg_volume(blobs, series_id=series_id)
        # Defensive: never segment the wrong modality even if the header guard drifted.
        if modality == "CT" and not volume["is_ct"]:
            raise ValueError("volume is not CT")
        if modality == "MR" and volume["is_ct"]:
            raise ValueError("volume is not MR")
        regions, label_vol = segmentation.segment(volume, task=task, roi_subset=roi_subset)
        regions = regions[: config.SEGMENT_MAX_STRUCTURES]
        view_id = secrets.token_hex(6)
        mask_urls, mask_edge = _save_masks(np.asarray(label_vol), view_id)
        method, model, lic = segmentation.active_provider(volume["is_ct"])
        return {
            "regions": regions,
            "unit": volume["unit"],
            "identifiers_removed": volume["identifiers_removed"],
            "n_quarantined": volume["n_quarantined"],
            "burned_in": volume["burned_in"],
            "n_slices": volume["n_slices"],
            "series_id": volume["series_id"],
            "slice_positions": volume["slice_positions"],
            "mask_urls": mask_urls,
            "mask_edge": mask_edge,
            "method": method,
            "model": model,
            "license": lic,
            "provenance": f"{model} · {lic} · {config.OVERLAY_CAPTION}",
        }
    return work


def _response(job_id: str, modality: str, st: dict) -> SegmentResponse:
    base = dict(
        job_id=job_id, modality=modality, disclaimer=_disclaimer(modality),
        intensity_unit=("HU" if modality == "CT" else "a.u."),
        status="queued",
    )
    state = st.get("state")
    result = st.get("result")
    if state == "done" and result:
        base.update(
            status="done", computed=True,
            regions=result["regions"], structure_count=len(result["regions"]),
            model=result["model"], license=result["license"], method=result["method"],
            provenance=result.get("provenance"),
            identifiers_removed=result["identifiers_removed"],
            n_quarantined=result["n_quarantined"], burned_in=result["burned_in"],
            n_slices=result["n_slices"], mask_urls=result["mask_urls"],
            mask_edge=result["mask_edge"], intensity_unit=result["unit"],
            series_id=result.get("series_id"), slice_positions=result.get("slice_positions"),
        )
    elif state == "error":
        base.update(status="error", detail=st.get("detail") or "segmentation failed")
    elif state in (None, "unknown"):
        base.update(status="unknown", detail="no such job")
    else:
        base.update(status=state)  # queued | running
    return SegmentResponse(**base)


async def _launch(request: Request, files: list[UploadFile], modality: str,
                  enabled: bool, allowed_modalities: set, task, roi_subset, series_id,
                  background_tasks: BackgroundTasks) -> SegmentResponse:
    upload_guard.reject_oversize_early(request, config.SEGMENT_MAX_TOTAL_BYTES)
    ip = client_ip(request)
    if not enabled:
        audit.log_event(None, "segment", request.url.path, ip, 503)
        raise HTTPException(503, "Anatomy segmentation is disabled on this deployment.")
    if not segmentation.available(modality):
        raise HTTPException(503, "Segmentation provider unavailable.")
    # Whitelist enforcement at the API boundary — a non-anatomy / non-commercial task
    # is rejected BEFORE any pixels are read or any weight loads.
    if task:
        try:
            config.assert_task_allowed(task)
        except config.ModelNotAllowed as e:
            audit.log_event(None, "segment", request.url.path, ip, 403)
            raise HTTPException(403, str(e))
    if series_id is not None and not re.fullmatch(r"[0-9a-f]{1,64}", series_id or ""):
        raise HTTPException(422, "Bad series id.")
    blobs = await _read_blobs(files)
    # Header-only modality guard (no pixel decode): refuse the wrong modality.
    mod, mixed = await run_in_threadpool(dicom_utils.consensus_modality, blobs)
    if mixed or mod not in allowed_modalities:
        raise HTTPException(422, f"This endpoint segments {modality} only "
                                 f"(uploaded modality: {mod or 'unknown'}).")
    params = {"task": task, "roi": roi_subset, "series": series_id, "model": config.SEGMENT_MODEL,
              "edge": config.SEGMENT_MAX_EDGE, "slices": config.SEGMENT_MAX_SLICES}
    content_hash = hashlib.sha256(b"".join(blobs)).hexdigest()
    job_id = hashlib.sha256((content_hash + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:32]
    try:
        job_id, is_new = seg_store.submit(
            job_id, _make_work(blobs, modality, task, roi_subset, series_id),
            meta={"modality": modality, "kind": "segment"})
    except seg_store.QueueFull:
        raise HTTPException(429, "Segmentation queue is busy — retry shortly.")
    if is_new:
        background_tasks.add_task(seg_store.run, job_id)
    audit.log_event(None, "segment", request.url.path, ip, 200)
    return _response(job_id, modality, seg_store.status(job_id))


@router.post("/segment", response_model=SegmentResponse)
async def segment_ct(request: Request, background_tasks: BackgroundTasks,
                     files: list[UploadFile] = File(...),
                     task: str | None = Form(default=None),
                     roi_subset: str | None = Form(default=None),
                     series_id: str | None = Form(default=None)):
    return await _launch(request, files, "CT", config.SEGMENT_ENABLED,
                         config.SEGMENT_MODALITIES, task, roi_subset, series_id, background_tasks)


@router.post("/mr-segment", response_model=SegmentResponse)
async def segment_mr(request: Request, background_tasks: BackgroundTasks,
                     files: list[UploadFile] = File(...),
                     task: str | None = Form(default=None),
                     roi_subset: str | None = Form(default=None),
                     series_id: str | None = Form(default=None)):
    return await _launch(request, files, "MR", config.MR_SEGMENT_ENABLED,
                         config.MR_SEGMENT_MODALITIES, task, roi_subset, series_id, background_tasks)


@router.get("/segment/{job_id}", response_model=SegmentResponse)
async def segment_poll(job_id: str):
    if not _JOB_RE.match(job_id):
        raise HTTPException(400, "Bad job id.")
    st = seg_store.status(job_id)
    meta = st.get("meta") or {}
    # The job store is shared with /api/ct-detect; never render another feature's job
    # through the segment response builder (its result shape differs).
    if meta.get("kind") not in (None, "segment"):
        st = {"state": "unknown", "result": None, "detail": None, "meta": {}}
    return _response(job_id, meta.get("modality", "CT"), st)
