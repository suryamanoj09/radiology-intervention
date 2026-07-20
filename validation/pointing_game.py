"""Pointing-game localization metric on NIH ChestX-ray14 expert boxes.

The question this answers: when the model flags a pathology, is its HOTTEST
Grad-CAM point actually inside the radiologist's box — and does that beat simply
guessing the centre of the chest? A heatmap that can't beat "always point at the
middle" adds no localization value, however pretty it looks.

For each expert-annotated (image, pathology, box) in BBox_List_2017.csv:
  * hit        = model's Grad-CAM PEAK falls inside the expert box
  * centre-hit = the image centre falls inside the expert box (the baseline)
Report per-pathology and overall hit-rate for both. The model earns its
localization only where hit-rate > centre-hit meaningfully.

This measures the SAME masked pipeline production runs (markers inpainted), so it
also serves as a regression guard on the shortcut fix: if masking pushed the peak
off real anatomy, hit-rate would drop here.

Usage (from the validation/ dir, backend venv active):
    python pointing_game.py --limit 120
    python pointing_game.py            # all boxes (slow on CPU)
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Import the real inference pipeline so we measure exactly what /analyze does.
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_BACKEND))
from app.services import vision_xray  # noqa: E402

BBOX_CSV = Path(__file__).resolve().parent / "data" / "nih-sample" / "BBox_List_2017.csv"
IMAGE_DIRS = [
    Path(__file__).resolve().parent / "data" / "nih-sample" / "sample" / "images",
    Path(__file__).resolve().parent / "data" / "nih-sample" / "sample" / "sample" / "images",
]

# NIH bbox label -> TorchXRayVision pathology name (only labels the model has).
LABEL_MAP = {
    "Atelectasis": "Atelectasis",
    "Cardiomegaly": "Cardiomegaly",
    "Effusion": "Effusion",
    "Infiltrate": "Infiltration",
    "Infiltration": "Infiltration",
    "Mass": "Mass",
    "Nodule": "Nodule",
    "Pneumonia": "Pneumonia",
    "Pneumothorax": "Pneumothorax",
}

NIH_SIZE = 1024.0  # NIH ChestX-ray14 boxes are defined on 1024x1024 images.


def _find_image(name: str) -> Path | None:
    for d in IMAGE_DIRS:
        p = d / name
        if p.exists():
            return p
    return None


def _rows():
    with open(BBOX_CSV, newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0] == "Image Index" or len(row) < 6:
                continue
            name, raw_label = row[0], row[1]
            label = LABEL_MAP.get(raw_label.strip())
            if not label:
                continue
            try:
                x, y, w, h = (float(row[2]), float(row[3]), float(row[4]), float(row[5]))
            except ValueError:
                continue
            yield name, label, (x, y, w, h)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap number of boxes (0 = all)")
    args = ap.parse_args(argv)

    per = {}          # label -> [hits, centre_hits, total]
    overall = [0, 0, 0]
    skipped = 0
    n = 0

    for name, label, (bx, by, bw, bh) in _rows():
        if args.limit and n >= args.limit:
            break
        path = _find_image(name)
        if path is None:
            skipped += 1
            continue
        try:
            img8 = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)
        except Exception:
            skipped += 1
            continue

        H, W = img8.shape
        sx, sy = W / NIH_SIZE, H / NIH_SIZE  # scale boxes if the PNG isn't 1024
        x0, y0, x1, y1 = bx * sx, by * sy, (bx + bw) * sx, (by + bh) * sy

        peak = vision_xray.attention_peak(img8, label)
        if peak is None:
            skipped += 1
            continue
        px, py = peak

        hit = 1 if (x0 <= px <= x1 and y0 <= py <= y1) else 0
        centre_hit = 1 if (x0 <= W / 2 <= x1 and y0 <= H / 2 <= y1) else 0

        d = per.setdefault(label, [0, 0, 0])
        d[0] += hit; d[1] += centre_hit; d[2] += 1
        overall[0] += hit; overall[1] += centre_hit; overall[2] += 1
        n += 1
        if n % 20 == 0:
            print(f"  ...scored {n} boxes", flush=True)

    print("\n=== Pointing game (Grad-CAM peak vs expert box) ===")
    print(f"scored {overall[2]} boxes, skipped {skipped} (image missing / label not scored)\n")
    print(f"{'Pathology':22} {'n':>4} {'CAM-hit':>8} {'centre':>8}  {'lift':>6}")
    print("-" * 54)
    for label in sorted(per):
        hits, ch, tot = per[label]
        if not tot:
            continue
        hr, cr = hits / tot, ch / tot
        print(f"{label:22} {tot:>4} {hr:8.1%} {cr:8.1%}  {hr - cr:+6.1%}")
    if overall[2]:
        hr, cr = overall[0] / overall[2], overall[1] / overall[2]
        lo, hi = _wilson(overall[0], overall[2])
        print("-" * 54)
        print(f"{'ALL':22} {overall[2]:>4} {hr:8.1%} {cr:8.1%}  {hr - cr:+6.1%}")
        print(f"\n95% Wilson CI on the CAM-hit rate: [{lo:.1%}, {hi:.1%}] over n={overall[2]}.")
        if overall[2] < 100:
            print("⚠ n is small — this result is DIRECTIONAL, not conclusive. The full "
                  "984-box NIH set is needed for a headline claim (needs the full download).")
        print("\nRead: 'lift' > 0 means the heatmap localizes better than guessing"
              " the centre of the chest. Lift <= 0 for a pathology means the CAM"
              " adds no localization value there — surface that honestly, don't"
              " draw a confident box.")
    return 0


def _wilson(hits: int, n: int, z: float = 1.96):
    """95% Wilson score interval for a proportion — honest error bars on small n."""
    if n == 0:
        return 0.0, 0.0
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
