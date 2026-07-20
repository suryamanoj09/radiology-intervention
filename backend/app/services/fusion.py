"""Multi-view study fusion (no training, no new model).

Combines the per-image AnalyzeResponse objects of ONE study (e.g. a PA + a lateral
chest film uploaded together) into a per-label FUSED confidence: the MAX banded
confidence across views, tagged with which view / image produced it.

MAX (not mean) is the safety-favouring choice — a finding visible on only one
projection (a retrocardiac opacity seen on the lateral, an apical pneumothorax on
an expiratory frontal) must NOT be diluted toward "normal" by a clean companion
view. This is a display-level aggregation of EXISTING model outputs; it makes no
new prediction, runs no model, and claims no accuracy improvement. Abstained
images (self-audit refused) are excluded from fusion so a non-CXR slot can't
inject spurious confidence.
"""
from __future__ import annotations

from .. import config
from ..models.schemas import AnalyzeResponse, FusedFinding, StudyResponse

_TRIAGE_ORDER = {"routine": 0, "priority": 1, "urgent": 2}


def _worst_triage(images: list[AnalyzeResponse]) -> tuple[str, list[str]]:
    """Study triage = worst per-image triage. Reasons are tagged with the view
    they came from so the clinician sees which projection drove the escalation."""
    worst = "routine"
    reasons: list[str] = []
    for im in images:
        if im.competence == "abstain":
            continue
        if _TRIAGE_ORDER.get(im.triage, 0) > _TRIAGE_ORDER.get(worst, 0):
            worst = im.triage
    for im in images:
        if im.competence == "abstain":
            continue
        for r in im.triage_reasons:
            tag = f"[{im.view}] {r}"
            if tag not in reasons:
                reasons.append(tag)
    return worst, reasons


def _mode() -> str:
    m = config.FUSION_MODE
    return m if m in ("max", "noisy_or", "calibrated_mean") else "max"


def fuse_findings(images: list[AnalyzeResponse]) -> list[FusedFinding]:
    """Per-label fusion across the study's non-abstained images.

    FUSION_MODE:
      * max (default)       — safety-favouring max of the raw score; a one-view
                              finding is never diluted.
      * calibrated_mean     — mean of CALIBRATED probabilities (honest for an
                              overconfident model); falls back to max if any view
                              lacks a calibrated value.
      * noisy_or            — 1 - Π(1 - calibrated_p); falls back to max likewise.
    A DOWN-WEIGHTED view's contribution is scaled (config.DOWNWEIGHT_FUSION_FACTOR)
    so a "less reliable" projection can't drive the study by accident; `flagged` is
    True if ANY (full-strength) view flagged the label. `per_view` shows each view's
    RAW score at full value for transparency.
    """
    mode = _mode()
    per_view: dict[str, dict[str, float]] = {}
    agg: dict[str, dict] = {}
    for im in images:
        if im.competence == "abstain":
            continue
        w = config.DOWNWEIGHT_FUSION_FACTOR if im.competence == "down-weight" else 1.0
        for f in im.findings:
            per_view.setdefault(f.label, {})[im.image_id] = round(f.probability, 4)
            a = agg.setdefault(f.label, {"raw": [], "cal": [], "flag": False,
                                         "max_raw": -1.0, "view": im.view, "image_id": im.image_id})
            a["raw"].append(f.probability * w)
            cal = f.calibrated_probability
            a["cal"].append((cal if cal is not None else f.probability) * w)
            a["has_cal"] = a.get("has_cal", True) and (cal is not None)
            if f.flagged and w == 1.0:
                a["flag"] = True
            if f.probability > a["max_raw"]:
                a["max_raw"] = f.probability
                a["view"], a["image_id"] = im.view, im.image_id

    out: list[FusedFinding] = []
    for label, a in agg.items():
        use_cal = mode in ("noisy_or", "calibrated_mean") and a.get("has_cal")
        eff_mode = mode if use_cal else "max"
        if eff_mode == "calibrated_mean":
            prob = sum(a["cal"]) / len(a["cal"])
            cal_prob = prob
        elif eff_mode == "noisy_or":
            prod = 1.0
            for c in a["cal"]:
                prod *= (1.0 - max(0.0, min(1.0, c)))
            prob = 1.0 - prod
            cal_prob = prob
        else:  # max
            prob = max(a["raw"])
            cal_prob = max(a["cal"]) if a.get("has_cal") else None
        out.append(FusedFinding(
            label=label, probability=round(prob, 4),
            calibrated_probability=round(cal_prob, 4) if cal_prob is not None else None,
            flagged=a["flag"], view=a["view"], image_id=a["image_id"],
            per_view=per_view.get(label, {}), fusion_mode=eff_mode))
    return sorted(out, key=lambda f: f.probability, reverse=True)


def build_study_response(images: list[AnalyzeResponse], study_id: str,
                         disclaimer: str) -> StudyResponse:
    fused = fuse_findings(images)
    triage, triage_reasons = _worst_triage(images)
    n_abstained = sum(1 for im in images if im.competence == "abstain")
    top = next((f.label for f in fused if f.flagged), None)
    return StudyResponse(
        study_id=study_id,
        images=images,
        fused=fused,
        top_finding=top,
        triage=triage,
        triage_reasons=triage_reasons,
        n_abstained=n_abstained,
        disclaimer=disclaimer,
    )
