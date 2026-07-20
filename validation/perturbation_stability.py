"""Perturbation-stability: is a finding signal or noise dressed as signal?

A model that flags a pathology at 0.52 on a film but 0.48 on the same film rotated
3 degrees is not localizing disease — it is reacting to acquisition jitter. We run
the SAME image through label-preserving perturbations (horizontal flip, small
rotation, small crop) and report:
  * flip rate — fraction of (label, perturbation) pairs whose FLAG decision changed
    vs. the original (the headline instability number);
  * mean confidence std — average per-label spread across perturbations.
Chest pathology labels are side-agnostic, so a horizontal flip should be near
label-invariant; a high flip rate is a red flag on the whole pipeline.

Usage:  python perturbation_stability.py <image.png> [--threshold 0.5]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services import vision_xray  # noqa: E402
from app.config import FINDING_THRESHOLD  # noqa: E402


def perturbations(img8: np.ndarray):
    """Label-PRESERVING perturbations of a grayscale image (name, array)."""
    fill = int(img8.min())
    yield "original", img8
    yield "hflip", np.ascontiguousarray(img8[:, ::-1])
    im = Image.fromarray(img8)
    yield "rot+3", np.asarray(im.rotate(3, resample=Image.BILINEAR, fillcolor=fill), dtype=np.uint8)
    yield "rot-3", np.asarray(im.rotate(-3, resample=Image.BILINEAR, fillcolor=fill), dtype=np.uint8)
    h, w = img8.shape
    c = max(1, int(0.04 * min(h, w)))
    yield "crop4%", np.ascontiguousarray(img8[c:h - c, c:w - c])


def stability(img8: np.ndarray, threshold: float = FINDING_THRESHOLD) -> dict:
    scores = {name: vision_xray.predict_probs(p) for name, p in perturbations(img8)}
    base = scores["original"]
    labels = list(base.keys())
    flips = total = 0
    per_label = {}
    for lb in labels:
        vals = [scores[n][lb] for n in scores if lb in scores[n]]
        std = float(np.std(vals))
        lbl_flips = 0
        for n in scores:
            if n == "original" or lb not in scores[n]:
                continue
            total += 1
            if (base[lb] >= threshold) != (scores[n][lb] >= threshold):
                flips += 1
                lbl_flips += 1
        per_label[lb] = {"base": round(base[lb], 3), "std": round(std, 3), "flips": lbl_flips}
    return {
        "flip_rate": round(flips / total, 3) if total else 0.0,
        "mean_conf_std": round(float(np.mean([v["std"] for v in per_label.values()])), 4),
        "n_perturbations": len(scores) - 1,
        "per_label": per_label,
    }


def emit_stats(image_dir: Path, n: int, out_path: Path) -> dict:
    """Aggregate per-label perturbation std over up to n images and write
    perturbation_stats.json — the noise floor /api/compare uses to suppress interval
    deltas that are inside measurement error."""
    imgs = sorted(image_dir.glob("*.png"))[:n]
    acc = {}
    for p in imgs:
        img8 = np.asarray(Image.open(p).convert("L"), dtype=np.uint8)
        r = stability(img8)
        for lb, v in r["per_label"].items():
            acc.setdefault(lb, []).append(v["std"])
    per_label = {lb: {"std": round(float(np.mean(v)), 4), "n_images": len(v)}
                 for lb, v in acc.items()}
    out_path.write_text(json.dumps({"per_label": per_label,
                                    "meta": {"n_images": len(imgs),
                                             "perturbations": "hflip,rot+3,rot-3,crop4%"}}), encoding="utf-8")
    return per_label


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="an image, OR a directory with --emit-stats")
    ap.add_argument("--threshold", type=float, default=FINDING_THRESHOLD)
    ap.add_argument("--emit-stats", action="store_true",
                    help="aggregate per-label std over a directory -> perturbation_stats.json")
    ap.add_argument("--n", type=int, default=15, help="images to aggregate for --emit-stats")
    args = ap.parse_args(argv)

    if args.emit_stats:
        out = Path(__file__).resolve().parent / "perturbation_stats.json"
        pl = emit_stats(Path(args.image), args.n, out)
        print(f"Wrote {out} ({len(pl)} labels over up to {args.n} images). "
              f"Copy to backend/perturbation_stats.json to enable the compare noise floor.")
        return 0

    img8 = np.asarray(Image.open(args.image).convert("L"), dtype=np.uint8)
    r = stability(img8, args.threshold)
    print(f"\n=== Perturbation stability: {Path(args.image).name} ===")
    print(f"flip rate = {r['flip_rate']:.1%}  (flag decisions that changed under a "
          f"label-preserving perturbation)")
    print(f"mean per-label confidence std = {r['mean_conf_std']}")
    print(f"\n{'label':24} {'base':>6} {'std':>6} {'flips':>6}")
    print("-" * 46)
    for lb, v in sorted(r["per_label"].items(), key=lambda kv: -kv[1]["std"]):
        print(f"{lb:24} {v['base']:6.3f} {v['std']:6.3f} {v['flips']:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
