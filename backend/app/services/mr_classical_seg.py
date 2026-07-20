"""SHIP-NOW classical MR anatomy-envelope / intensity-band labeler.

This is the always-available, weight-free MR provider for the anatomy-overlay path.
It labels a coarse in-tissue body mask and splits its signal into a few generic
intensity BANDS. It is NOT disease detection: it never characterizes, detects, or
excludes any abnormality, and it makes NO tissue-type claim.

WHY MR is special (and why this file is deliberately conservative):
  MR intensity is ARBITRARY (a.u.). A voxel value is not calibrated to any physical
  quantity the way a CT Hounsfield unit is — it depends on the sequence, coil, scaler,
  and vendor. So this module NEVER emits HU, NEVER names a tissue type (no "fat",
  "white matter", "CSF" — those imply a calibration that does not exist), and reports
  every band with an intensity_unit of 'a.u.'. Region labels come from a CLOSED
  vocabulary of pure signal/anatomy-envelope nouns (see _LABELS) — never a pathology
  word, never a calibrated-tissue word.

Method (fully deterministic — fixed percentiles + Otsu, NO RNG => byte-identical
output across runs):
  1. Robust-normalize the volume by its 99th percentile (clip to [0, 1]).
  2. Build a coarse "in-tissue" body mask: Otsu threshold -> largest connected
     component -> binary closing (padded so a body touching the array border is not
     nibbled) -> fill holes. This is a rough skull-strip / body mask, nothing more.
  3. Within that mask, split the normalized signal into 3 deterministic bands at the
     33rd / 66th percentiles: low- / mid- / high-signal region.

Output partition (each voxel carries exactly ONE structure_id, per the mask contract):
  1  low-signal region   #6f7b8a
  2  mid-signal region   #57c98b
  3  high-signal region  #ffd24d
The three bands TILE the in-tissue mask, so they already ARE the "imaged tissue
envelope". A separate painted envelope structure would overlap the bands and break
the one-id-per-voxel invariant of the indexed label PNG, so the envelope is kept as
an OPTIONAL documented alternative (ENVELOPE_COLOR / EMIT_ENVELOPE_ONLY) rather than
a fourth overlapping layer. Colors are CATEGORICAL identity swatches — never an
alarm/hot ramp.

Provider contract (called by the lead's segmentation.py):
  label_mr(vol, spacing_mm) -> (regions, label_vol)
    vol         : np.ndarray (Z, H, W) int16, arbitrary a.u.
    spacing_mm  : (row_mm, col_mm, z_mm); ANY element may be None
    regions     : list[dict] (Region shape from the pinned contract)
    label_vol   : np.ndarray (Z, H, W) uint8, voxel == its region's structure_id
                  (0 = unlabeled / background)
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from scipy import ndimage
from skimage.filters import threshold_otsu

from .. import config

# --- Provenance (mandated verbatim by the pinned contract) ------------------
METHOD = "mr-intensity-cluster-v1"
MODEL = "classical-mr-intensity"
LICENSE = "no-model (scipy/numpy/scikit-image BSD-3-Clause)"
INTENSITY_UNIT = "a.u."

# Closed label vocabulary — pure signal/anatomy-envelope nouns. NEVER a pathology
# word and NEVER a calibrated-tissue-type word (MR intensity is arbitrary).
_LABELS = {
    1: "low-signal region",
    2: "mid-signal region",
    3: "high-signal region",
}
# Categorical identity colors (NOT an alarm/hot ramp): grey / green / amber.
_COLORS = {
    1: "#6f7b8a",
    2: "#57c98b",
    3: "#ffd24d",
}
# Optional, documented alternative single-structure envelope (NOT painted by default;
# it would overlap the band partition). Kept so the seam is discoverable.
ENVELOPE_COLOR = "#4da3ff"
ENVELOPE_LABEL = "imaged tissue envelope"
EMIT_ENVELOPE_ONLY = False  # if True, emit ONE envelope region instead of the 3 bands

# Band split points (percentiles of in-tissue signal). Fixed => deterministic.
_BAND_PCTS = (33.0, 66.0)
# 99th-percentile robust-normalization ceiling.
_NORM_PCT = 99.0
# Morphology strength for the coarse body mask.
_CLOSE_ITERS = 2


def available() -> bool:
    """The classical MR provider needs no weights and is always available."""
    return True


def _is_pos(x) -> bool:
    """True only for a real, finite, strictly-positive spacing value."""
    return x is not None and np.isfinite(x) and x > 0


def _largest_component(mask: np.ndarray, structure: np.ndarray) -> np.ndarray:
    """Keep only the single largest connected component of a boolean mask."""
    lab, n = ndimage.label(mask, structure=structure)
    if n <= 1:
        return mask
    # counts[0] is background; pick the largest foreground label deterministically.
    counts = np.bincount(lab.ravel())
    counts[0] = 0
    keep = int(counts.argmax())
    return lab == keep


def _closing_padded(mask: np.ndarray, structure: np.ndarray, iters: int) -> np.ndarray:
    """Binary closing that does NOT nibble a body touching the array border.

    scipy's binary_closing erodes from the array edge (border_value=0), so a mask that
    reaches the volume border (an MR body almost always spans every slice) would lose
    real voxels. Padding by `iters` moves that zero-border out of the real data, making
    the closing extensive (result ⊇ input) as a closing must be."""
    p = np.pad(mask, iters, mode="constant", constant_values=False)
    c = ndimage.binary_closing(p, structure=structure, iterations=iters)
    sl = tuple(slice(iters, iters + s) for s in mask.shape)
    return c[sl]


def _in_tissue_mask(norm: np.ndarray, structure: np.ndarray) -> np.ndarray:
    """Coarse skull-strip / body mask: Otsu -> largest CC -> closing -> fill holes."""
    finite = norm[np.isfinite(norm)]
    if finite.size == 0 or float(finite.min()) == float(finite.max()):
        # Uniform / empty volume — Otsu is undefined; there is no foreground.
        return np.zeros(norm.shape, dtype=bool)
    try:
        thr = float(threshold_otsu(norm))
    except Exception:
        return np.zeros(norm.shape, dtype=bool)
    fg = norm > thr
    if not fg.any():
        return np.zeros(norm.shape, dtype=bool)
    fg = _largest_component(fg, structure)
    fg = _closing_padded(fg, structure, _CLOSE_ITERS)
    fg = ndimage.binary_fill_holes(fg)
    return fg


def _measure(mask: np.ndarray, vol_f: np.ndarray, spacing_mm, structure) -> dict:
    """Geometric measurements for one band mask (never a disease measurement)."""
    row_mm, col_mm, z_mm = spacing_mm
    voxel_count = int(mask.sum())
    in_plane_known = _is_pos(row_mm) and _is_pos(col_mm)
    volume_known = in_plane_known and _is_pos(z_mm)
    area_mm2 = float(voxel_count * row_mm * col_mm) if in_plane_known else None
    volume_ml = (
        float(voxel_count * row_mm * col_mm * z_mm / 1000.0) if volume_known else None
    )
    _, n_components = ndimage.label(mask, structure=structure)
    return {
        "voxel_count": voxel_count,
        "area_mm2": area_mm2,
        "volume_ml": volume_ml,
        "mean_intensity": float(vol_f[mask].mean()),
        "n_components": int(n_components),
    }


def _region(structure_id: int, label: str, color: str, meas: dict) -> dict:
    """Assemble one Region dict in the pinned contract shape (NO extra keys)."""
    return {
        "structure_id": structure_id,
        "label": label,
        "color": color,
        "volume_ml": meas["volume_ml"],
        "voxel_count": meas["voxel_count"],
        "area_mm2": meas["area_mm2"],
        "mean_intensity": meas["mean_intensity"],
        "intensity_unit": INTENSITY_UNIT,
        "hu_range": None,               # MR signal is arbitrary; never an HU band
        "n_components": meas["n_components"],
        "method": METHOD,
        "model": MODEL,
        "license": LICENSE,
    }


def label_mr(vol: np.ndarray, spacing_mm) -> tuple[list[dict], np.ndarray]:
    """Deterministically label a coarse MR in-tissue mask into signal bands.

    See the module docstring for the full method. Returns (regions, label_vol) per the
    pinned provider contract; NEVER emits HU, a tissue-type name, or any diagnosis-
    shaped value. Enforces the SEGMENT_MAX_STRUCTURES cap.
    """
    vol = np.asarray(vol)
    if vol.ndim == 2:  # tolerate a single slice; contract is (Z, H, W)
        vol = vol[None, ...]
    if vol.ndim != 3:
        raise ValueError(f"label_mr expects a (Z, H, W) volume, got shape {vol.shape}")

    label_vol = np.zeros(vol.shape, dtype=np.uint8)
    vol_f = vol.astype(np.float32, copy=False)

    # Normalize spacing to a 3-tuple even if a shorter/None tuple slips through.
    spacing_mm = tuple(spacing_mm) if spacing_mm is not None else (None, None, None)
    if len(spacing_mm) != 3:
        spacing_mm = (spacing_mm + (None, None, None))[:3]

    # (1) Robust normalization by the 99th percentile.
    p99 = float(np.percentile(vol_f, _NORM_PCT))
    if not np.isfinite(p99) or p99 <= 0:
        return [], label_vol  # degenerate (all-zero / non-finite) volume
    norm = np.clip(vol_f / p99, 0.0, 1.0)

    # (2) Coarse in-tissue body mask.
    structure = ndimage.generate_binary_structure(3, 1)
    fg = _in_tissue_mask(norm, structure)
    if not fg.any():
        return [], label_vol

    # Optional single-structure envelope mode (kept for the seam; off by default).
    if EMIT_ENVELOPE_ONLY:
        label_vol[fg] = 1
        meas = _measure(fg, vol_f, spacing_mm, structure)
        return [_region(1, ENVELOPE_LABEL, ENVELOPE_COLOR, meas)], label_vol

    # (3) Split the in-tissue signal into 3 deterministic percentile bands.
    fg_vals = norm[fg]
    lo_thr, hi_thr = (float(v) for v in np.percentile(fg_vals, list(_BAND_PCTS)))
    band_masks = {
        1: fg & (norm <= lo_thr),
        2: fg & (norm > lo_thr) & (norm <= hi_thr),
        3: fg & (norm > hi_thr),
    }

    regions: list[dict] = []
    for sid in (1, 2, 3):
        if len(regions) >= config.SEGMENT_MAX_STRUCTURES:
            break
        mask = band_masks[sid]
        if not mask.any():
            continue  # empty band (e.g. flat signal) — skip; keep ids stable
        label_vol[mask] = sid
        meas = _measure(mask, vol_f, spacing_mm, structure)
        regions.append(_region(sid, _LABELS[sid], _COLORS[sid], meas))

    return regions, label_vol


# Two-sentence provenance note (for logs / the router's `method`/`detail` line).
NOTE = (
    "Classical MR labeler: robust 99th-percentile normalization, an Otsu + largest-"
    "component + closing + fill-holes in-tissue body mask, then a deterministic split "
    "of that mask's signal into low/mid/high bands at the 33rd/66th percentiles. "
    "MR intensity is arbitrary (a.u.) so no Hounsfield value or tissue-type name is "
    "ever emitted — these are geometric anatomy-envelope regions for overlay only, "
    "never disease detection."
)
