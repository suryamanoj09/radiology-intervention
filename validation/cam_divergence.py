"""Cross-pathology CAM divergence / collapse diagnostic.

The worry (raised on image aa2a5daa3ca9): on ONE image, different pathologies
produce different attention locations — but are the per-class Grad-CAMs genuinely
CLASS-SPECIFIC, or is the model spraying / collapsing several findings onto one
salient region? A per-class explanation that is identical across classes explains
nothing.

For a given image we take the top-N scored pathologies, compute each one's CAM,
and measure pairwise:
  * centroid distance (fraction of image diagonal) — how far apart the hot spots are
  * IoU of the high-attention masks — how much the regions overlap
  * Pearson correlation of the full CAMs — how similar the maps are overall
Then a verdict:
  * COLLAPSED   — maps are near-identical (high mean IoU / high correlation / tiny
                  centroid spread): the CAMs are NOT class-specific here.
  * CLASS-SPECIFIC — maps diverge (low IoU, spread centroids): good.
  * MIXED       — in between.

This is a QA/interpretability tool, not a score shown to clinicians. Run it when a
set of findings looks suspicious.

Usage (from validation/, backend venv):
    python cam_divergence.py ../backend/storage/uploads/aa2a5daa3ca9.png --top 4
"""
import argparse
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
from PIL import Image

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_BACKEND))
from app.services import vision_xray  # noqa: E402
from app import config  # noqa: E402


def _centroid(cam):
    m = cam >= config.ATTENTION_MASK_FRAC * cam.max() if cam.max() > 0 else np.zeros_like(cam, bool)
    if not m.any():
        return None
    ys, xs = np.where(m)
    return float(xs.mean()), float(ys.mean())


def _mask(cam):
    return (cam >= config.ATTENTION_MASK_FRAC * cam.max()) if cam.max() > 0 else np.zeros_like(cam, bool)


def _iou(a, b):
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter) / float(union) if union else 0.0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--top", type=int, default=4, help="how many top-scored pathologies to compare")
    args = ap.parse_args(argv)

    img8 = np.asarray(Image.open(args.image).convert("L"), dtype=np.uint8)
    probs = vision_xray.predict_probs(img8)
    labels = [k for k, _ in sorted(probs.items(), key=lambda kv: -kv[1])[:args.top]]
    print(f"Top {len(labels)} pathologies: " + ", ".join(f"{l}({probs[l]:.2f})" for l in labels))

    maps = vision_xray.attention_maps(img8, labels)
    labels = [l for l in labels if l in maps]  # keep only those with a CAM
    H, W = next(iter(maps.values())).shape
    diag = float(np.hypot(H, W))

    cents = {l: _centroid(maps[l]) for l in labels}
    masks = {l: _mask(maps[l]) for l in labels}

    print(f"\nPer-class hot centroid (x%, y%):")
    for l in labels:
        c = cents[l]
        print(f"  {l:24} " + (f"x={c[0]/W:.0%} y={c[1]/H:.0%}" if c else "empty map"))

    print(f"\n{'pair':44} {'centroid-d':>10} {'IoU':>6} {'corr':>6}")
    print("-" * 70)
    dists, ious, corrs = [], [], []
    for a, b in combinations(labels, 2):
        ca, cb = cents[a], cents[b]
        d = (np.hypot(ca[0] - cb[0], ca[1] - cb[1]) / diag) if (ca and cb) else float("nan")
        iou = _iou(masks[a], masks[b])
        fa, fb = maps[a].ravel(), maps[b].ravel()
        corr = float(np.corrcoef(fa, fb)[0, 1]) if fa.std() > 0 and fb.std() > 0 else float("nan")
        if not np.isnan(d):
            dists.append(d)
        ious.append(iou)
        if not np.isnan(corr):
            corrs.append(corr)
        print(f"{a[:20]+' vs '+b[:20]:44} {d:10.1%} {iou:6.2f} {corr:6.2f}")

    mean_iou = float(np.mean(ious)) if ious else 0.0
    mean_corr = float(np.mean(corrs)) if corrs else 0.0
    mean_d = float(np.mean(dists)) if dists else 0.0
    # Verdict thresholds (interpretability heuristic, not a clinical score).
    if mean_iou >= 0.60 or mean_corr >= 0.85 or mean_d <= 0.03:
        verdict = "COLLAPSED — per-class CAMs are NOT class-specific on this image"
    elif mean_iou <= 0.25 and mean_corr <= 0.5:
        verdict = "CLASS-SPECIFIC — maps diverge as they should"
    else:
        verdict = "MIXED — some overlap; interpret per-class maps with care"
    print("-" * 70)
    print(f"mean centroid-distance={mean_d:.1%}  mean IoU={mean_iou:.2f}  mean corr={mean_corr:.2f}")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
