"""Validation harness — measure the pretrained model's behaviour honestly.

Produces a versioned "behaviour card": per-pathology detection metrics (AUROC,
sensitivity, specificity at the flag threshold) on NIH ChestX-ray14, plus a
Grad-CAM localization check against the 984 NIH ground-truth boxes.

These are ENGINEERING SANITY CHECKS on a research-grade pretrained model, on
public data the model was partly trained on relatives of — NOT clinical
validation and NOT a performance guarantee. That caveat is printed on the card.

Run (after download_data.py):  python run_validation.py [--limit N]
Outputs:  behavior_card.json, behavior_card.md
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

HERE = Path(__file__).parent
DATA = HERE / "data"
sys.path.insert(0, str(HERE.parent / "backend"))

from app.config import FINDING_THRESHOLD, ENSEMBLE_WEIGHTS  # noqa: E402
from app.services import vision_xray  # noqa: E402

# NIH label -> TorchXRayVision pathology (same strings; explicit for safety).
NIH_LABELS = ["Atelectasis", "Cardiomegaly", "Effusion", "Infiltration", "Mass",
              "Nodule", "Pneumonia", "Pneumothorax", "Consolidation", "Edema",
              "Emphysema", "Fibrosis", "Pleural_Thickening", "Hernia"]


def _find_labels_csv():
    for name in ("sample_labels.csv", "Data_Entry_2017.csv"):
        hits = list((DATA / "nih-sample").rglob(name))
        if hits:
            return hits[0]
    return None


def _find_images_dir():
    for p in (DATA / "nih-sample").rglob("images"):
        if p.is_dir() and any(p.glob("*.png")):
            return p
    # some mirrors nest images in images/images
    pngs = list((DATA / "nih-sample").rglob("*.png"))
    return pngs[0].parent if pngs else None


def _load_uint8(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("L"), dtype=np.uint8)


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix, iy = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, ix2 - ix) * max(0, iy2 - iy)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def detection_metrics(labels_csv, images_dir, limit):
    df = pd.read_csv(labels_csv)
    label_col = "Finding Labels" if "Finding Labels" in df.columns else df.columns[1]
    name_col = "Image Index" if "Image Index" in df.columns else df.columns[0]

    y_true = defaultdict(list)
    y_score = defaultdict(list)
    n = 0
    for _, row in df.iterrows():
        img_path = images_dir / str(row[name_col])
        if not img_path.exists():
            continue
        gt = set(str(row[label_col]).split("|"))
        try:
            probs = vision_xray.predict_probs(_load_uint8(img_path))
        except Exception:
            continue
        for lbl in NIH_LABELS:
            if lbl in probs:
                y_true[lbl].append(1 if lbl in gt else 0)
                y_score[lbl].append(probs[lbl])
        n += 1
        if limit and n >= limit:
            break

    from sklearn.metrics import roc_auc_score
    rows = []
    for lbl in NIH_LABELS:
        t = np.array(y_true.get(lbl, []))
        s = np.array(y_score.get(lbl, []))
        if t.size == 0 or t.sum() == 0 or t.sum() == t.size:
            rows.append({"pathology": lbl, "n": int(t.size), "positives": int(t.sum()),
                         "auroc": None, "sensitivity": None, "specificity": None})
            continue
        pred = (s >= FINDING_THRESHOLD).astype(int)
        tp = int(((pred == 1) & (t == 1)).sum()); fn = int(((pred == 0) & (t == 1)).sum())
        tn = int(((pred == 0) & (t == 0)).sum()); fp = int(((pred == 1) & (t == 0)).sum())
        # Sens/spec CURVE across thresholds so the UI slider can show live "at 0.55:
        # sens 0.82 / spec 0.61" instead of a single operating-point number.
        curve = []
        for th in np.round(np.arange(0.05, 1.0, 0.05), 2):
            pr = (s >= th).astype(int)
            ctp = int(((pr == 1) & (t == 1)).sum()); cfn = int(((pr == 0) & (t == 1)).sum())
            ctn = int(((pr == 0) & (t == 0)).sum()); cfp = int(((pr == 1) & (t == 0)).sum())
            curve.append({"t": float(th),
                          "sens": round(ctp / (ctp + cfn), 3) if (ctp + cfn) else None,
                          "spec": round(ctn / (ctn + cfp), 3) if (ctn + cfp) else None})
        rows.append({
            "pathology": lbl, "n": int(t.size), "positives": int(t.sum()),
            # Fewer than 20 positives => treat the metric as unreliable/indicative.
            "reliable": bool(int(t.sum()) >= 20),
            "auroc": round(float(roc_auc_score(t, s)), 3),
            "sensitivity": round(tp / (tp + fn), 3) if (tp + fn) else None,
            "specificity": round(tn / (tn + fp), 3) if (tn + fp) else None,
            "curve": curve,
        })
    return rows, n, y_true, y_score


def emit_calibration(y_true, y_score, out_path):
    """Derive per-label flag thresholds in BANDED space by maximizing Youden's J
    (sensitivity + specificity - 1) on the NIH sample. NO TRAINING — this only
    tunes each label's decision threshold; model weights are untouched. The app
    loads the result via config.CALIBRATION_PATH."""
    from sklearn.metrics import roc_curve
    # Require enough positives so a tiny sample can't yield a degenerate operating
    # point (e.g. n=3 pneumonia -> threshold ~0, flagging everything), and clamp
    # to a sane band. Sparse labels fall back to the FINDING_THRESHOLD floor.
    MIN_POS = 20
    CLAMP_LO, CLAMP_HI = 0.2, 0.8
    thresholds, skipped = {}, {}
    for lbl in NIH_LABELS:
        t = np.array(y_true.get(lbl, []))
        s = np.array(y_score.get(lbl, []))
        pos = int(t.sum()) if t.size else 0
        if t.size == 0 or pos < MIN_POS or pos == t.size:
            skipped[lbl] = pos
            continue
        fpr, tpr, thr = roc_curve(t, s)
        best = int(np.argmax(tpr - fpr))
        cut = float(thr[best]) if np.isfinite(thr[best]) else float(s.max())
        thresholds[lbl] = round(min(CLAMP_HI, max(CLAMP_LO, cut)), 4)
    payload = {
        "thresholds": thresholds,
        "meta": {
            "method": "youden_j",
            "space": "banded_op_norm",
            "ensemble": ENSEMBLE_WEIGHTS,
            "source": "NIH ChestX-ray14 sample",
            "caveat": "In-distribution operating-point tuning, not clinical calibration.",
        },
    }
    out_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return thresholds


def _ece_and_bins(t: np.ndarray, s: np.ndarray, bins: np.ndarray) -> dict:
    """Expected Calibration Error + a reliability table (predicted confidence vs
    observed positive frequency per bin). ECE = sum_b (n_b/N) * |obs_b - conf_b|."""
    n = len(s)
    ece = 0.0
    reliability = []
    for i in range(len(bins) - 1):
        lo, hi = bins[i], bins[i + 1]
        m = (s >= lo) & (s <= hi) if i == len(bins) - 2 else (s >= lo) & (s < hi)
        cnt = int(m.sum())
        if cnt == 0:
            reliability.append({"bin": [round(float(lo), 2), round(float(hi), 2)],
                                "count": 0, "conf": None, "obs": None})
            continue
        conf, obs = float(s[m].mean()), float(t[m].mean())
        ece += cnt / n * abs(obs - conf)
        reliability.append({"bin": [round(float(lo), 2), round(float(hi), 2)],
                            "count": cnt, "conf": round(conf, 3), "obs": round(obs, 3)})
    return {"ece": round(ece, 4), "n": n, "reliability": reliability}


def calibration_metrics(y_true, y_score, n_bins=10) -> dict:
    """Reliability diagram + ECE for the DISPLAYED banded confidence — the honest
    test of whether "0.7 confidence" means "≈70% observed positives", not just
    whether the 0.5 threshold is placed right. Per-label + micro-averaged overall."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    all_t, all_s, per = [], [], {}
    for lbl in NIH_LABELS:
        t = np.array(y_true.get(lbl, []), dtype=float)
        s = np.array(y_score.get(lbl, []), dtype=float)
        if t.size == 0:
            continue
        all_t.append(t)
        all_s.append(s)
        per[lbl] = {**_ece_and_bins(t, s, bins), "positives": int(t.sum())}
    if not all_t:
        return {"available": False, "note": "no scored labels"}
    T, S = np.concatenate(all_t), np.concatenate(all_s)
    return {"available": True, "n_bins": n_bins,
            "overall": _ece_and_bins(T, S, bins), "per_class": per}


def emit_calibration_map(y_true, y_score, out_path) -> dict:
    """Fit a PER-LABEL isotonic map (raw score -> calibrated P) on held-out data
    and write it as a portable piecewise-linear table the backend loads. This is
    the fix for the ECE≈0.24 overconfidence — NO retraining, only a monotonic
    remap of the displayed number."""
    from sklearn.isotonic import IsotonicRegression
    per_label, excluded = {}, {}
    grid = np.linspace(0.0, 1.0, 21)
    for lbl in NIH_LABELS:
        t = np.array(y_true.get(lbl, []), dtype=float)
        s = np.array(y_score.get(lbl, []), dtype=float)
        pos = int(t.sum()) if t.size else 0
        # Require enough POSITIVES so a small-sample isotonic step can't invent a
        # misleading calibrated probability. Labels below this get NO calibrated
        # number and are recorded as excluded (with the reason) so the UI can show
        # an honest "insufficient_data" state instead of a bare score.
        if t.size < 40 or pos < 12 or pos == t.size:
            excluded[lbl] = {"reason": "too_few_positives", "positives": pos, "n": int(t.size)}
            continue
        ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        ir.fit(s, t)
        ys = ir.predict(grid)
        per_label[lbl] = {"x": [round(float(x), 4) for x in grid],
                          "y": [round(float(y), 4) for y in ys]}
    payload = {"mode": "isotonic", "per_label": per_label, "excluded": excluded,
               "meta": {"method": "isotonic", "source": "NIH ChestX-ray14 sample",
                        "min_positives": 12,
                        "caveat": "In-distribution isotonic remap; recalibrate on target data."}}
    out_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return per_label


def no_flag_npv(y_true, y_score) -> dict:
    """MEASURED negative predictive value of the "no-flag" state (FIX #1).

    NPV = P(truly negative | not flagged) = TN / (TN + FN), at the SAME per-label flag
    thresholds the app uses. Per-label over each label's not-flagged instances, and
    study-level over images where NO label was flagged (the state a user is tempted to
    read as "normal"). IN-DISTRIBUTION on the NIH sample — labelled as such, never a
    clinical guarantee. Study-level requires the per-label arrays to be image-aligned
    (they are: all labels are appended in the same per-image loop in detection_metrics).
    """
    from app.config import LABEL_THRESHOLDS

    def thr(lbl):
        return LABEL_THRESHOLDS.get(lbl, FINDING_THRESHOLD)

    labels = [l for l in NIH_LABELS if y_score.get(l)]
    n = min((len(y_score[l]) for l in labels), default=0)

    per_label, thresholds = [], {}
    for lbl in labels:
        s, t = y_score[lbl], y_true[lbl]
        th = thr(lbl)
        thresholds[lbl] = round(th, 4)
        tn = sum(1 for si, ti in zip(s, t) if si < th and ti == 0)
        fn = sum(1 for si, ti in zip(s, t) if si < th and ti == 1)
        no_flag_n = tn + fn
        per_label.append({"pathology": lbl, "threshold": round(th, 4),
                          "positives": int(sum(t)), "no_flag_n": no_flag_n,
                          "false_negative": fn,
                          "npv": round(tn / no_flag_n, 4) if no_flag_n else None})

    any_flag = [False] * n
    any_true = [False] * n
    for lbl in labels:
        s, t, th = y_score[lbl], y_true[lbl], thr(lbl)
        for i in range(n):
            if s[i] >= th:
                any_flag[i] = True
            if t[i] == 1:
                any_true[i] = True
    no_flag = [i for i in range(n) if not any_flag[i]]
    tn = sum(1 for i in no_flag if not any_true[i])
    fn = sum(1 for i in no_flag if any_true[i])
    prevalence = round(sum(any_true) / n, 4) if n else None
    study = {"n_images": n, "no_flag_images": len(no_flag), "true_negative": tn,
             "missed_disease": fn,
             "npv": round(tn / len(no_flag), 4) if no_flag else None,
             "test_set_prevalence": prevalence}
    return {
        "available": True,
        "definition": "NPV = P(truly negative | model flagged nothing) = TN / (TN + FN).",
        "note": ("IN-DISTRIBUTION estimate on the NIH ChestX-ray14 sample "
                 f"({n} images; prevalence ~{int((prevalence or 0) * 100)}%, far higher "
                 "than screening). Computed from the real validation scores at the "
                 "production flag thresholds — NOT a clinical guarantee. Recompute at "
                 "target-population prevalence. A no-flag result is NOT a normal read."),
        "flag_thresholds": thresholds,
        "study_level": study,
        "per_label": sorted(per_label, key=lambda r: r["pathology"]),
    }


def dump_predictions(y_true, y_score, out_path) -> None:
    """Dump raw (label -> [scores], [labels]) so decision_curve.py / risk_coverage.py
    can compute net benefit and risk-coverage without re-running the model."""
    payload = {lbl: {"score": [round(float(x), 5) for x in y_score.get(lbl, [])],
                     "true": [int(v) for v in y_true.get(lbl, [])]}
               for lbl in NIH_LABELS if y_true.get(lbl)}
    out_path.write_text(json.dumps(payload), encoding="utf-8")


def subgroup_metrics(labels_csv, images_dir, limit) -> dict:
    """Per-view-subgroup AUROC (PA vs AP/portable). Aggregate AUROC hides exactly
    the acquisition shift that matters clinically — portable/supine ICU films are a
    different distribution. Micro-averaged over labels within each subgroup."""
    df = pd.read_csv(labels_csv)
    if "View Position" not in df.columns:
        return {"available": False, "note": "no 'View Position' column in labels csv"}
    label_col = "Finding Labels" if "Finding Labels" in df.columns else df.columns[1]
    name_col = "Image Index" if "Image Index" in df.columns else df.columns[0]

    groups = {"PA": {"t": defaultdict(list), "s": defaultdict(list), "n": 0},
              "AP": {"t": defaultdict(list), "s": defaultdict(list), "n": 0}}
    n = 0
    for _, row in df.iterrows():
        vp = str(row.get("View Position", "")).strip().upper()
        grp = "PA" if vp == "PA" else ("AP" if vp == "AP" else None)
        if grp is None:
            continue
        img_path = images_dir / str(row[name_col])
        if not img_path.exists():
            continue
        gt = set(str(row[label_col]).split("|"))
        try:
            probs = vision_xray.predict_probs(_load_uint8(img_path))
        except Exception:
            continue
        g = groups[grp]
        g["n"] += 1
        for lbl in NIH_LABELS:
            if lbl in probs:
                g["t"][lbl].append(1 if lbl in gt else 0)
                g["s"][lbl].append(probs[lbl])
        n += 1
        if limit and n >= limit:
            break

    from sklearn.metrics import roc_auc_score
    out = {"available": True, "groups": {}}
    for grp, g in groups.items():
        T = np.concatenate([np.array(g["t"][l]) for l in NIH_LABELS if g["t"][l]]) if g["n"] else np.array([])
        S = np.concatenate([np.array(g["s"][l]) for l in NIH_LABELS if g["s"][l]]) if g["n"] else np.array([])
        micro = None
        if T.size and 0 < T.sum() < T.size:
            micro = round(float(roc_auc_score(T, S)), 3)
        out["groups"][grp] = {"images": g["n"], "micro_auroc": micro, "label_instances": int(T.size)}
    return out


def localization_metrics(images_dir, limit):
    bbox_csv = next((DATA / "nih-sample").rglob("BBox_List_2017.csv"), None)
    if not bbox_csv:
        return {"available": False, "note": "BBox_List_2017.csv not found"}
    df = pd.read_csv(bbox_csv)
    cols = list(df.columns)
    name_col, label_col = cols[0], cols[1]
    box_cols = cols[2:6]

    per = defaultdict(lambda: {"n": 0, "hits": 0, "iou_sum": 0.0})
    n = 0
    for _, row in df.iterrows():
        img_path = images_dir / str(row[name_col])
        if not img_path.exists():
            continue
        label = str(row[label_col])
        if label not in NIH_LABELS:
            continue
        gt = [float(row[c]) for c in box_cols]  # x, y, w, h
        try:
            bbox = vision_xray.localize(_load_uint8(img_path), label)
        except Exception:
            continue
        p = per[label]; p["n"] += 1
        if bbox:
            pred = [bbox.x, bbox.y, bbox.width, bbox.height]
            iou = _iou(pred, gt)
            p["iou_sum"] += iou
            # "hit" = attention box overlaps the ground-truth region at all
            if iou > 0:
                p["hits"] += 1
        n += 1
        if limit and n >= limit:
            break

    out = {"available": True, "per_class": {}, "total_boxes": n}
    for lbl, v in per.items():
        out["per_class"][lbl] = {
            "n": v["n"],
            "hit_rate": round(v["hits"] / v["n"], 3) if v["n"] else None,
            "mean_iou": round(v["iou_sum"] / v["n"], 3) if v["n"] else None,
        }
    return out


CAVEAT = (
    "Engineering sanity check on a research-grade pretrained model (TorchXRayVision "
    "densenet121-res224-all) using public data. NOT clinical validation, NOT a "
    "performance guarantee. The model was trained on datasets related to NIH/CheXpert, "
    "so these numbers are in-distribution and optimistic. Grad-CAM localization is a "
    "region-of-attention check, not lesion segmentation."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=800, help="max images to score (0 = all)")
    ap.add_argument("--emit-calibration", action="store_true",
                    help="write calibration.json (per-label thresholds) from this run")
    ap.add_argument("--emit-calibration-map", action="store_true",
                    help="write calibration_map.json (isotonic score->probability map)")
    ap.add_argument("--dump-predictions", action="store_true",
                    help="write predictions.json (for decision_curve.py / risk_coverage.py)")
    args = ap.parse_args()

    labels_csv, images_dir = _find_labels_csv(), _find_images_dir()
    if not labels_csv or not images_dir:
        raise SystemExit("NIH sample not found. Run download_data.py first (needs a Kaggle token).")

    print(f"Scoring detection on up to {args.limit or 'all'} images ...")
    det_rows, n_scored, y_true, y_score = detection_metrics(labels_csv, images_dir, args.limit or None)
    print("Scoring Grad-CAM localization vs ground-truth boxes ...")
    loc = localization_metrics(images_dir, args.limit or None)
    print("Computing calibration (reliability + ECE) ...")
    calib = calibration_metrics(y_true, y_score)
    print("Computing subgroup performance (PA vs AP) ...")
    subgroup = subgroup_metrics(labels_csv, images_dir, args.limit or None)

    card = {
        "model": "torchxrayvision ensemble: " + ", ".join(ENSEMBLE_WEIGHTS),
        "flag_threshold": FINDING_THRESHOLD,
        "images_scored": n_scored,
        "caveat": CAVEAT,
        "detection": det_rows,
        "localization": loc,
        "calibration": calib,   # reliability diagram + ECE on the displayed confidence
        "subgroup": subgroup,   # PA vs AP/portable micro-AUROC
        # FIX #1 — measured NPV of the no-flag state (the "no flag != normal" number).
        "no_flag_npv": no_flag_npv(y_true, y_score),
    }
    (HERE / "behavior_card.json").write_text(json.dumps(card, indent=1), encoding="utf-8")

    if args.emit_calibration:
        cal_path = HERE / "calibration.json"
        thr = emit_calibration(y_true, y_score, cal_path)
        print(f"Wrote {cal_path} ({len(thr)} labels). To use it, set "
              f"CALIBRATION_PATH={cal_path} (or copy it to backend/calibration.json).")

    if args.emit_calibration_map:
        cmap_path = HERE / "calibration_map.json"
        pl = emit_calibration_map(y_true, y_score, cmap_path)
        print(f"Wrote {cmap_path} (isotonic map, {len(pl)} labels). "
              f"Copy to backend/calibration_map.json to enable calibrated probabilities.")

    if args.dump_predictions:
        pred_path = HERE / "predictions.json"
        dump_predictions(y_true, y_score, pred_path)
        print(f"Wrote {pred_path} for decision_curve.py / risk_coverage.py.")

    md = [f"# Model behaviour card\n", f"> {CAVEAT}\n",
          f"- Model: `{card['model']}`  ·  flag threshold: {FINDING_THRESHOLD}  ·  "
          f"images scored: {n_scored}\n", "## Detection\n",
          "| Pathology | n | pos | AUROC | Sensitivity | Specificity |",
          "|---|---|---|---|---|---|"]
    for r in det_rows:
        md.append(f"| {r['pathology']} | {r['n']} | {r['positives']} | "
                  f"{r['auroc']} | {r['sensitivity']} | {r['specificity']} |")
    md.append("\n## Grad-CAM localization (vs NIH ground-truth boxes)\n")
    if loc.get("available"):
        md.append("| Pathology | boxes | hit-rate | mean IoU |")
        md.append("|---|---|---|---|")
        for lbl, v in loc["per_class"].items():
            md.append(f"| {lbl} | {v['n']} | {v['hit_rate']} | {v['mean_iou']} |")
    else:
        md.append(loc.get("note", "not available"))

    md.append("\n## Calibration (reliability + ECE on displayed confidence)\n")
    if calib.get("available"):
        ov = calib["overall"]
        md.append(f"**Overall ECE = {ov['ece']}** (0 = perfectly calibrated) "
                  f"over {ov['n']} label-instances, {calib['n_bins']} bins.\n")
        md.append("| confidence bin | count | mean confidence | observed positive rate |")
        md.append("|---|---|---|---|")
        for b in ov["reliability"]:
            if b["count"]:
                md.append(f"| {b['bin'][0]}–{b['bin'][1]} | {b['count']} | {b['conf']} | {b['obs']} |")
        md.append("\n> A calibrated model has observed-rate ≈ mean-confidence in every "
                  "row. Large gaps mean the confidence number is over/under-confident, "
                  "not just that the 0.5 threshold is placed correctly.")
    else:
        md.append(calib.get("note", "not available"))

    md.append("\n## Subgroup performance (acquisition shift)\n")
    if subgroup.get("available"):
        md.append("| View | images | micro-AUROC | label-instances |")
        md.append("|---|---|---|---|")
        for grp, v in subgroup["groups"].items():
            md.append(f"| {grp} | {v['images']} | {v['micro_auroc']} | {v['label_instances']} |")
        md.append("\n> Aggregate AUROC hides acquisition shift; PA (upright) and "
                  "AP/portable (often ICU/supine) are different distributions.")
    else:
        md.append(subgroup.get("note", "not available"))
    (HERE / "behavior_card.md").write_text("\n".join(md), encoding="utf-8")

    print("Wrote behavior_card.json and behavior_card.md")


if __name__ == "__main__":
    main()
