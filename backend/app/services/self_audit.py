"""Self-audit / abstention gate — "the AI that knows when to shut up."

Before the classifier scores anything, decide whether the input even looks like a
frontal chest radiograph. A composite out-of-distribution / quality score drives
READ / DOWN-WEIGHT / ABSTAIN:

  * READ         — looks like a CXR; score normally.
  * DOWN-WEIGHT  — borderline / low quality; score but flag caution.
  * ABSTAIN      — clearly not a readable CXR; refuse BEFORE scoring.

Signals (all CPU, license-clean, no training):
  1. TorchXRayVision autoencoder (Apache-2.0) reconstruction error — trained on
     normal CXRs, so a knee/CT/selfie/dog reconstructs poorly (strong signal).
  2. Cheap image heuristics — aspect ratio, dynamic range, blur (Laplacian var),
     near-constant frames.

The AE is optional (config.SELF_AUDIT_AE); if it can't load, the gate degrades to
heuristics only and never hard-ABSTAINs on the AE signal alone.
"""

import logging
import threading

import numpy as np
from PIL import Image

from .. import config

logger = logging.getLogger(__name__)

_ae = None
_ae_lock = threading.Lock()
_ae_failed = False


def _get_ae():
    global _ae, _ae_failed
    if _ae is None and not _ae_failed and config.SELF_AUDIT_AE:
        with _ae_lock:
            if _ae is None and not _ae_failed:
                try:
                    import torchxrayvision as xrv
                    logger.info("Loading TorchXRayVision autoencoder for OOD gate ...")
                    _ae = xrv.autoencoders.ResNetAE(weights="101-elastic")
                    _ae.eval()
                except Exception:
                    logger.exception("OOD autoencoder failed to load; heuristics only")
                    _ae_failed = True
    return _ae


def warm_up():
    if config.SELF_AUDIT_ENABLED:
        _get_ae()


def _ae_reconstruction_error(img8: np.ndarray) -> float | None:
    ae = _get_ae()
    if ae is None:
        return None
    try:
        import torch
        import torchxrayvision as xrv

        img = xrv.datasets.normalize(img8.astype(np.float32), 255)
        h, w = img.shape
        size = max(h, w)
        sq = np.full((size, size), float(img.min()), dtype=np.float32)
        sq[(size - h) // 2:(size - h) // 2 + h, (size - w) // 2:(size - w) // 2 + w] = img
        arr = np.asarray(Image.fromarray(sq).resize((224, 224), Image.BILINEAR), dtype=np.float32)
        tensor = torch.from_numpy(arr)[None, None, ...]
        with _ae_lock:
            with torch.no_grad():
                out = ae(tensor)
                recon = out["out"] if isinstance(out, dict) else out
        # Normalize both to [0,1] before MSE so the error scale is stable.
        t = (tensor - tensor.min()) / (tensor.max() - tensor.min() + 1e-6)
        r = (recon - recon.min()) / (recon.max() - recon.min() + 1e-6)
        return float(torch.mean((t - r) ** 2))
    except Exception:
        logger.exception("AE reconstruction failed; skipping AE signal")
        return None


def _heuristics(img8: np.ndarray) -> tuple[float, list[str]]:
    """Cheap quality/OOD score in [0,1] + reasons (higher = more suspect)."""
    import cv2

    reasons = []
    score = 0.0
    h, w = img8.shape
    aspect = w / h if h else 1.0
    if aspect < 0.5 or aspect > 2.0:
        score += 0.4
        reasons.append(f"unusual aspect ratio ({aspect:.2f})")

    dyn = float(img8.max()) - float(img8.min())
    if dyn < 40:
        score += 0.5
        reasons.append("very low dynamic range (near-blank image)")

    std = float(img8.std())
    if std < 12:
        score += 0.3
        reasons.append("near-constant image")

    blur = float(cv2.Laplacian(img8, cv2.CV_64F).var())
    if blur < 20:
        score += 0.25
        reasons.append("very low sharpness (blurred)")

    return min(1.0, score), reasons


def _ae_component(img8: np.ndarray) -> tuple[float | None, list[str]]:
    err = _ae_reconstruction_error(img8)
    if err is None:
        return None, []
    lo, hi = config.AE_ERR_LOW, config.AE_ERR_HIGH
    norm = (err - lo) / max(hi - lo, 1e-6)
    norm = min(1.0, max(0.0, norm))
    reasons = []
    if norm > 0.6:
        reasons.append("does not reconstruct like a chest radiograph")
    return norm, reasons


def _structure_component(img8: np.ndarray) -> tuple[float, list[str]]:
    """Detect a SYNTHETIC / non-anatomical image (test pattern, UI screenshot, a
    rendered shape). A real radiograph has organic sensor texture EVERYWHERE and a
    broad, continuous histogram; a synthetic image has large EXACTLY-flat fills and
    very few distinct grey levels. This is a RELIABLE "not a radiograph" signal — a
    genuine CXR never looks like this — so it may force ABSTAIN. Near-black collimation
    borders are excluded so a legitimately-bordered film is not mistaken for a fill.
    """
    import cv2

    reasons: list[str] = []
    f = img8.astype(np.float32)
    # Local variance in a 7x7 window (E[x^2] - E[x]^2). A perfectly flat fill is 0;
    # real sensor/film texture is > 1 almost everywhere.
    mean = cv2.boxFilter(f, -1, (7, 7), borderType=cv2.BORDER_REFLECT)
    local_var = cv2.boxFilter(f * f, -1, (7, 7), borderType=cv2.BORDER_REFLECT) - mean * mean
    fg = img8 > config.BACKGROUND_LEVEL            # ignore near-black collimation border
    n_fg = int(fg.sum())
    if n_fg < 64:
        return 0.0, []                              # essentially blank; other signals handle it
    flat_frac = float(((local_var < 1.0) & fg).sum()) / n_fg

    # Histogram entropy over the NON-background pixels (bits). Real CXR ~6-7.5;
    # a 2-3 tone synthetic image ~1-2.
    vals = img8[fg]
    p = np.bincount(vals, minlength=256).astype(np.float64)
    p /= p.sum()
    nz = p[p > 0]
    entropy = float(-(nz * np.log2(nz)).sum())
    top1 = float(p.max())

    score = 0.0
    if flat_frac > 0.30:                            # 0.30 -> 0.5 ... 0.60+ -> 1.0
        score = max(score, min(1.0, 0.5 + (flat_frac - 0.30) / 0.30 * 0.5))
        reasons.append(f"{flat_frac * 100:.0f}% of the imaged region is perfectly flat — "
                       "not radiographic texture (looks synthetic)")
    if entropy < 3.5 and flat_frac > 0.15:
        score = max(score, 0.85)
        reasons.append(f"very few distinct grey levels (entropy {entropy:.1f} bits) — looks synthetic")
    if top1 > 0.55:
        score = max(score, 0.8)
        reasons.append("a single intensity dominates the image (uniform fill)")

    # FIX #5 — near-perfectly SMOOTH content (rendered gradients / ramps / vignettes)
    # that the flat + entropy checks miss: they are NOT flat (a gradient varies) and
    # have high entropy, yet carry no radiographic texture. A real radiograph has fine
    # sensor/anatomical high-frequency detail EVERYWHERE, so almost no pixels have a
    # near-zero Laplacian; a mathematically-smooth synthetic image has almost all of
    # them. The bar is deliberately extreme (>= 0.90 of the imaged region, and the
    # image must be contrasty, not a near-blank frame) so a genuine — even slightly
    # blurred — chest film is never over-abstained here.
    dyn = float(img8.max()) - float(img8.min())
    if dyn >= 40.0:
        lap = np.abs(cv2.Laplacian(img8, cv2.CV_64F))
        smooth_frac = float(((lap <= 1.0) & fg).sum()) / n_fg
        if smooth_frac >= 0.90:
            score = max(score, 0.85)
            reasons.append(f"{smooth_frac * 100:.0f}% of the imaged region is near-perfectly "
                           "smooth (no radiographic texture) — looks rendered/synthetic, "
                           "not a radiograph")
    return min(1.0, score), reasons


def _color_component(color_saturation: float) -> tuple[float, list[str]]:
    if color_saturation <= config.COLOR_SAT_OOD:
        return 0.0, []
    # A saturated photo (sat ~0.2-0.5) maps toward 1.0.
    comp = min(1.0, color_saturation / 0.25)
    return comp, ["color image — radiographs are grayscale"]


def assess(img8: np.ndarray, color_saturation: float = 0.0) -> dict:
    """Return {ood_score, competence, reasons, ae_error_norm}.

    Only RELIABLE signals (color, or a very high AE error) can force ABSTAIN.
    Quality heuristics (blur, aspect) can DOWN-WEIGHT but never hard-refuse a
    plausibly-real radiograph.
    """
    if not config.SELF_AUDIT_ENABLED:
        return {"ood_score": 0.0, "competence": "read", "reasons": [], "ae_error_norm": None}

    color_ood, color_reasons = _color_component(color_saturation)
    struct_ood, struct_reasons = _structure_component(img8)
    h_score, h_reasons = _heuristics(img8)
    ae_norm, ae_reasons = _ae_component(img8)

    # RELIABLE OOD signals may force ABSTAIN: a color image, a synthetic/flat image, or
    # a very high AE error. Quality heuristics (blur/aspect) only DOWN-WEIGHT.
    reliable_ood = max(color_ood, struct_ood,
                       (ae_norm or 0.0) if (ae_norm and ae_norm >= 0.9) else 0.0)
    ood = max(color_ood, struct_ood, ae_norm or 0.0, 0.6 * h_score)

    if reliable_ood >= config.OOD_ABSTAIN_THRESHOLD:
        competence = "abstain"
    elif ood >= config.OOD_CAUTION_THRESHOLD:
        competence = "down-weight"
    else:
        competence = "read"

    return {"ood_score": round(float(ood), 3), "competence": competence,
            "reasons": color_reasons + struct_reasons + ae_reasons + h_reasons,
            "ae_error_norm": ae_norm}
