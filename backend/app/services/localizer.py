"""High-resolution Grad-CAM localizer (res512) for FLAGGED findings only.

Rationale (per expert review): the DenseNet-res224 classifier has a 7x7 CAM grid
where one cell ~= one lung zone, so a crisp contour is never defensible and the
pointing score is capped by resolution. Running a res512 ResNet (16x16 grid) as a
SEPARATE localizer — invoked ONLY for the handful of flagged findings, never for
every classified label — buys real spatial resolution at a bounded latency cost
(~a few seconds per flagged finding, not per label).

Division of labour, stated honestly to the reader:
  * the 224 ENSEMBLE produces the displayed CONFIDENCE (fast, per request);
  * this 512 model produces only the ATTENTION MAP for a flagged label.
So the CAM explains THIS model's logit for the label, not the exact ensemble
number — captioned as such. Off unless config.LOCALIZER_WEIGHTS is set.
"""
import logging
import threading

import numpy as np
from PIL import Image

from .. import config

logger = logging.getLogger(__name__)

_model = None
_wrapper = None
_pathologies: list[str] = []
_lock = threading.Lock()
_infer_lock = threading.Lock()
_load_failed = False


def available() -> bool:
    return bool(config.LOCALIZER_WEIGHTS) and not _load_failed


def _load():
    global _model, _wrapper, _pathologies, _load_failed
    if _model is not None or _load_failed:
        return _model
    with _lock:
        if _model is not None or _load_failed:
            return _model
        try:
            import torch.nn as nn
            import torchxrayvision as xrv

            logger.info("Loading res512 localizer %s ...", config.LOCALIZER_WEIGHTS)
            m = xrv.models.ResNet(weights=config.LOCALIZER_WEIGHTS)
            m.eval()

            class _Raw(nn.Module):
                """Raw logits (bypassing xrv op_norm/sigmoid so Grad-CAM gradients
                don't saturate). Shares layers, so model.layer4[-1] is a valid
                target here too."""
                def __init__(self, base):
                    super().__init__()
                    self.m = base.model  # torchvision resnet50

                def forward(self, x):
                    return self.m(x)

            _wrapper = _Raw(m).eval()
            _model = m
            _pathologies = list(m.pathologies)
        except Exception:
            logger.exception("res512 localizer failed to load; falling back to densenet CAM")
            _load_failed = True
    return _model


def warm_up():
    if config.LOCALIZER_WEIGHTS:
        _load()


def _preprocess(img8: np.ndarray):
    """uint8 HxW -> (1x1x512x512 tensor, geometry) via the SAME pad-to-square as the
    classifier, so attention maps back to original coordinates cleanly."""
    import torch
    import torchxrayvision as xrv

    img = xrv.datasets.normalize(img8.astype(np.float32), 255)
    h, w = img.shape
    size = max(h, w)
    pt, pl = (size - h) // 2, (size - w) // 2
    square = np.full((size, size), float(img.min()), dtype=np.float32)
    square[pt:pt + h, pl:pl + w] = img
    arr = np.asarray(Image.fromarray(square).resize((512, 512), Image.BILINEAR), dtype=np.float32)
    return torch.from_numpy(arr)[None, None, ...], (pt, pl, h, w, size)


def _to_original(cam512: np.ndarray, geom) -> np.ndarray:
    import cv2
    pt, pl, h, w, size = geom
    cam_sq = cv2.resize(cam512, (size, size), interpolation=cv2.INTER_LINEAR)
    return cam_sq[pt:pt + h, pl:pl + w]


# --- Progressive enhancement (T7): compute the sharp res512 CAM in the BACKGROUND
# after the fast 224 result has already shipped, then the frontend swaps it in with
# a "sharpening..." chip. Zero GPU: the ~10s/CAM cost is off the request path.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def hires_result(image_id: str) -> dict:
    with _jobs_lock:
        return dict(_jobs.get(image_id, {"status": "unknown", "findings": []}))


def compute_hires(image_id: str, labels: list[str]) -> None:
    """Background job: recompute each flagged label's CAM at 16x16 and save a
    `_hires` overlay. Loads the saved display image and re-masks it (so the marker
    shortcut defence still holds) — no arrays crossing the task boundary."""
    with _jobs_lock:
        _jobs[image_id] = {"status": "pending", "findings": []}
    try:
        from PIL import Image
        from . import vision_xray
        path = config.UPLOADS_DIR / f"{image_id}.png"
        if not path.exists() or not available():
            with _jobs_lock:
                _jobs[image_id] = {"status": "error", "findings": []}
            return
        img8 = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)
        img8, _ = vision_xray._cap_resolution(img8, None)
        img8m, _ = vision_xray._mask_burned_in_markers(img8)
        out = []
        for label in labels:
            camm = cam(img8m, label)
            if camm is None or camm.max() <= 0:
                continue
            state, contour_ok = vision_xray._classify_cam(camm, 16)
            if state != "localized":
                continue
            _mx, _ar, contour = vision_xray._measure_attention(camm, None, None)
            fname = f"{image_id}_{vision_xray._label_slug(label)}_hires.png"
            vision_xray._save_overlay(img8, camm, None, config.HEATMAPS_DIR / fname,
                                      contour=contour, draw_contour=contour_ok)
            out.append({"label": label, "heatmap_url": f"/static/heatmaps/{fname}"})
        with _jobs_lock:
            _jobs[image_id] = {"status": "done", "findings": out}
    except Exception:
        logger.exception("hires localization failed for %s", image_id)
        with _jobs_lock:
            _jobs[image_id] = {"status": "error", "findings": []}


def cam(img8: np.ndarray, label: str) -> np.ndarray | None:
    """16x16-grid Grad-CAM for `label` in ORIGINAL-image coords, or None if the
    localizer is off / failed / lacks the label. Caller passes the SAME (marker-
    masked) image the classifier saw."""
    if not config.LOCALIZER_WEIGHTS:
        return None
    m = _load()
    if m is None or label not in _pathologies:
        return None
    from pytorch_grad_cam import GradCAM
    from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

    idx = _pathologies.index(label)
    tensor, geom = _preprocess(img8)
    try:
        with _infer_lock:
            with GradCAM(model=_wrapper, target_layers=[m.model.layer4[-1]]) as g:
                grayscale = g(input_tensor=tensor, targets=[ClassifierOutputTarget(idx)])
        return _to_original(grayscale[0], geom)
    except Exception:
        logger.exception("res512 Grad-CAM failed for %s", label)
        return None
