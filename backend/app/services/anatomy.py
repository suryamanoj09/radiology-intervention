"""Anatomy-awareness gate.

The classifier + Grad-CAM sometimes attend to the wrong place — e.g. flag
"Cardiomegaly" while the attention sits on the patient's arm or an image corner,
not the heart. This module segments chest anatomy (license-clean TorchXRayVision
PSPNet) and checks whether a finding's attention region actually overlaps the
anatomy that finding could plausibly come from (heart/mediastinum for cardiac
findings, lungs for lung findings, bones for fractures). Low overlap => the flag
is anatomically implausible and is suppressed or cautioned.
"""

import logging
import threading

import numpy as np

from .. import config

logger = logging.getLogger(__name__)

_seg = None
_lock = threading.Lock()
_failed = False

# Structure groups (PSPNet target names).
LUNG = {"Left Lung", "Right Lung"}
HEART = {"Heart", "Mediastinum", "Aorta", "Left Hilus Pulmonis", "Right Hilus Pulmonis"}
BONE = {"Left Clavicle", "Right Clavicle", "Left Scapula", "Right Scapula", "Spine"}
DIAPHRAGM = {"Facies Diaphragmatica"}

# Which structures a given model label could plausibly arise from.
_RELEVANT = {
    "Cardiomegaly": HEART,
    "Enlarged Cardiomediastinum": HEART,
    "Effusion": LUNG | DIAPHRAGM,
    "Pneumonia": LUNG, "Consolidation": LUNG, "Infiltration": LUNG,
    "Nodule": LUNG, "Mass": LUNG, "Lung Lesion": LUNG, "Lung Opacity": LUNG,
    "Emphysema": LUNG, "Fibrosis": LUNG, "Edema": LUNG, "Atelectasis": LUNG,
    "Pneumothorax": LUNG, "Pleural_Thickening": LUNG,
    "Fracture": BONE,
    "Hernia": DIAPHRAGM | LUNG,
}


def relevant_structures(label: str) -> set[str]:
    return _RELEVANT.get(label, LUNG | HEART)  # default: central chest


def _get_seg():
    global _seg, _failed
    if _seg is None and not _failed:
        with _lock:
            if _seg is None and not _failed:
                try:
                    import torchxrayvision as xrv
                    logger.info("Loading anatomy segmentation (PSPNet) ...")
                    m = xrv.baseline_models.chestx_det.PSPNet()
                    m.eval()
                    _seg = m
                except Exception:
                    logger.exception("Anatomy segmentation failed to load; gate disabled")
                    _failed = True
    return _seg


def warm_up():
    if config.ANATOMY_GATE_ENABLED:
        _get_seg()


def segment(img8: np.ndarray):
    """Return {structure_name: bool mask (H,W in img8 geometry)} or None.

    Uses the same pad-to-square transform as the classifier so the returned masks
    align with the Grad-CAM (also in img8 geometry)."""
    if not config.ANATOMY_GATE_ENABLED:
        return None
    seg = _get_seg()
    if seg is None:
        return None
    try:
        import torch
        import torch.nn.functional as F
        import torchxrayvision as xrv

        h, w = img8.shape
        size = max(h, w)
        pt, pl = (size - h) // 2, (size - w) // 2
        img = xrv.datasets.normalize(img8.astype(np.float32), 255)
        sq = np.full((size, size), float(img.min()), dtype=np.float32)
        sq[pt:pt + h, pl:pl + w] = img
        t = torch.from_numpy(sq)[None, None]
        t = F.interpolate(t, size=(512, 512), mode="bilinear", align_corners=False)
        with _lock:
            with torch.no_grad():
                probs = torch.sigmoid(seg(t))[0]
        probs = F.interpolate(probs[None], size=(size, size),
                              mode="bilinear", align_corners=False)[0].numpy()
        return {name: (probs[i][pt:pt + h, pl:pl + w] >= 0.5)
                for i, name in enumerate(seg.targets)}
    except Exception:
        logger.exception("Anatomy segmentation failed at inference")
        return None


def attention_overlap(cam_mask: np.ndarray, structures: set[str], masks: dict) -> float | None:
    """Fraction of the high-attention region that lies on the relevant anatomy."""
    if not masks:
        return None
    m = int(cam_mask.sum())
    if m == 0:
        return None
    rel = np.zeros(cam_mask.shape, dtype=bool)
    for s in structures:
        mk = masks.get(s)
        if mk is not None:
            rel |= mk
    if not rel.any():
        return None
    return int(np.logical_and(cam_mask, rel).sum()) / m
