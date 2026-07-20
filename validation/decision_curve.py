"""Decision Curve Analysis (Vickers & Elkin, Med Decis Making 2006).

AUROC asks "does it rank?"; calibration asks "does the number mean what it says?";
DCA asks the only question that matters clinically: "does acting on this beat the
trivial treat-all / treat-none strategies at a plausible threshold?"

Net benefit at threshold probability pt:
    NB = TP/N - (FP/N) * pt/(1-pt)
compared against treat-all and treat-none (NB = 0). DCA is meaningless on
uncalibrated scores, so run it on the CALIBRATED probability (calibration_map.json)
— it pairs specifically with the calibration work.

Reads predictions.json from `run_validation.py --dump-predictions`.
Usage:  python decision_curve.py [--label Effusion] [--raw]   (--raw = skip calibration)
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))


def _calibrated(label, scores, use_cal):
    if not use_cal:
        return scores
    from app.services import calibration
    out = []
    for s in scores:
        c = calibration.calibrate(label, s)
        out.append(c if c is not None else s)
    return np.array(out, dtype=float)


def net_benefit(p, y, pt):
    pred = p >= pt
    n = len(y)
    tp = int(np.sum(pred & (y == 1)))
    fp = int(np.sum(pred & (y == 0)))
    if pt >= 1.0:
        return 0.0
    return tp / n - (fp / n) * (pt / (1.0 - pt))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=None, help="one label, else micro-averaged over all")
    ap.add_argument("--raw", action="store_true", help="use raw score (skip calibration map)")
    args = ap.parse_args(argv)

    pred_path = HERE / "predictions.json"
    if not pred_path.exists():
        raise SystemExit("predictions.json not found. Run: run_validation.py --dump-predictions")
    data = json.loads(pred_path.read_text(encoding="utf-8"))
    labels = [args.label] if args.label else list(data.keys())

    ps, ys = [], []
    for lbl in labels:
        if lbl not in data:
            continue
        s = np.array(data[lbl]["score"], dtype=float)
        y = np.array(data[lbl]["true"], dtype=int)
        ps.append(_calibrated(lbl, s, not args.raw))
        ys.append(y)
    if not ps:
        raise SystemExit("no matching labels in predictions.json")
    p = np.concatenate(ps)
    y = np.concatenate(ys)
    prev = float(y.mean())

    print(f"\n=== Decision curve ({'raw score' if args.raw else 'calibrated'}) — "
          f"{args.label or 'all labels (micro)'} ===")
    print(f"n = {len(y)}, prevalence = {prev:.3f}\n")
    print(f"{'pt':>5} {'model':>9} {'treat-all':>10} {'treat-none':>11}  best")
    print("-" * 46)
    for pt in [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]:
        nb_model = net_benefit(p, y, pt)
        nb_all = prev - (1 - prev) * (pt / (1 - pt))
        nb_none = 0.0
        best = max([("model", nb_model), ("all", nb_all), ("none", nb_none)], key=lambda t: t[1])[0]
        print(f"{pt:5.2f} {nb_model:9.4f} {nb_all:10.4f} {nb_none:11.4f}  {best}")
    print("\nRead: where 'model' has the highest net benefit, using the tool beats "
          "treating everyone / no one. If treat-all/none wins at your threshold, the "
          "model adds no decision value there — surface that, don't hide it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
