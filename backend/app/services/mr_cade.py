"""Classical MR CADe — RELATIVE-signal CANDIDATE detection (RESEARCH, unvalidated).

MR intensity is arbitrary (a.u.), so a candidate can only be RELATIVE: a focal region
whose signal is a strong statistical outlier vs the surrounding imaged tissue. This
NEVER makes an absolute or tissue-specific claim, NEVER emits HU, and (like the CT
CADe) is disclaimed research output for a radiologist to confirm. Deterministic;
scores are detector confidence in [0,1], not a probability of disease.
"""
import numpy as np
import scipy.ndimage as ndi

from .. import config
from . import mr_classical_seg

LICENSE = "no-model (scipy/numpy/scikit-image BSD-3-Clause)"
_Z = 2.5              # outlier threshold in std-devs above the tissue mean
_D_MIN_MM, _D_MAX_MM = 3.0, 40.0


def _voxel_mm3(spacing_mm):
    r, c, z = spacing_mm
    return float(r) * float(c) * float(z) if (r and c and z) else None


def detect_relative_hyperintensity(vol, spacing_mm):
    vol = np.asarray(vol).astype(np.float32)
    if vol.ndim != 3:
        return []
    structure = ndi.generate_binary_structure(3, 1)
    p99 = float(np.percentile(vol, 99))
    if not np.isfinite(p99) or p99 <= 0:
        return []
    fg = mr_classical_seg._in_tissue_mask(np.clip(vol / p99, 0.0, 1.0), structure)
    if fg.sum() < 500:
        return []
    vals = vol[fg]
    mean, std = float(vals.mean()), float(vals.std())
    if std <= 1e-6:
        return []
    bright = ndi.binary_opening(fg & (vol > mean + _Z * std), structure=structure)
    lbl, n = ndi.label(bright, structure=structure)
    if n == 0:
        return []
    counts = np.bincount(lbl.ravel())
    counts[0] = 0
    objs = ndi.find_objects(lbl)
    vmm3 = _voxel_mm3(spacing_mm)
    out = []
    for i in range(1, n + 1):
        vox = int(counts[i])
        if vox < 20:
            continue
        d = 2.0 * (3.0 * vox * vmm3 / (4.0 * np.pi)) ** (1.0 / 3.0) if vmm3 else None
        if d is not None and not (_D_MIN_MM <= d <= _D_MAX_MM):
            continue
        sl = objs[i - 1]
        comp = lbl[sl] == i
        zc = int((sl[0].start + sl[0].stop) // 2)
        yc = int((sl[1].start + sl[1].stop) // 2)
        xc = int((sl[2].start + sl[2].stop) // 2)
        ydim, xdim = sl[1].stop - sl[1].start, sl[2].stop - sl[2].start
        zscore = (float(vol[sl][comp].mean()) - mean) / std
        score = float(min(1.0, max(0.0, (zscore - _Z) / 4.0 + 0.4)))
        out.append({
            "label": "Candidate focal signal abnormality", "kind": "relative hyperintensity",
            "score": round(score, 3),
            "region": {"slice_index": zc, "bbox": [int(sl[2].start), int(sl[1].start), int(xdim), int(ydim)],
                       "centroid": [xc, yc]},
            "est_max_mm": round(d, 1) if d is not None else None,
            "est_volume_ml": round(vox * vmm3 / 1000.0, 1) if vmm3 else None,
            "mean_hu": None,  # MR is a.u. — never an HU claim
            "model": "classical-mr-hyperintensity-cade", "license": LICENSE,
        })
    out.sort(key=lambda c: -c["score"])
    return out


_DETECTORS = {"classical-mr-hyperintensity-cade": detect_relative_hyperintensity}


def detect(volume: dict, detectors: list[str] | None = None) -> list[dict]:
    """Run classical MR relative-signal detectors on a build_seg_volume() dict. MR only."""
    if volume.get("is_ct"):
        return []
    vol, spacing = np.asarray(volume["hu"]), volume["spacing_mm"]
    cands = []
    for name in (detectors or list(_DETECTORS.keys())):
        fn = _DETECTORS.get(name)
        if fn is None:
            continue
        config.assert_detector_allowed(name)
        cands += [c for c in fn(vol, spacing) if c["score"] >= config.DETECT_MIN_SCORE]
    cands.sort(key=lambda c: -c["score"])
    return cands[: config.DETECT_MAX_CANDIDATES]
