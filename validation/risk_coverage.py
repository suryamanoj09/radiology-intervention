"""Risk-coverage curve — turn the abstain gate into a tuned operating point.

The pipeline abstains on low-confidence inputs, but the OOD_* thresholds are
hand-picked constants. A risk-coverage curve makes them principled: sort by
confidence, "abstain" on the least-confident fraction, and report the error on the
remaining. You then pick the abstain rate that hits a target accuracy instead of
guessing thresholds.

Confidence proxy per label-instance = |score - flag_threshold| (distance from the
decision boundary); correct = (score >= threshold) == true. Reads predictions.json
from `run_validation.py --dump-predictions`.

Usage:  python risk_coverage.py [--threshold 0.5]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args(argv)
    pred_path = HERE / "predictions.json"
    if not pred_path.exists():
        raise SystemExit("predictions.json not found. Run: run_validation.py --dump-predictions")
    data = json.loads(pred_path.read_text(encoding="utf-8"))

    scores, trues = [], []
    for lbl, d in data.items():
        scores.extend(d["score"])
        trues.extend(d["true"])
    s = np.array(scores, dtype=float)
    y = np.array(trues, dtype=int)
    pred = (s >= args.threshold).astype(int)
    correct = (pred == y).astype(int)
    conf = np.abs(s - args.threshold)  # distance from the boundary = confidence

    order = np.argsort(-conf)  # most confident first
    correct_sorted = correct[order]
    n = len(y)

    print(f"\n=== Risk-coverage (abstain gate) — n={n}, threshold={args.threshold} ===")
    print(f"{'coverage':>9} {'kept':>6} {'accuracy':>9} {'abstained':>10}")
    print("-" * 40)
    for cov in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5]:
        k = max(1, int(round(cov * n)))
        acc = float(correct_sorted[:k].mean())
        print(f"{cov:9.0%} {k:6d} {acc:9.3f} {1 - cov:10.0%}")
    print("\nRead: accuracy should RISE as coverage falls (abstaining on the least "
          "confident cases). Pick the abstain rate that reaches your target accuracy; "
          "if accuracy does not rise, the confidence signal is not selective.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
