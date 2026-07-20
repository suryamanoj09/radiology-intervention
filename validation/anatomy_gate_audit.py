"""Anatomy-gate false-negative audit — the one component that can silently DELETE
a correct finding.

The anatomy gate suppresses a flag whose attention is not on plausible anatomy. If
PSPNet mis-segments, a TRUE finding is dropped and the clinician sees only a
reliability note. This measures that risk on NIH ground-truth boxes: among
GT-positive findings the model FLAGGED by score, what fraction did the anatomy gate
suppress? The number is merged into behavior_card.json as `anatomy_gate.fn_rate`.

Usage (anatomy gate must be ON):  python anatomy_gate_audit.py [--limit 60]
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
from app.services import vision_xray  # noqa: E402
from app import config  # noqa: E402

BBOX = HERE / "data" / "nih-sample" / "BBox_List_2017.csv"
IMG_DIRS = [HERE / "data" / "nih-sample" / "sample" / "images",
            HERE / "data" / "nih-sample" / "sample" / "sample" / "images"]
LABEL_MAP = {"Atelectasis": "Atelectasis", "Cardiomegaly": "Cardiomegaly",
             "Effusion": "Effusion", "Infiltrate": "Infiltration",
             "Infiltration": "Infiltration", "Mass": "Mass", "Nodule": "Nodule",
             "Pneumonia": "Pneumonia", "Pneumothorax": "Pneumothorax"}


def _find(name):
    for d in IMG_DIRS:
        if (d / name).exists():
            return d / name
    return None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args(argv)
    if config.ANATOMY_GATE_MODE != "suppress" or not config.ANATOMY_GATE_ENABLED:
        print("NOTE: anatomy gate is not in suppress mode; audit measures the active config.")

    flagged_pos = 0      # GT-positive findings the model flagged by score
    suppressed = 0       # ...that the anatomy gate then suppressed
    per_label = defaultdict(lambda: [0, 0])  # label -> [flagged_pos, suppressed]
    n = 0
    with open(BBOX, newline="") as fh:
        for row in csv.reader(fh):
            if args.limit and n >= args.limit:
                break
            if not row or row[0] == "Image Index" or len(row) < 6:
                continue
            label = LABEL_MAP.get(row[1].strip())
            path = _find(row[0])
            if not label or path is None:
                continue
            try:
                img8 = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)
                resp = vision_xray.analyze_xray(img8, None, "CR", "image")
            except Exception:
                continue
            f = next((x for x in resp.findings if x.label == label), None)
            if f is None:
                continue
            thr = config.LABEL_THRESHOLDS.get(label, config.FINDING_THRESHOLD)
            # "would-be flagged by score" = raw score cleared the threshold.
            if f.probability >= thr:
                flagged_pos += 1
                per_label[label][0] += 1
                if f.heatmap_state == "suppressed":
                    suppressed += 1
                    per_label[label][1] += 1
            n += 1

    fn_rate = round(suppressed / flagged_pos, 3) if flagged_pos else None
    print(f"\n=== Anatomy-gate FN audit (n={n} GT boxes) ===")
    print(f"GT-positive findings flagged by score: {flagged_pos}")
    print(f"...suppressed by the anatomy gate:      {suppressed}")
    print(f"FALSE-NEGATIVE RATE (gate deletes a true, score-flagged finding): {fn_rate}")
    print(f"\n{'label':16} {'flagged+':>9} {'suppressed':>11}")
    for lb, (fl, su) in sorted(per_label.items()):
        print(f"{lb:16} {fl:>9} {su:>11}")

    # Merge into the behaviour card so the number sits next to AUROC.
    card_path = config.BEHAVIOR_CARD_PATH
    try:
        card = json.loads(card_path.read_text(encoding="utf-8")) if card_path.exists() else {}
        card["anatomy_gate"] = {"fn_rate": fn_rate, "flagged_positives": flagged_pos,
                                "suppressed": suppressed, "n_boxes": n,
                                "note": "Fraction of score-flagged GT-positive findings the "
                                        "anatomy gate suppressed (a safety gate's own miss rate)."}
        card_path.write_text(json.dumps(card, indent=1), encoding="utf-8")
        print(f"\nMerged anatomy_gate.fn_rate into {card_path}")
    except Exception as e:
        print(f"(could not merge into behaviour card: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
