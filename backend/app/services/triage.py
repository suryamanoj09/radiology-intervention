"""Emergency triage flag.

Rule-based review-priority signal (NOT an alerting system, NOT a diagnosis).
Wording is always "needs priority review", never "emergency diagnosed".

Two safety-driven behaviours:
  * Pneumothorax — the one true emergency in the label set — uses a low,
    sensitivity-favouring threshold and is surfaced as "cannot exclude", because
    CXR models are insensitive to small/apical/supine pneumothoraces.
  * Triage is recomputed on the clinician's CONFIRMED findings at report time
    (assess_confirmed), so a human-confirmed pneumothorax can never ride through
    as "routine" just because the model's confidence was low.
"""

from .. import config
from ..models.schemas import Finding, StructuredFindings

_ORDER = {"routine": 0, "priority": 1, "urgent": 2}

# Labels that escalate the review queue when the model is confident.
PRIORITY_LABELS = {"Effusion", "Pneumonia", "Consolidation", "Edema", "Mass", "Lung Lesion"}


def _max_level(*levels: str) -> str:
    return max(levels, key=lambda lv: _ORDER.get(lv, 0)) if levels else "routine"


def assess(findings: list[Finding]) -> tuple[str, list[str]]:
    """Model-output triage for the top-of-page BANNER. Fires ONLY on a CALIBRATED
    probability above config.PRIORITY_MIN_CALIBRATED_P — never off a raw or
    uncalibrated score, so an overconfident 54% (calibrated ~5%) can't manufacture a
    red emergency (alert fatigue).

    Two extra safety gates:
      * FIX #4 — the calibrated P is CLAMPED to config.TRIAGE_MAX_CALIBRATED_P and the
        label's isotonic map must carry enough knot support, so a sparse-label tail
        that snapped to 1.0 cannot manufacture a false 'urgent' banner.
      * FIX #3 — a label that is NOT reliably measured (insufficient positive support
        or at/below-chance AUROC, e.g. Pneumonia 0.458 or Pneumothorax on 9 positives)
        does NOT escalate the banner; it is still surfaced as an advisory 'cannot
        exclude' per-finding disposition chip.
    """
    from . import calibration, label_map, reliability
    level = "routine"
    reasons: list[str] = []
    for f in findings:
        cp = f.calibrated_probability
        if cp is None:
            continue  # never fire the banner off a raw/uncalibrated score
        # FIX #4: clamp the calibrated P feeding triage (flags stay on the raw score).
        cp = min(float(cp), config.TRIAGE_MAX_CALIBRATED_P)
        if cp < config.PRIORITY_MIN_CALIBRATED_P:
            continue
        # FIX #3 / FIX #4: an unreliably-measured label, or a label whose calibration
        # map lacks knot support, is ADVISORY only — it must not escalate the banner
        # (the per-finding disposition still carries the 'cannot exclude' caveat).
        if not reliability.is_reliable(f.label) or not calibration.enough_knots(f.label):
            continue
        name = label_map.raw_display(f.label)
        if f.label == "Pneumothorax":
            level = "urgent"
            f.urgent = True
            reasons.append(f"Pneumothorax (P≈{cp:.0%}) — review promptly")
        elif f.label in PRIORITY_LABELS:
            level = _max_level(level, "priority")
            reasons.append(f"{name} (P≈{cp:.0%})")
    return level, reasons


def assess_confirmed(structured: StructuredFindings) -> tuple[str, list[str]]:
    """Recompute triage from the clinician's CONFIRMED findings."""
    level = "routine"
    reasons: list[str] = []
    if structured.pneumothorax:
        level = "urgent"
        reasons.append("Clinician-confirmed pneumothorax")
    priority = []
    if structured.pleural_effusion:
        priority.append("pleural effusion")
    if structured.consolidation:
        priority.append("consolidation")
    if priority and level != "urgent":
        level = "priority"
    reasons.extend(f"Clinician-confirmed {p}" for p in priority)
    return level, reasons


def combine(model_level: str, confirmed_level: str) -> str:
    return _max_level(model_level, confirmed_level)


# The gap between a raw confidence number and a clinical action. A model can be
# "flagged" at 0.51 and 0.85 and mean very different things; this maps each flagged
# finding to an explicit DISPOSITION so the UI is decision-support, not a number
# dump. Tied to the calibrated operating characteristics (op-point + priority).
BORDERLINE_MARGIN = float(getattr(config, "DISPOSITION_BORDERLINE_MARGIN", 0.05))


def finding_disposition(f: Finding) -> str | None:
    """Explicit action for a FLAGGED finding, or None if not flagged. Ordered by
    severity so the most urgent disposition always wins."""
    if not f.flagged:
        return None
    from . import reliability
    p = f.probability
    rel = reliability.label_reliability(f.label)
    if f.label == "Pneumothorax":
        # Pneumothorax stays a prominent 'cannot exclude' prompt (the model misses
        # small/apical/supine cases), but when it is not reliably measured the wording
        # is explicitly ADVISORY rather than a confident urgent call (FIX #3).
        if not rel["reliable"]:
            return ("Cannot exclude — advisory only; pneumothorax is not reliably "
                    "measured here and the model misses small/apical/supine cases. "
                    "Confirm on the image.")
        if p >= config.PNEUMOTHORAX_URGENT_THRESHOLD:
            return "Urgent — cannot exclude; review promptly"
        if p >= config.PNEUMOTHORAX_ALERT_THRESHOLD:
            return "Cannot exclude — confirm on the image (low score; model misses PTX)"
    # FIX #3 — any other not-reliably-measured label is surfaced as ADVISORY, not a
    # confident finding, so a hurried reader does not over-trust a low-value flag.
    if not rel["reliable"]:
        return (f"Advisory only — this label is not reliably measured "
                f"({rel['reason']}); cannot exclude, confirm independently — not a "
                f"confident finding.")
    if f.label in PRIORITY_LABELS and p >= config.URGENT_THRESHOLD:
        return "Recommend clinical correlation"
    thr = config.LABEL_THRESHOLDS.get(f.label, config.FINDING_THRESHOLD)
    if p < thr + BORDERLINE_MARGIN:
        return "Borderline — near the operating point, below a confident reporting threshold"
    return "Flagged for review"


def apply_dispositions(findings: list[Finding]) -> None:
    for f in findings:
        f.disposition = finding_disposition(f)
