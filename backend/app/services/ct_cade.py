"""Classical, deterministic CT CADe — disease-CANDIDATE detection (RESEARCH, unvalidated).

These are transparent, weight-free heuristics (numpy + scipy) that surface CANDIDATE
regions for a radiologist to confirm. They are NOT validated detectors: they will miss
real disease and flag normal anatomy. The RESEARCH framing + disclaimers in the schema
and router are what keep this defensible (see models/detect.py, routers/detect.py).

Detectors:
  * lung nodule  — compact soft-tissue-density blobs inside a lung mask (vessels and
    the chest wall are rejected by size/compactness/elongation).
  * hyperdensity — compact hyperdense regions (acute blood ~50-90 HU / calcification)
    inside the body, away from bone. A generic "look here" candidate.

Everything is deterministic (fixed thresholds, no RNG) so the output is byte-identical
across runs; scores are detector confidence in [0,1], NOT probabilities of disease.
"""
import numpy as np
import scipy.ndimage as ndi

from .. import config

# --- Lung nodule detector parameters (fixed) --------------------------------
_LUNG_HU_MAX = -400          # air/lung threshold
_NODULE_HU_LO = -100         # solid/part-solid nodule density band
_NODULE_HU_HI = 300
_NODULE_D_MIN_MM = 3.0
_NODULE_D_MAX_MM = 30.0
# --- Hyperdensity detector parameters ---------------------------------------
_HYPER_HU_LO = 50
_HYPER_HU_HI = 100           # acute blood band (calcification > 100 is scored lower)
_HYPER_D_MIN_MM = 4.0
_HYPER_D_MAX_MM = 60.0

LICENSE = "no-model (scipy/numpy BSD-3-Clause)"


def _equiv_diameter_mm(voxels: int, voxel_mm3: float | None) -> float | None:
    if not voxel_mm3:
        return None
    vol_mm3 = voxels * voxel_mm3
    return 2.0 * (3.0 * vol_mm3 / (4.0 * np.pi)) ** (1.0 / 3.0)


def _voxel_mm3(spacing_mm):
    r, c, z = spacing_mm
    if r and c and z:
        return float(r) * float(c) * float(z)
    return None


def _lung_mask(hu: np.ndarray) -> np.ndarray:
    """Internal air = lungs (+ airways/bowel gas): air voxels NOT connected to the
    volume border (which is the outside-body air)."""
    air = hu < _LUNG_HU_MAX
    lbl, n = ndi.label(air)
    if n == 0:
        return np.zeros(hu.shape, dtype=bool)
    # Outside-body air always touches the IN-PLANE border (the body is centred in each
    # slice). Use only the in-plane edges (y/x faces), NOT the z-faces, so lungs that
    # legitimately reach the first/last slice of a tightly-cropped volume are kept.
    border = set(np.unique(np.concatenate([
        lbl[:, 0, :].ravel(), lbl[:, -1, :].ravel(),
        lbl[:, :, 0].ravel(), lbl[:, :, -1].ravel(),
    ])))
    border.discard(0)
    keep = np.ones(n + 1, dtype=bool)
    keep[0] = False
    for b in border:
        keep[b] = False
    internal = keep[lbl]
    internal = ndi.binary_closing(internal, iterations=1)
    return internal


def _component_candidates(mask, hu, spacing_mm, *, d_min, d_max, kind, label,
                          model, extent_min=0.35, elong_max=3.5, score_fn=None):
    """Connected components of `mask` -> candidate dicts, filtered by size / compactness
    / elongation (rejects vessels and sheets)."""
    voxel_mm3 = _voxel_mm3(spacing_mm)
    lbl, n = ndi.label(mask)
    if n == 0:
        return []
    out = []
    objs = ndi.find_objects(lbl)
    for i in range(1, n + 1):
        sl = objs[i - 1]
        if sl is None:
            continue
        comp = lbl[sl] == i
        voxels = int(comp.sum())
        d = _equiv_diameter_mm(voxels, voxel_mm3)
        if d is not None and not (d_min <= d <= d_max):
            continue
        if d is None and not (10 <= voxels <= 200000):  # px fallback when spacing absent
            continue
        # Bounding box in (z, y, x)
        zdim = sl[0].stop - sl[0].start
        ydim = sl[1].stop - sl[1].start
        xdim = sl[2].stop - sl[2].start
        bbox_vox = max(zdim * ydim * xdim, 1)
        extent = voxels / bbox_vox                         # compact blob -> high
        # Elongation in MILLIMETRES (not voxels) — else on thick-slice CT a spherical
        # nodule reads as elongated (z-dim in fat slices) and is wrongly dropped.
        row_mm, col_mm, z_mm = spacing_mm
        if row_mm and col_mm and z_mm:
            mdims = sorted([zdim * float(z_mm), ydim * float(row_mm), xdim * float(col_mm)])
        else:
            mdims = sorted([float(zdim), float(ydim), float(xdim)])
        elong = mdims[-1] / max(mdims[0], 1e-6)            # vessel/sheet -> high
        if extent < extent_min or elong > elong_max:
            continue
        zc = int((sl[0].start + sl[0].stop) // 2)
        yc = int((sl[1].start + sl[1].stop) // 2)
        xc = int((sl[2].start + sl[2].stop) // 2)
        mean_hu = float(hu[sl][comp].mean())
        base = min(1.0, extent) * min(1.0, 1.5 / max(elong, 1.0))
        score = float(min(1.0, max(0.0, score_fn(d, mean_hu, base) if score_fn else base)))
        out.append({
            "label": label, "kind": kind, "score": round(score, 3),
            "region": {"slice_index": zc, "bbox": [int(sl[2].start), int(sl[1].start),
                                                    int(xdim), int(ydim)],
                       "centroid": [xc, yc]},
            "est_max_mm": round(d, 1) if d is not None else None,
            "mean_hu": round(mean_hu, 1),
            "model": model, "license": LICENSE,
        })
    return out


def detect_lung_nodules(hu, spacing_mm):
    lungs = _lung_mask(hu)
    if lungs.sum() < 500:                                   # no real lung field -> skip
        return []
    # The lung ZONE = the lung air WITH its internal non-air islands filled in, so a
    # nodule (a solid "hole" inside the lung air) is inside the search region. Dilating
    # then also captures juxtapleural nodules on the lung margin.
    lung_zone = ndi.binary_fill_holes(lungs)
    search = ndi.binary_dilation(lung_zone, iterations=2)
    solid = (hu >= _NODULE_HU_LO) & (hu <= _NODULE_HU_HI) & search
    solid = ndi.binary_opening(solid, iterations=1)         # despeckle

    def score(d, mean_hu, base):
        # peak plausibility around ~8 mm; solid density boosts.
        if d is None:
            return base * 0.6
        size_term = np.exp(-((d - 8.0) ** 2) / (2 * 7.0 ** 2))
        return base * (0.5 + 0.5 * size_term)

    return _component_candidates(
        solid, hu, spacing_mm, d_min=_NODULE_D_MIN_MM, d_max=_NODULE_D_MAX_MM,
        kind="pulmonary nodule", label="Candidate pulmonary nodule",
        model="classical-lung-nodule-cade", extent_min=0.4, elong_max=3.0, score_fn=score)


def detect_hyperdensities(hu, spacing_mm):
    # Hyperdense band = acute blood ~50-90 HU. Cap the band at 300 HU and subtract a
    # DILATED bone mask so vertebrae/sternum/ribs (and their partial-volume rims) are
    # not emitted as haemorrhage candidates (calcification has its own detector).
    body = ndi.binary_erosion(hu > -300, iterations=1)
    bone = ndi.binary_dilation(hu >= 150, iterations=1)
    hyper = (hu >= _HYPER_HU_LO) & (hu <= 300) & body & ~bone
    hyper = ndi.binary_opening(hyper, iterations=1)

    def score(d, mean_hu, base):
        # blood band (50-90) most suggestive; pure calcium (>150) less so.
        band = 1.0 if _HYPER_HU_LO <= mean_hu <= _HYPER_HU_HI else 0.5
        return base * band

    return _component_candidates(
        hyper, hu, spacing_mm, d_min=_HYPER_D_MIN_MM, d_max=_HYPER_D_MAX_MM,
        kind="hyperdensity (e.g. haemorrhage/calcification)",
        label="Candidate hyperdensity", model="classical-hyperdensity-cade",
        extent_min=0.35, elong_max=4.0, score_fn=score)


def _large_region_candidates(mask, hu, spacing_mm, *, min_ml, min_vox, kind, label,
                             model, score_fn):
    """Candidates for LARGE, non-compact collections (effusion/air) — size-gated, no
    compactness requirement (a fluid sheet or air crescent is not a blob)."""
    voxel_mm3 = _voxel_mm3(spacing_mm)
    lbl, n = ndi.label(mask)
    if n == 0:
        return []
    counts = np.bincount(lbl.ravel())
    counts[0] = 0
    objs = ndi.find_objects(lbl)
    out = []
    for i in range(1, n + 1):
        vox = int(counts[i])
        vol_ml = (vox * voxel_mm3 / 1000.0) if voxel_mm3 else None
        if voxel_mm3 is not None:
            if vol_ml < min_ml:
                continue
        elif vox < min_vox:
            continue
        sl = objs[i - 1]
        comp = lbl[sl] == i
        zc = int((sl[0].start + sl[0].stop) // 2)
        yc = int((sl[1].start + sl[1].stop) // 2)
        xc = int((sl[2].start + sl[2].stop) // 2)
        ydim, xdim = sl[1].stop - sl[1].start, sl[2].stop - sl[2].start
        mean_hu = float(hu[sl][comp].mean())
        score = float(min(1.0, max(0.0, score_fn(vol_ml, mean_hu, vox))))
        out.append({
            "label": label, "kind": kind, "score": round(score, 3),
            "region": {"slice_index": zc, "bbox": [int(sl[2].start), int(sl[1].start), int(xdim), int(ydim)],
                       "centroid": [xc, yc]},
            "est_max_mm": round(_equiv_diameter_mm(vox, voxel_mm3), 1) if voxel_mm3 else None,
            "est_volume_ml": round(vol_ml, 1) if vol_ml is not None else None,
            "mean_hu": round(mean_hu, 1), "model": model, "license": LICENSE,
        })
    return out


def detect_calcifications(hu, spacing_mm):
    # Compact very-high-HU blobs that are NOT part of the skeleton (large bone
    # structures), i.e. vascular / soft-tissue calcification candidates.
    bone = hu >= 300
    lbl, n = ndi.label(bone)
    if n:
        counts = np.bincount(lbl.ravel())
        counts[0] = 0
        skeleton = np.isin(lbl, np.where(counts > 400)[0])   # large bones = skeleton
        skeleton = ndi.binary_dilation(skeleton, iterations=2)
    else:
        skeleton = np.zeros(hu.shape, dtype=bool)
    calc = (hu >= 150) & ~skeleton
    calc = ndi.binary_opening(calc, iterations=1)

    def score(d, mean_hu, base):
        return base * (0.7 + 0.3 * min(1.0, (mean_hu - 150) / 250.0))

    return _component_candidates(
        calc, hu, spacing_mm, d_min=2.0, d_max=25.0, kind="calcification",
        label="Candidate calcification", model="classical-calcification-cade",
        extent_min=0.3, elong_max=4.0, score_fn=score)


def detect_effusion(hu, spacing_mm):
    lungs = _lung_mask(hu)
    if lungs.sum() < 500:
        return []
    # Thoracic search zone = a generous dilation of the lung footprint (a large effusion
    # displaces the lung, so the pleural fluid can sit several mm from aerated lung).
    thorax = ndi.binary_dilation(ndi.binary_fill_holes(lungs), iterations=6)
    body = ndi.binary_erosion(hu > -200, iterations=1)
    fluid = (hu >= -20) & (hu <= 25) & thorax & body        # simple fluid density band
    fluid = ndi.binary_opening(fluid, iterations=1)

    def score(vol_ml, mean_hu, vox):
        if vol_ml is None:
            return 0.5
        return 0.45 + min(0.45, vol_ml / 150.0)             # bigger collection -> higher

    return _large_region_candidates(
        fluid, hu, spacing_mm, min_ml=5.0, min_vox=400,
        kind="pleural fluid collection", label="Candidate pleural fluid collection",
        model="classical-effusion-cade", score_fn=score)


def detect_pneumothorax(hu, spacing_mm):
    # PURE air (< -960) inside the thoracic cavity. Aerated lung parenchyma averages
    # ~-850 (vessels raise it), so this threshold mostly excludes normal lung and
    # catches pure-air pockets. Honest caveat: classical air-only detection is weak
    # (large airways / bowel gas also read as pure air), so this is conservative + low.
    pure = _lung_mask(hu) & (hu < -960)
    pure = ndi.binary_opening(pure, iterations=1)

    def score(vol_ml, mean_hu, vox):
        if vol_ml is None:
            return 0.4
        return 0.35 + min(0.35, vol_ml / 300.0)

    return _large_region_candidates(
        pure, hu, spacing_mm, min_ml=8.0, min_vox=600,
        kind="intrathoracic air (possible pneumothorax)",
        label="Candidate intrathoracic air", model="classical-pneumothorax-cade", score_fn=score)


_DETECTORS = {
    "classical-lung-nodule-cade": detect_lung_nodules,
    "classical-hyperdensity-cade": detect_hyperdensities,
    "classical-calcification-cade": detect_calcifications,
    "classical-effusion-cade": detect_effusion,
    "classical-pneumothorax-cade": detect_pneumothorax,
}


def detect(volume: dict, detectors: list[str] | None = None) -> list[dict]:
    """Run the requested classical detectors on a build_seg_volume() dict (CT/HU).
    Returns a de-duplicated, score-sorted, capped list of candidate dicts. CT only."""
    if not volume.get("is_ct"):
        return []                                           # HU-based; MR has no HU
    hu = np.asarray(volume["hu"])
    spacing = volume["spacing_mm"]
    names = detectors or list(_DETECTORS.keys())
    cands: list[dict] = []
    for name in names:
        fn = _DETECTORS.get(name)
        if fn is None:
            continue
        config.assert_detector_allowed(name)                # fail closed
        for c in fn(hu, spacing):
            if c["score"] >= config.DETECT_MIN_SCORE:
                cands.append(c)
    cands.sort(key=lambda c: -c["score"])
    return _dedup(cands)[: config.DETECT_MAX_CANDIDATES]


def _dedup(cands: list[dict]) -> list[dict]:
    """Greedy overlap suppression (highest score first): drop a candidate whose centroid
    is within ~one region-size of an already-kept candidate on a nearby slice, so two
    detectors flagging the SAME lesion collapse to one box."""
    kept: list[dict] = []
    for c in cands:
        r = c["region"]
        cz, (cx, cy) = r["slice_index"], r["centroid"]
        w, h = (r["bbox"][2], r["bbox"][3]) if r.get("bbox") else (8, 8)
        tol = max(w, h, 6)
        dup = False
        for k in kept:
            kr = k["region"]
            if abs(kr["slice_index"] - cz) <= 3:
                kx, ky = kr["centroid"]
                if (kx - cx) ** 2 + (ky - cy) ** 2 <= tol ** 2:
                    dup = True
                    break
        if not dup:
            kept.append(c)
    return kept
