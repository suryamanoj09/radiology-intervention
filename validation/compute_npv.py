"""Compute the MEASURED negative predictive value (NPV) of the "no-flag" state and
inject it into the behaviour card (FIX #1).

HONESTY: every number here is computed from the REAL validation scores dumped by
run_validation.py (--dump-predictions -> predictions.json), at the SAME per-label flag
thresholds the production app uses (app.config.LABEL_THRESHOLDS + FINDING_THRESHOLD).
Nothing is invented. It is an IN-DISTRIBUTION estimate on the NIH ChestX-ray14 sample
(disease prevalence far higher than a screening population), so it is labelled as such
and must be recomputed at the target-population prevalence before any clinical claim.

NPV = P(truly negative | not flagged) = TN / (TN + FN).
  * per-label:   over each label's not-flagged instances.
  * study-level: over images where NO label was flagged at all — the state a user is
                 most tempted to misread as "normal".

Run:  python compute_npv.py   (reads backend/predictions.json, patches behaviour cards)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
BACKEND = HERE.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app import config  # noqa: E402

NIH_LABELS = ["Atelectasis", "Cardiomegaly", "Effusion", "Infiltration", "Mass",
              "Nodule", "Pneumonia", "Pneumothorax", "Consolidation", "Edema",
              "Emphysema", "Fibrosis", "Pleural_Thickening", "Hernia"]


def _threshold_for(label: str) -> float:
    return config.LABEL_THRESHOLDS.get(label, config.FINDING_THRESHOLD)


def compute(preds: dict) -> dict:
    labels = [l for l in NIH_LABELS if l in preds and preds[l].get("score")]
    n = min(len(preds[l]["score"]) for l in labels) if labels else 0

    per_label = []
    thresholds = {}
    for lb in labels:
        s = preds[lb]["score"]
        t = preds[lb]["true"]
        th = _threshold_for(lb)
        thresholds[lb] = round(th, 4)
        tn = fn = 0
        for si, ti in zip(s, t):
            if si < th:               # not flagged
                if ti == 0:
                    tn += 1
                else:
                    fn += 1
        no_flag_n = tn + fn
        per_label.append({
            "pathology": lb,
            "threshold": round(th, 4),
            "positives": int(sum(t)),
            "no_flag_n": no_flag_n,
            "false_negative": fn,      # disease present but not flagged
            "npv": round(tn / no_flag_n, 4) if no_flag_n else None,
        })

    # Study-level: an image is "no-flag" iff no label crossed its threshold; it is a
    # true negative iff NONE of the NIH findings are actually present on it.
    any_flag = [False] * n
    any_true = [False] * n
    for lb in labels:
        s = preds[lb]["score"]
        t = preds[lb]["true"]
        th = _threshold_for(lb)
        for i in range(n):
            if s[i] >= th:
                any_flag[i] = True
            if t[i] == 1:
                any_true[i] = True
    no_flag = [i for i in range(n) if not any_flag[i]]
    tn = sum(1 for i in no_flag if not any_true[i])
    fn = sum(1 for i in no_flag if any_true[i])
    prevalence = round(sum(any_true) / n, 4) if n else None

    study = {
        "n_images": n,
        "no_flag_images": len(no_flag),
        "true_negative": tn,
        "missed_disease": fn,           # a no-flag image that DID have disease
        "npv": round(tn / len(no_flag), 4) if no_flag else None,
        "test_set_prevalence": prevalence,
    }

    return {
        "available": True,
        "definition": "NPV = P(truly negative | model flagged nothing) = TN / (TN + FN).",
        "note": ("IN-DISTRIBUTION estimate on the NIH ChestX-ray14 sample "
                 f"({n} images; disease prevalence ~{int((prevalence or 0) * 100)}%, far "
                 "higher than a screening population). Computed from the real validation "
                 "scores at the production flag thresholds — NOT a clinical guarantee. "
                 "Recompute at the target-population prevalence. A no-flag result is NOT "
                 "a normal read: at this prevalence the model still missed disease on "
                 f"{fn} of {len(no_flag)} no-flag studies."),
        "flag_thresholds": thresholds,
        "study_level": study,
        "per_label": sorted(per_label, key=lambda r: r["pathology"]),
    }


def _patch_card(card_path: Path, block: dict) -> bool:
    if not card_path.exists():
        return False
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["no_flag_npv"] = block
    card_path.write_text(json.dumps(card, indent=1), encoding="utf-8")
    return True


def main():
    preds_path = BACKEND / "predictions.json"
    if not preds_path.exists():
        raise SystemExit(f"{preds_path} not found — run run_validation.py --dump-predictions first.")
    preds = json.loads(preds_path.read_text(encoding="utf-8"))
    block = compute(preds)
    print(json.dumps(block["study_level"], indent=1))
    for card in (BACKEND / "behavior_card.json", HERE / "behavior_card.json"):
        ok = _patch_card(card, block)
        print(("patched " if ok else "skipped (missing) ") + str(card))


if __name__ == "__main__":
    main()
