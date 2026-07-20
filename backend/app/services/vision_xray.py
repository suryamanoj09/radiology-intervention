"""Chest X-ray analysis: pretrained TorchXRayVision DenseNet ensemble + Grad-CAM.

Outputs per-pathology model confidence (banded op_norm, never called a diagnosis)
and a Grad-CAM heatmap of model attention for each flagged finding. A heatmap is a
region of model attention, NOT a lesion boundary, and no size is inferred from it —
any measurement must come from the clinician's caliper.

Phase-0 correctness properties are preserved and extended:
  * Displayed confidence uses each model's op_norm output — a per-class banded
    score calibrated so 0.5 == that model's operating point. "confidence >= 0.5"
    is exactly "flagged", and classes with no calibrated operating point (op_norm
    would return a misleading 0.5) are dropped.
  * Grad-CAM runs on the RAW LOGITS via a per-model wrapper, because op_norm +
    sigmoid saturate the gradients and make attention maps vanish.
  * Pad-to-square preprocessing keeps the full field of view.

No-training correctness upgrade:
  * ENSEMBLE — the banded outputs of one or more TorchXRayVision weights are
    averaged PER LABEL (aligned by pathology name). Each model keeps its own
    op_threshs, so every vote is in banded space before averaging; a model only
    votes on labels it actually has and whose op_thresh is not NaN. Configurable
    via config.ENSEMBLE_WEIGHTS; defaults to a single model for CPU speed.
  * PER-FINDING LOCALIZATION — every flagged finding (capped at config.LOCALIZE_MAX,
    emergency labels first) gets its own Grad-CAM region/overlay, sourced from the
    ensemble model that scored that label highest (the model most responsible for
    the flag). Grad-CAM stays on that owner model's logit wrapper.
  * Optional test-time augmentation (horizontal flip average), env-gated.
  * Per-label flag thresholds may be overridden from a calibration JSON emitted by
    the validation harness (config.LABEL_THRESHOLDS) — no retraining.

None of this claims improved accuracy; only the validation harness can measure it.
"""

import json
import logging
import re
import threading

import numpy as np
from PIL import Image

from .. import config
from ..models.schemas import AnalyzeResponse, BBox, Finding
from . import anatomy, calibration, localizer, reliability, triage

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[0-9a-f]{12}$")

_models = None                  # list[_XRVModel]: the ensemble
_model_lock = threading.Lock()
_infer_lock = threading.Lock()  # Grad-CAM re-enables grads on the shared models


class _LogitWrapper:
    """Returns the classifier's raw logits (bypassing sigmoid + op_norm) so
    Grad-CAM has non-saturated gradients. Shares layers with the real model, so
    model.features[-1] is a valid target layer here too."""

    def __init__(self, m):
        import torch.nn as nn

        class _Net(nn.Module):
            def __init__(self, base):
                super().__init__()
                self.features = base.features
                self.classifier = base.classifier

            def forward(self, x):
                import torch.nn.functional as F
                f = self.features(x)
                out = F.relu(f, inplace=True)
                out = F.adaptive_avg_pool2d(out, (1, 1)).flatten(1)
                return self.classifier(out)

        self.net = _Net(m).eval()


class _XRVModel:
    """One pretrained TorchXRayVision model plus its Grad-CAM logit wrapper.

    Keeps op_threshs so the model's output stays banded (op_norm: 0.5 == this
    model's operating point), exactly as the Phase-0 single model did. Only labels
    this model actually has (and whose op_thresh is not NaN) may vote / localize."""

    __slots__ = ("name", "model", "logit", "op_threshs", "pathologies")

    def __init__(self, name, model, op_threshs):
        self.name = name
        self.model = model
        self.logit = _LogitWrapper(model)
        self.op_threshs = op_threshs
        self.pathologies = list(model.pathologies)

    def votes(self, i: int) -> bool:
        """True if label index i is a real, calibrated class on this model."""
        if not self.pathologies[i]:
            return False
        if (self.op_threshs is not None and i < len(self.op_threshs)
                and np.isnan(float(self.op_threshs[i]))):
            return False
        return True


def _load_one(name: str) -> _XRVModel:
    import torchxrayvision as xrv

    logger.info("Loading TorchXRayVision %s ...", name)
    model = xrv.models.DenseNet(weights=name)
    model.eval()
    op = getattr(model, "op_threshs", None)
    op = op.detach().clone() if op is not None else None
    return _XRVModel(name, model, op)


def _get_models():
    """Load the configured ensemble once (double-checked lock). Falls back to the
    default single model if a configured weight fails to load, so the app never
    comes up with no model."""
    global _models
    if _models is None:
        with _model_lock:
            if _models is None:
                import torch
                torch.set_num_threads(max(1, (torch.get_num_threads() or 2)))
                loaded: list[_XRVModel] = []
                for nm in config.ENSEMBLE_WEIGHTS:
                    try:
                        loaded.append(_load_one(nm))
                    except Exception:
                        logger.exception("Failed to load ensemble weight %s; skipping", nm)
                if not loaded:
                    loaded.append(_load_one("densenet121-res224-all"))
                _models = loaded
                logger.info("Ensemble ready: %s (TTA hflip=%s)",
                            [m.name for m in _models], config.TTA_HFLIP)
    return _models


def warm_up():
    """Load the ensemble at startup so the first request isn't a cold multi-second
    stall. On the free Space this also triggers the one-time weight download for
    each configured model."""
    models = _get_models()
    # T1 guard: if the model's label set ever drifts from the display contract, the
    # UI could silently mis-name or drop a label. Log loudly (don't crash the app).
    try:
        from . import label_map
        live = set(models[0].pathologies)
        contract = set(label_map.RAW_DISPLAY.keys())
        if live - contract:
            logger.error("Model emits labels with NO display mapping: %s", live - contract)
        if contract - live:
            logger.warning("Display contract has labels the model no longer emits: %s",
                           contract - live)
    except Exception:
        logger.exception("label-contract check failed")


def _preprocess(img8: np.ndarray):
    """uint8 HxW -> (tensor 1x1x224x224, geometry).

    PAD to square (not center-crop) so the full field of view is analyzed — a
    center crop on portrait films silently discards the lung apices and
    costophrenic angles, exactly where pneumothorax and effusion present.
    """
    import torch
    import torchxrayvision as xrv

    img = xrv.datasets.normalize(img8.astype(np.float32), 255)
    h, w = img.shape
    size = max(h, w)
    pad_top, pad_left = (size - h) // 2, (size - w) // 2
    square = np.full((size, size), float(img.min()), dtype=np.float32)
    square[pad_top:pad_top + h, pad_left:pad_left + w] = img

    pil = Image.fromarray(square).resize((224, 224), Image.BILINEAR)
    arr = np.asarray(pil, dtype=np.float32)
    tensor = torch.from_numpy(arr)[None, None, ...]
    return tensor, (pad_top, pad_left, h, w, size)


def _cap_resolution(img8: np.ndarray, pixel_spacing: float | None):
    """Bound the working image so overlay memory/size stays fixed regardless of input."""
    h, w = img8.shape
    longest = max(h, w)
    if longest <= config.MAX_OVERLAY_EDGE:
        return img8, pixel_spacing
    scale = config.MAX_OVERLAY_EDGE / longest
    new = (int(round(w * scale)), int(round(h * scale)))
    small = np.asarray(Image.fromarray(img8).resize(new, Image.BILINEAR), dtype=np.uint8)
    return small, (pixel_spacing / scale if pixel_spacing else None)


def _mask_burned_in_markers(img8: np.ndarray) -> tuple[np.ndarray, int]:
    """Detect & inpaint burned-in annotation markers (side letters "L"/"R",
    "PORTABLE", "AP", timestamps) so the model cannot take a shortcut on the text
    instead of the anatomy (Zech 2018; DeGrave 2021, "shortcuts over signal").

    Returns (image, n_pixels_inpainted). The image is the SAME shape/dtype; when
    nothing marker-like is found it is returned unchanged. Detection is deliberately
    conservative — near-saturated, COMPACT glyphs in the outer margin bands only —
    so the central chest is never touched and a genuinely bright finding inside the
    lungs cannot be erased. We INPAINT (fill from neighbours) rather than crop, so
    the lung apices and costophrenic angles are preserved.
    """
    import cv2

    if not config.MASK_MARKERS_ENABLED:
        return img8, 0
    h, w = img8.shape
    if h < 64 or w < 64:
        return img8, 0

    # 1) Near-saturated pixels — burned-in text is drawn at/near pure white.
    bright = (img8 >= config.MARKER_BRIGHT_MIN).astype(np.uint8)
    if int(bright.sum()) == 0:
        return img8, 0

    # 2) Restrict to the outer margin bands. The centre of the film (where real
    #    pathology lives) is protected, so we can never inpaint a true finding.
    margin = np.zeros((h, w), np.uint8)
    my, mx = int(config.MARKER_MARGIN_FRAC * h), int(config.MARKER_MARGIN_FRAC * w)
    if my > 0:
        margin[:my, :] = 1
        margin[h - my:, :] = 1
    if mx > 0:
        margin[:, :mx] = 1
        margin[:, w - mx:] = 1
    cand = cv2.bitwise_and(bright, margin)
    if int(cand.sum()) == 0:
        return img8, 0

    # 3) Join nearby glyphs into words, then keep only marker-LIKE components:
    #    compact, small relative to the frame, and not a long thin border line /
    #    collimator edge.
    cand = cv2.morphologyEx(
        cand, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(cand, 8)
    mask = np.zeros((h, w), np.uint8)
    max_area = config.MARKER_MAX_AREA_FRAC * h * w
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        cw = int(stats[i, cv2.CC_STAT_WIDTH])
        ch = int(stats[i, cv2.CC_STAT_HEIGHT])
        if area < config.MARKER_MIN_AREA:      # single-pixel speck / noise
            continue
        if area > max_area:                    # a bright FIELD (shoulder), not a marker
            continue
        if cw > 0.4 * w or ch > 0.4 * h:       # long border line / collimator edge
            continue
        mask[lbl == i] = 1
    if int(mask.sum()) == 0:
        return img8, 0

    # 4) Grow the mask to cover glyph halos, then inpaint from surrounding tissue.
    mask = cv2.dilate(
        mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=2)
    inpainted = cv2.inpaint(img8, mask, config.MARKER_INPAINT_RADIUS, cv2.INPAINT_TELEA)
    return inpainted, int(mask.sum())


def _banded(m: _XRVModel, tensor) -> np.ndarray:
    """Banded (op_norm) output for one model, optionally averaged with its
    horizontal flip (TTA). Labels here are side-agnostic, so the flip is a valid
    robustness average. Caller must already hold _infer_lock + torch.no_grad."""
    import torch

    out = m.model(tensor)[0].numpy()
    if config.TTA_HFLIP:
        flipped = torch.flip(tensor, dims=[3])
        out = (out + m.model(flipped)[0].numpy()) / 2.0
    return out


def _score(tensor) -> dict[str, tuple[float, "_XRVModel", int]]:
    """Ensemble-average banded confidence per label.

    Returns {label: (mean_score, owner_model, owner_class_idx)}. The owner is the
    model that scored the label highest — used to source that label's Grad-CAM from
    the model most responsible for flagging it. Labels are aligned across models by
    name, so models with different pathology lists ensemble only where they overlap.
    """
    import torch

    agg: dict[str, list[tuple[float, _XRVModel, int]]] = {}
    with _infer_lock:
        with torch.no_grad():
            for m in _get_models():
                banded = _banded(m, tensor)
                for i, label in enumerate(m.pathologies):
                    if not m.votes(i):
                        continue
                    agg.setdefault(label, []).append((float(banded[i]), m, i))

    out: dict[str, tuple[float, _XRVModel, int]] = {}
    for label, entries in agg.items():
        mean = sum(e[0] for e in entries) / len(entries)
        best = max(entries, key=lambda e: e[0])
        out[label] = (mean, best[1], best[2])
    return out


def _threshold_for(label: str) -> float:
    """Per-label flag threshold: calibration override if present, else the floor."""
    return config.LABEL_THRESHOLDS.get(label, config.FINDING_THRESHOLD)


_auroc_cache = None


def _label_auroc() -> dict:
    """Per-label detection metrics from the behaviour card (auroc + reliability +
    positives), for AUROC-based auto-denial. Cached. Maps label -> dict."""
    global _auroc_cache
    if _auroc_cache is not None:
        return _auroc_cache
    out = {}
    try:
        if config.BEHAVIOR_CARD_PATH.exists():
            card = json.loads(config.BEHAVIOR_CARD_PATH.read_text(encoding="utf-8"))
            for row in card.get("detection", []):
                if row.get("auroc") is not None:
                    out[row["pathology"]] = {
                        "auroc": row["auroc"],
                        "reliable": bool(row.get("reliable", False)),
                        "positives": int(row.get("positives", 0) or 0),
                    }
    except Exception:
        logger.exception("behaviour card AUROC load failed")
    _auroc_cache = out
    return out


def _denial(label: str):
    """(reason, auroc) if `label` is too weak to surface as a finding, else None.

    AUROC-based denial fires ONLY when the measurement is RELIABLE (enough positives).
    A sub-floor AUROC from a tiny validation sample (Pneumonia 0.46 on 2 positives,
    Nodule 0.63 on 7) is statistical noise, not evidence the label is weak — hiding
    the label on that basis would assert a measurement we don't have. Such labels
    surface WITH the AUROC-weak + not-calibrated cautions the UI already shows. The
    explicit LABEL_DENYLIST (e.g. Fracture) is independent and always denies.
    """
    info = _label_auroc().get(label)
    a = info["auroc"] if info else None
    if label in config.LABEL_DENYLIST:
        return ("this model's label is unreliable (report-mention supervision, no "
                "site, uncalibrated)", a)
    if info and a is not None and a < config.LABEL_MIN_AUROC:
        if info["reliable"] or not config.LABEL_MIN_AUROC_REQUIRE_RELIABLE:
            return (f"measured AUROC {a} is below the {config.LABEL_MIN_AUROC} floor "
                    f"({info['positives']} positives — reliable)", a)
        # Sub-floor but UNRELIABLE (too few positives) -> do not hide; the UI shows
        # the AUROC-weak ⚠ chip and the "not calibrated" caution instead.
    return None


def _gradcam(net, tensor, class_idx: int) -> np.ndarray:
    """224x224 attention map in [0, 1] for the given class, computed on raw logits
    of the model that owns the class."""
    from pytorch_grad_cam import GradCAM
    from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

    target_layers = [net.features[-1]]  # norm5, the final feature map
    with _infer_lock:
        with GradCAM(model=net, target_layers=target_layers) as cam:
            grayscale = cam(input_tensor=tensor, targets=[ClassifierOutputTarget(class_idx)])
    return grayscale[0]


def _cam_to_original(cam224: np.ndarray, geom: tuple) -> np.ndarray:
    """Map the 224x224 CAM back through the pad-to-square transform to the
    original image geometry."""
    import cv2

    pad_top, pad_left, h, w, size = geom
    cam_sq = cv2.resize(cam224, (size, size), interpolation=cv2.INTER_LINEAR)
    return cam_sq[pad_top:pad_top + h, pad_left:pad_left + w]


def _attention_bbox(cam: np.ndarray) -> BBox | None:
    import cv2

    if cam.max() <= 0:
        return None
    mask = (cam >= config.ATTENTION_MASK_FRAC * cam.max()).astype(np.uint8)
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return None
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return BBox(
        x=int(stats[largest, cv2.CC_STAT_LEFT]),
        y=int(stats[largest, cv2.CC_STAT_TOP]),
        width=int(stats[largest, cv2.CC_STAT_WIDTH]),
        height=int(stats[largest, cv2.CC_STAT_HEIGHT]),
    )


def _measure_attention(cam: np.ndarray, sp_row: float | None, sp_col: float | None):
    """From the attention CAM (float [0,1] in ORIGINAL-image coords) derive a
    coarse SIZE ESTIMATE of the high-attention region -- NOT a lesion measurement.

    Returns (est_max_2d_mm, est_area_mm2, attention_contour):
      * est_max_2d_mm  -- longest caliper (max Feret) diameter of the largest
        attention blob, in mm, computed in PHYSICAL space so anisotropic pixel
        spacing (row != col) is honored. None when spacing is unknown.
      * est_area_mm2   -- high-attention pixel count * pixel area, in mm^2. None
        when spacing is unknown (no fake mm on PNG/JPG).
      * attention_contour -- simplified polygon (<= config.ATTENTION_POLY_MAX_POINTS
        points) of that blob in original-image pixel coords, for a contour overlay.

    The high-attention mask is CAM >= config.ATTENTION_MASK_FRAC * max -- the same
    mask _attention_bbox uses. Cost is bounded: the caliper runs on the convex
    hull (few vertices), so the farthest-pair search is trivially small.
    """
    import cv2

    if cam.max() <= 0:
        return None, None, None
    mask = (cam >= config.ATTENTION_MASK_FRAC * cam.max()).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None, None
    largest = max(contours, key=cv2.contourArea)

    # Simplified polygon for the contour overlay; loosen epsilon until the point
    # count is capped, so the payload/overlay stays bounded regardless of shape.
    peri = cv2.arcLength(largest, True)
    eps = max(0.01 * peri, 1e-3)
    poly = cv2.approxPolyDP(largest, eps, True)
    while len(poly) > config.ATTENTION_POLY_MAX_POINTS and eps < peri:
        eps *= 1.6
        poly = cv2.approxPolyDP(largest, eps, True)
    attention_contour = [[int(p[0][0]), int(p[0][1])] for p in poly]

    if sp_row is None:
        return None, None, attention_contour  # no spacing -> no fabricated mm
    col = sp_col if sp_col else sp_row  # square-pixel fallback when col unknown

    area_mm2 = float(int(mask.sum()) * float(sp_row) * float(col))

    # Max caliper (Feret) diameter: farthest pair of convex-hull vertices, scaled
    # to mm FIRST so row/col anisotropy is correct. Hull => O(k^2), k small.
    hull = cv2.convexHull(largest).reshape(-1, 2).astype(np.float64)
    hull[:, 0] *= float(col)     # x (column) -> mm
    hull[:, 1] *= float(sp_row)  # y (row) -> mm
    max_d = 0.0
    for i in range(len(hull)):
        dx = hull[:, 0] - hull[i, 0]
        dy = hull[:, 1] - hull[i, 1]
        m = float(np.sqrt(dx * dx + dy * dy).max())
        if m > max_d:
            max_d = m
    return round(max_d, 1), round(area_mm2, 1), attention_contour


def _background_fraction(cam: np.ndarray, img8: np.ndarray) -> float:
    """Fraction of the high-attention region sitting on near-black background
    (image border / blank margin). High => the flag is likely a non-anatomical
    artifact rather than a real finding."""
    if cam.max() <= 0:
        return 0.0
    mask = cam >= config.ATTENTION_MASK_FRAC * cam.max()
    m = int(mask.sum())
    if m == 0:
        return 0.0
    bg = int(np.logical_and(mask, img8 <= config.BACKGROUND_LEVEL).sum())
    return bg / m


def _cam_cells_spanned(cam: np.ndarray, native_grid: int) -> float:
    """How many NATIVE Grad-CAM grid cells the high-attention region spans. A value
    below CAM_MIN_CELLS means the 'blob' is a single upsampled cell — the upsampler
    talking, not real structure — so it must not be outlined as a boundary."""
    if cam.max() <= 0 or native_grid <= 0:
        return 0.0
    hot = cam >= config.ATTENTION_MASK_FRAC * cam.max()
    per_cell = cam.size / float(native_grid * native_grid)
    return float(hot.sum()) / per_cell if per_cell > 0 else 0.0


def _classify_cam(cam: np.ndarray, native_grid: int) -> tuple[str, bool]:
    """Classify a Grad-CAM map -> (state, contour_ok).

    state: 'none'      -> empty/all-zero map (no localization at all)
           'diffuse'   -> attention spread over > CAM_DIFFUSE_MAX_FRAC of the image
                          (non-specific; no region to outline)
           'localized' -> a focal region of attention
    contour_ok: draw a CRISP contour only when the region is focal, spans enough
    NATIVE cells, AND the grid is fine enough (>= CONTOUR_MIN_GRID). Otherwise the
    overlay uses a soft gradient edge — a crisp line at 7x7 is a boundary the model
    cannot support.
    """
    if cam.max() <= 0:
        return "none", False
    hot = cam >= config.ATTENTION_MASK_FRAC * cam.max()
    frac = float(hot.mean())
    if frac <= 0:
        return "none", False
    if frac > config.CAM_DIFFUSE_MAX_FRAC:
        return "diffuse", False
    cells = _cam_cells_spanned(cam, native_grid)
    if cells < config.CAM_MIN_CELLS:
        # A hot blob spanning fewer than min_cells NATIVE cells is the upsampler
        # talking, not structure. At the 7x7 default, a single hot cell bilinearly
        # upsampled ~150x is exactly the hard-edged "diamond" — so render NO overlay
        # and label it non-localizing, rather than dress up an interpolation kernel.
        return "diffuse", False
    contour_ok = native_grid >= config.CONTOUR_MIN_GRID
    return "localized", contour_ok


def _heatmap_caption(state: str, label: str, native_grid: int) -> str:
    if state == "localized":
        if native_grid >= config.CONTOUR_MIN_GRID:
            return (f"Region of model attention for {label} — the outline is the "
                    f"high-attention contour, not a lesion boundary.")
        return (f"Approximate region of model attention for {label} — from a coarse "
                f"{native_grid}×{native_grid} map, shown as a soft gradient (no precise "
                f"boundary can be drawn at this resolution).")
    if state == "diffuse":
        return (f"Diffuse / non-localizing — the model's attention for {label} is "
                f"spread across the image, so no specific region is shown.")
    if state == "none":
        return (f"No attention map — the model produced no localized region for "
                f"{label} (the map was empty).")
    if state == "suppressed":
        return (f"Flag suppressed for {label} — attention was not on plausible "
                f"anatomy (see reliability note).")
    if state == "abstained":
        return "Image not scored (out-of-distribution) — no attention maps."
    if state == "error":
        return f"Attention map unavailable for {label} — localization failed."
    return ""


def _colormap():
    import cv2
    return cv2.COLORMAP_CIVIDIS if config.HEATMAP_COLORMAP == "cividis" else cv2.COLORMAP_INFERNO


def _save_overlay(img8: np.ndarray, cam: np.ndarray, bbox: BBox | None, out_path,
                  contour: list[list[int]] | None = None, draw_contour: bool = False) -> None:
    import cv2

    base = cv2.cvtColor(img8, cv2.COLOR_GRAY2BGR).astype(np.float32)
    cam = np.clip(cam, 0.0, None).astype(np.float32)

    # Floor-and-ceiling percentile normalize, NOT min-max. Min-max stretches the
    # single brightest pixel to 1.0 on every image, manufacturing a hot focal spot
    # even on a flat, uncertain map. We subtract a low-percentile FLOOR (typical
    # background attention) and divide by a high-percentile ceiling, so cold
    # regions go transparent; and when floor≈ceiling (a diffuse map with no real
    # contrast) we render nothing rather than fabricate a hotspot.
    if cam.max() > 0:
        lo = float(np.percentile(cam, config.OVERLAY_LO_PCT))
        hi = float(np.percentile(cam, config.OVERLAY_HI_PCT))
        if (hi - lo) <= config.OVERLAY_MIN_CONTRAST_FRAC * float(cam.max()):
            norm = np.zeros_like(cam)  # no localization signal -> no manufactured heat
        else:
            norm = np.clip((cam - lo) / (hi - lo), 0.0, 1.0)
    else:
        norm = cam

    # Perceptually-uniform, colour-vision-safe colormap encoding INTENSITY ONLY
    # (never pathology identity). Jet/rainbow is never used (measured higher error).
    heat = cv2.applyColorMap((norm * 255).astype(np.uint8), _colormap()).astype(np.float32)

    # Alpha PROPORTIONAL to activation: cold regions are fully transparent, so the
    # anatomy underneath stays visible instead of being buried under a whole-frame
    # purple haze. gamma>1 sharpens the falloff around the true focus.
    alpha = (np.power(norm, config.OVERLAY_ALPHA_GAMMA) * config.OVERLAY_ALPHA_MAX)[..., None]
    overlay = (base * (1.0 - alpha) + heat * alpha).astype(np.uint8)

    # Draw a CRISP contour only when the caller says the resolution supports it
    # (grid >= CONTOUR_MIN_GRID and focal). Otherwise the soft gradient above IS the
    # localization — a crisp line at 7x7 is a boundary Grad-CAM cannot support, and a
    # box both overclaims and (on a marker shortcut) neatly frames the text.
    if draw_contour and contour and len(contour) >= 3:
        pts = np.asarray(contour, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(overlay, [pts], True, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(str(out_path), overlay)


def _new_image_id() -> str:
    import secrets
    return secrets.token_hex(6)  # 12 hex chars


def _label_slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "finding"


def abstain_response(img8: np.ndarray, modality: str, source_format: str,
                     audit: dict, identifiers_removed: int = 0,
                     view_position: str | None = None) -> AnalyzeResponse:
    """Self-audit refused this input: save the image so the user sees what they
    uploaded, but do NOT score it (cheaper, fails safe)."""
    img8, _ = _cap_resolution(img8, None)
    image_id = _new_image_id()
    Image.fromarray(img8).save(config.UPLOADS_DIR / f"{image_id}.png")
    resp = AnalyzeResponse(
        image_id=image_id,
        image_url=f"/static/uploads/{image_id}.png",
        heatmap_url=None,
        top_finding=None,
        findings=[],
        normal_read=False,
        read_disposition=config.READ_DISPOSITION_NOT_NORMAL,
        read_disposition_message=config.ABSTAIN_READ_MESSAGE,
        competence="abstain",
        ood_score=audit.get("ood_score", 1.0),
        audit_reasons=audit.get("reasons", []),
        triage="routine",
        triage_reasons=[],
        modality=modality,
        source_format=source_format,
        view_position=(view_position or None),
        identifiers_removed=identifiers_removed,
        disclaimer=config.DISCLAIMER,
    )
    (config.ANALYSIS_DIR / f"{image_id}.json").write_text(
        resp.model_dump_json(), encoding="utf-8")
    return resp


def analyze_xray(img8: np.ndarray, pixel_spacing: float | None,
                 modality: str, source_format: str,
                 identifiers_removed: int = 0, audit: dict | None = None,
                 pixel_spacing_col: float | None = None,
                 view_position: str | None = None) -> AnalyzeResponse:
    _get_models()
    h0 = img8.shape[0]
    img8, pixel_spacing = _cap_resolution(img8, pixel_spacing)
    # _cap_resolution may downscale the working image; scale the (anisotropic)
    # column spacing by the same factor so mm math matches the resized pixels.
    scale = img8.shape[0] / h0 if h0 else 1.0
    if pixel_spacing_col is not None and scale:
        pixel_spacing_col = pixel_spacing_col / scale

    # Shortcut-learning defence: the MODEL is fed a copy with burned-in markers
    # ("L", "PORTABLE", timestamps) inpainted, so it cannot read the text instead
    # of the anatomy. The clinician still views the ORIGINAL img8 (saved for
    # display and used as the overlay base), so nothing is hidden from the reader.
    img8_model, n_marker_px = _mask_burned_in_markers(img8)
    if n_marker_px:
        logger.info("Inpainted %d burned-in marker pixel(s) before inference.", n_marker_px)
    tensor, geom = _preprocess(img8_model)

    # Ensemble-averaged banded confidence per label (0.5 == operating point).
    scored = _score(tensor)

    from . import label_map
    findings: list[Finding] = []
    not_assessed: list[dict] = []
    for label, (p, _owner, _idx) in scored.items():
        d = _denial(label)
        if d is not None:
            reason, auroc = d
            not_assessed.append({"label": label, "display": label_map.raw_display(label),
                                 "reason": reason, "auroc": auroc})
            continue
        cp = calibration.calibrate(label, p)  # honest P(disease); None if no map
        rel = reliability.label_reliability(label)  # FIX #3 — measured, not hardcoded
        findings.append(Finding(
            label=label, probability=round(p, 4),
            calibrated_probability=round(cp, 4) if cp is not None else None,
            calibration_state=calibration.state(label),
            reliably_measured=rel["reliable"],
            reliability_state=rel["state"],
            flagged=p >= _threshold_for(label)))  # flag still on the raw score
    findings.sort(key=lambda f: f.probability, reverse=True)
    not_assessed.sort(key=lambda x: x["display"])

    image_id = _new_image_id()
    Image.fromarray(img8).save(config.UPLOADS_DIR / f"{image_id}.png")

    # Segment chest anatomy once, to gate each finding by anatomical plausibility.
    anat = anatomy.segment(img8)

    # Per-finding localization: a Grad-CAM region + anatomy gate for each flagged
    # finding. EVERY flagged priority/emergency label is localized (so a dangerous
    # flag — e.g. Pneumothorax — is never shown without an anatomy check), then the
    # remaining latency budget is filled with the highest-confidence other findings.
    flagged = [f for f in findings if f.flagged]
    priority = sorted(
        (f for f in flagged if f.label in config.LOCALIZE_PRIORITY_LABELS),
        key=lambda f: -f.probability)
    others = sorted(
        (f for f in flagged if f.label not in config.LOCALIZE_PRIORITY_LABELS),
        key=lambda f: -f.probability)
    ordered = priority + others[:max(0, config.LOCALIZE_MAX - len(priority))]
    native_grid = config.native_cam_grid()
    loc_on = localizer.available()
    n_hires = 0
    for f in ordered:
        try:
            # Prefer the high-resolution res512 localizer (16x16 grid) for this
            # FLAGGED finding, capped at LOCALIZER_MAX_FINDINGS (priority-first);
            # fall back to the fast densenet CAM (7x7). The res512 map explains that
            # model's logit, not the ensemble number — captioned as such.
            # img8_model is the marker-masked image the classifier saw.
            grid = native_grid
            cam = (localizer.cam(img8_model, f.label)
                   if loc_on and n_hires < config.LOCALIZER_MAX_FINDINGS else None)
            from_localizer = cam is not None
            if from_localizer:
                grid = 16
                n_hires += 1
            else:
                _mean, owner, class_idx = scored[f.label]
                cam = _cam_to_original(_gradcam(owner.logit.net, tensor, class_idx), geom)

            # Reliability: if the model's attention is mostly on non-anatomical
            # background (image border / blank area), the flag is likely spurious.
            bg = _background_fraction(cam, img8)
            if bg >= config.ATTENTION_BG_SUPPRESS:
                f.flagged = False
                f.reliability_note = (
                    "Flag suppressed — the model's attention for this label fell on a "
                    "non-anatomical region (image border / blank area), so it is "
                    "unreliable.")
                f.heatmap_state = "suppressed"
                f.heatmap_caption = _heatmap_caption("suppressed", f.label, native_grid)
                continue
            if bg >= config.ATTENTION_BG_CAUTION:
                f.reliability_note = (
                    "Caution — part of the model's attention is on a non-anatomical "
                    "region; interpret this flag carefully.")

            # Anatomy gate: does the attention actually overlap the anatomy this
            # finding could arise from (heart for cardiac, lungs for lung, ...)?
            if anat is not None and cam.max() > 0:
                cam_mask = cam >= config.ATTENTION_MASK_FRAC * cam.max()
                ov = anatomy.attention_overlap(
                    cam_mask, anatomy.relevant_structures(f.label), anat)
                if ov is not None and ov < config.ANATOMY_MIN_OVERLAP:
                    # The anatomy gate can DELETE a correct finding if PSPNet
                    # mis-segments, so warn_only keeps the flag (caution only). Its
                    # false-negative rate is measured into the behaviour card.
                    if config.ANATOMY_GATE_MODE == "warn_only":
                        f.reliability_note = (
                            f"Caution — the model's attention is not on the expected "
                            f"anatomy (only {ov:.0%} overlap); the anatomy gate is in "
                            f"warn-only mode, so the flag is kept for you to judge.")
                    else:
                        f.flagged = False
                        f.reliability_note = (
                            f"Flag suppressed — the model's attention is not on the "
                            f"expected anatomy for this finding (only {ov:.0%} overlap "
                            f"with the relevant region, e.g. heart/lungs), so it is a "
                            f"likely misattribution.")
                        f.heatmap_state = "suppressed"
                        f.heatmap_caption = _heatmap_caption("suppressed", f.label, native_grid)
                        continue
                if ov is not None and ov < config.ANATOMY_CAUTION_OVERLAP and not f.reliability_note:
                    f.reliability_note = (
                        f"Caution — only {ov:.0%} of the model's attention is on the "
                        f"expected anatomy for this finding; interpret carefully.")

            # Localization state: never leave a blank/soft map ambiguous. Use the
            # grid of the model that ACTUALLY produced this CAM (16 for res512, 7 for
            # densenet) so contour eligibility reflects real resolution.
            state, contour_ok = _classify_cam(cam, grid)
            f.heatmap_state = state
            f.heatmap_caption = _heatmap_caption(state, f.label, grid)
            if from_localizer and state == "localized":
                f.heatmap_caption += " Region from the higher-resolution 16×16 localizer."

            if state != "localized":
                # 'diffuse' or 'none': there is NO specific region. Do not ship an
                # overlay URL (a whole-frame smear would masquerade as a heatmap) or
                # a size estimate (an "≈X mm" beside "no region" is a contradiction).
                # The state + caption carry the honest explanation instead.
                f.heatmap_url = None
                f.bbox = None
                f.est_max_2d_mm = None
                f.est_area_mm2 = None
                f.attention_contour = None
                f.size_note = (
                    "Diffuse / non-localizing attention — no specific region or size."
                    if state == "diffuse" else
                    "No localized region of attention — the attention map was empty.")
                continue

            f.bbox = _attention_bbox(cam)
            est_max, est_area, contour = _measure_attention(
                cam, pixel_spacing, pixel_spacing_col)
            f.est_max_2d_mm = est_max
            f.est_area_mm2 = est_area
            # Only carry a polygon when a crisp contour is actually drawn; otherwise
            # a precise outline would imply a boundary the resolution can't support.
            f.attention_contour = contour if contour_ok else None
            if est_max is not None:
                f.size_note = (
                    f"~{est_max:.0f} mm across (about {est_area:.0f} mm2 area), "
                    "estimated from the region of model attention — not a lesion "
                    "measurement; confirm with the caliper."
                )
            else:
                f.size_note = (
                    "Region of model attention — not a lesion boundary and not a "
                    "measurement. Use the caliper for any size."
                )
            fname = f"{image_id}_{_label_slug(f.label)}.png"
            _save_overlay(img8, cam, f.bbox, config.HEATMAPS_DIR / fname,
                          contour=contour, draw_contour=contour_ok)
            f.heatmap_url = f"/static/heatmaps/{fname}"
        except Exception:
            logger.exception("Grad-CAM failed for %s; leaving that finding without a region",
                             f.label)
            f.heatmap_state = "error"
            f.heatmap_caption = _heatmap_caption("error", f.label, native_grid)
            # Roll back any partial region fields set before the failure, so an
            # 'error' finding never ships a size estimate / bbox with no map.
            f.heatmap_url = None
            f.bbox = None
            f.est_max_2d_mm = None
            f.est_area_mm2 = None
            f.attention_contour = None

    # Any flagged finding we did not localize (below the latency budget) still gets
    # an explicit state, so a flagged row is NEVER left with an ambiguous blank map.
    for f in findings:
        if f.flagged and not f.heatmap_state:
            f.heatmap_state = "not_localized"
            f.heatmap_caption = (
                f"Flagged by model score; no attention map was computed for {f.label}. "
                f"Localization runs on the highest-priority findings first to keep "
                f"latency bounded — request this one to localize it.")

    # Back-compat top-level fields: the highest-confidence flagged finding.
    top = next((f for f in findings if f.flagged), None)
    heatmap_url = None
    if top and top.heatmap_url:
        heatmap_url = top.heatmap_url
    else:
        heatmap_url = next((f.heatmap_url for f in ordered if f.heatmap_url), None)

    level, reasons = triage.assess(findings)
    # Confidence -> action: attach an explicit disposition to each FINAL flagged
    # finding (after anatomy/background suppression), so the UI is not just a number.
    triage.apply_dispositions(findings)

    resp = AnalyzeResponse(
        image_id=image_id,
        image_url=f"/static/uploads/{image_id}.png",
        heatmap_url=heatmap_url,
        top_finding=top.label if top else None,
        findings=findings,
        # FIX #1 — explicit non-normal contract on EVERY analysis. `normal_read` is
        # always False; the message matters most on a ZERO-flag result, where the
        # absence of a flag must not be read as "normal".
        normal_read=False,
        read_disposition=config.READ_DISPOSITION_NOT_NORMAL,
        read_disposition_message=config.NORMAL_READ_MESSAGE,
        triage=level,
        triage_reasons=reasons,
        competence=(audit or {}).get("competence", "read"),
        ood_score=(audit or {}).get("ood_score", 0.0),
        audit_reasons=(audit or {}).get("reasons", []),
        pixel_spacing_mm=pixel_spacing,
        pixel_spacing_col_mm=pixel_spacing_col,
        modality=modality,
        source_format=source_format,
        view_position=(view_position or None),
        identifiers_removed=identifiers_removed,
        not_assessed=not_assessed,
        disclaimer=config.DISCLAIMER,
    )

    # Persist to the PRIVATE analysis dir (not a StaticFiles mount) so full results
    # are not world-readable by guessing an id.
    (config.ANALYSIS_DIR / f"{image_id}.json").write_text(
        resp.model_dump_json(), encoding="utf-8")
    return resp


def predict_probs(img8: np.ndarray, mask_markers: bool = True) -> dict[str, float]:
    """Ensemble-averaged banded per-pathology confidence for a uint8 image, no file
    writes. Used by the validation harness so it measures exactly what /analyze
    scores — hence marker masking is ON by default here too. The marker-ablation
    tool passes mask_markers=False to score the raw image for comparison."""
    _get_models()
    img8, _ = _cap_resolution(img8, None)
    if mask_markers:
        img8, _ = _mask_burned_in_markers(img8)
    tensor, _ = _preprocess(img8)
    scored = _score(tensor)
    return {label: mean for label, (mean, _o, _i) in scored.items()}


def localize(img8: np.ndarray, label: str) -> BBox | None:
    """Grad-CAM attention bbox (original-image coords) for a pathology, no file
    writes. Sourced from the ensemble model that scores the label highest."""
    _get_models()
    img8, _ = _cap_resolution(img8, None)
    img8, _ = _mask_burned_in_markers(img8)
    tensor, geom = _preprocess(img8)
    scored = _score(tensor)
    if label not in scored:
        return None
    _mean, owner, idx = scored[label]
    cam = _cam_to_original(_gradcam(owner.logit.net, tensor, idx), geom)
    return _attention_bbox(cam)


def attention_peak(img8: np.ndarray, label: str) -> tuple[int, int] | None:
    """(x, y) pixel of PEAK Grad-CAM attention for a label in ORIGINAL-image
    coordinates, or None if the label isn't scored / the map is empty. Marker-
    masked exactly like production. Used by the pointing-game localization metric
    (is the model's hottest point inside the expert's box?)."""
    _get_models()
    img8, _ = _cap_resolution(img8, None)
    img8, _ = _mask_burned_in_markers(img8)
    # Use the res512 localizer's 16x16 CAM when enabled (this is how the pointing
    # game measures whether res512 beats the 7x7 densenet ceiling); else densenet.
    cam = localizer.cam(img8, label) if localizer.available() else None
    if cam is None:
        tensor, geom = _preprocess(img8)
        scored = _score(tensor)
        if label not in scored:
            return None
        _mean, owner, idx = scored[label]
        cam = _cam_to_original(_gradcam(owner.logit.net, tensor, idx), geom)
    if cam.max() <= 0:
        return None
    y, x = np.unravel_index(int(np.argmax(cam)), cam.shape)
    return int(x), int(y)


def attention_maps(img8: np.ndarray, labels: list[str]) -> dict[str, np.ndarray]:
    """{label: Grad-CAM (float, ORIGINAL-image coords)} for several labels in ONE
    preprocessing pass, marker-masked exactly like production. Labels not scored by
    the model are omitted. Used by the cross-pathology divergence diagnostic (are
    per-class CAMs class-specific, or collapsing onto one salient region?)."""
    _get_models()
    img8, _ = _cap_resolution(img8, None)
    img8, _ = _mask_burned_in_markers(img8)
    tensor, geom = _preprocess(img8)
    scored = _score(tensor)
    out: dict[str, np.ndarray] = {}
    for lb in labels:
        if lb not in scored:
            continue
        _mean, owner, idx = scored[lb]
        out[lb] = _cam_to_original(_gradcam(owner.logit.net, tensor, idx), geom)
    return out


def load_saved(image_id: str) -> AnalyzeResponse | None:
    if not _ID_RE.match(image_id or ""):
        return None
    path = config.ANALYSIS_DIR / f"{image_id}.json"
    if not path.exists():
        return None
    return AnalyzeResponse(**json.loads(path.read_text(encoding="utf-8")))
