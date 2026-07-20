"""Deterministic CT tissue labeling by Hounsfield-Unit threshold — SHIP-NOW baseline.

This module performs classical, weight-free ANATOMY/TISSUE labeling of a CT volume
by binning voxels into fixed, physically-motivated HU bands (air/lung/fat/soft-
tissue/mixed/trabecular-bone/cortical-bone). It is:

  * DETERMINISTIC — fixed thresholds and morphology params, no RNG anywhere, so the
    output is byte-identical across runs for identical input.
  * WEIGHT-FREE — pure numpy + scipy.ndimage (both BSD-3-Clause). No model, no
    network, no training data. CPU-instant.

It is NOT disease detection. The HU bands label the DENSITY of tissue present; they
do not detect, characterize, or exclude any disease, injury, or abnormality, and the
per-region numbers are GEOMETRIC measurements (voxel counts, volumes, mean HU), never
scores or probabilities. Boundaries are approximate and frequently wrong at partial-
volume interfaces — a qualified reader must verify every region before any use.

Provider contract (called by services/segmentation.py):
    label_tissue(hu, spacing_mm, *, is_ct=True) -> (regions, label_vol)
"""
import numpy as np
import scipy.ndimage as ndi

from .. import config

# --- Fixed algorithm parameters (never RNG; changing these changes the version) ---
METHOD = "hu-threshold-v1"
MODEL = "classical-hu-threshold"
LICENSE = "no-model (scipy/numpy BSD-3-Clause)"
INTENSITY_UNIT = "HU"

# A connected component smaller than a 3x3x3 neighbourhood (27 voxels) is speckle,
# not anatomy — dropped after morphological cleanup.
MIN_COMPONENT_VOX = 27

# Conventional 12-bit CT ceiling (HU range is nominally -1024..3071). Used only as
# the REPORTED upper bound of the open-ended cortical-bone band; the band's MASK is
# `hu >= 600` with no upper cut, so metal/contrast above 3071 is still labelled bone.
_HU_CEIL = 3071.0

# Disjoint, half-open HU bands -> structure_id / anatomy label / categorical color.
# Together they tile [-800, +inf); HU < -800 is air and stays background id 0 (NOT a
# region). `intervals` is a tuple of half-open [lo, hi) ranges (hi None => open-ended).
# `hu_range` is the [lo, hi] pair reported on the region (None where the band is not a
# single contiguous interval, i.e. the two-part "mixed / partial-volume" band).
_BANDS = (
    {"id": 1, "key": "lung", "label": "lung field (aerated, -800..-400 HU)",
     "color": "#4da3ff", "intervals": ((-800, -400),), "hu_range": [-800.0, -400.0]},
    {"id": 2, "key": "fat", "label": "fat-density tissue (-120..-40 HU)",
     "color": "#ffd24d", "intervals": ((-120, -40),), "hu_range": [-120.0, -40.0]},
    {"id": 3, "key": "soft_tissue", "label": "soft tissue / muscle (-40..80 HU)",
     "color": "#e8836b", "intervals": ((-40, 80),), "hu_range": [-40.0, 80.0]},
    {"id": 4, "key": "mixed", "label": "mixed / partial-volume",
     "color": "#9aa0a6", "intervals": ((-400, -120), (80, 150)), "hu_range": None},
    {"id": 5, "key": "trabecular_bone", "label": "trabecular bone (150..600 HU)",
     "color": "#b98cff", "intervals": ((150, 600),), "hu_range": [150.0, 600.0]},
    {"id": 6, "key": "cortical_bone", "label": "cortical bone (>=600 HU)",
     "color": "#f2f2f2", "intervals": ((600, None),), "hu_range": [600.0, _HU_CEIL]},
)


def _band_mask(hu: np.ndarray, intervals) -> np.ndarray:
    """Boolean mask = union of the band's half-open [lo, hi) HU intervals."""
    mask = np.zeros(hu.shape, dtype=bool)
    for lo, hi in intervals:
        part = hu >= lo
        if hi is not None:
            part &= hu < hi
        mask |= part
    return mask


def label_tissue(hu, spacing_mm, *, is_ct=True):
    """Deterministically label CT tissue by HU band.

    Args:
        hu: np.ndarray (Z, H, W) int16 — Hounsfield Units.
        spacing_mm: (row_mm, col_mm, z_mm); ANY element may be None.
        is_ct: HARD GATE — must be True (MR has no HU).

    Returns:
        (regions, label_vol) where regions is list[dict] (Region shape) and label_vol
        is np.ndarray (Z, H, W) uint8, each voxel = its region's structure_id
        (0 = unlabeled / air / dropped speckle).
    """
    if not is_ct:
        raise ValueError(
            "label_tissue is a CT-only HU labeler; MR volumes have no Hounsfield "
            "Units (use label_mr for MR). Refusing to run on non-CT input.")

    hu = np.asarray(hu)
    if hu.ndim != 3:
        raise ValueError(f"expected a 3D (Z, H, W) volume, got shape {hu.shape!r}")

    row_mm, col_mm, z_mm = spacing_mm
    in_plane_ok = row_mm is not None and col_mm is not None
    voxel_vol_ok = in_plane_ok and z_mm is not None
    voxel_area_mm2 = (float(row_mm) * float(col_mm)) if in_plane_ok else None
    voxel_vol_mm3 = (
        float(row_mm) * float(col_mm) * float(z_mm)) if voxel_vol_ok else None

    struct = ndi.generate_binary_structure(3, 1)
    label_vol = np.zeros(hu.shape, dtype=np.uint8)
    max_structures = int(config.SEGMENT_MAX_STRUCTURES)

    # --- Phase 1: paint label_vol from each band's cleaned mask. -------------
    # Despeckle (opening) + smooth (closing) ONLY — deliberately NO fill_holes: a
    # "hole" inside a density band is ANOTHER tissue (bone inside soft tissue, air
    # inside lung), not noise, so filling it would absorb a different tissue's voxels
    # and corrupt this band's mean HU. Bands are disjoint in HU; the only overlaps
    # come from closing, where the higher-id band wins the label_vol assignment.
    painted_bands = []
    for band in _BANDS:
        raw = _band_mask(hu, band["intervals"])
        if not raw.any():
            continue
        cleaned = ndi.binary_closing(ndi.binary_opening(raw, structure=struct), structure=struct)
        if not cleaned.any():
            continue
        labeled, _ = ndi.label(cleaned, structure=struct)
        counts = np.bincount(labeled.ravel())
        counts[0] = 0  # background is never a kept component
        keep = counts >= MIN_COMPONENT_VOX
        final_mask = keep[labeled]
        if not final_mask.any():
            continue
        label_vol[final_mask] = band["id"]
        painted_bands.append(band)

    # --- Phase 2: stats from the FINAL label_vol, so every voxel counts for exactly
    # ONE region (the overlay mask and the reported numbers can never disagree, and a
    # band fully overwritten by a higher-id band drops out). ------------------
    regions: list[dict] = []
    for band in painted_bands:
        if len(regions) >= max_structures:
            break  # enforce the structure cap (bands processed in id order)
        mask = label_vol == band["id"]
        voxel_count = int(mask.sum())
        if voxel_count == 0:
            continue
        _lab, n_components = ndi.label(mask, structure=struct)
        volume_ml = (voxel_count * voxel_vol_mm3 / 1000.0) if voxel_vol_ok else None
        area_mm2 = (voxel_count * voxel_area_mm2) if voxel_area_mm2 is not None else None
        regions.append({
            "structure_id": band["id"],
            "label": band["label"],
            "color": band["color"],
            "volume_ml": volume_ml,
            "voxel_count": voxel_count,
            "area_mm2": area_mm2,
            "mean_intensity": float(hu[mask].mean()),
            "intensity_unit": INTENSITY_UNIT,
            "hu_range": (list(band["hu_range"]) if band["hu_range"] is not None else None),
            "n_components": int(n_components),
            "method": METHOD,
            "model": MODEL,
            "license": LICENSE,
        })

    return regions, label_vol
