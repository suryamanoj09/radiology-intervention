"""Prior-study comparison.

Compares model confidences between two analyzed studies and classifies each
flagged pathology as new / worsened / improved / resolved / stable. These are
changes in MODEL CONFIDENCE, not confirmed disease progression — the report
wording keeps that distinction.
"""

import json
import logging

from .. import config
from ..models.schemas import AnalyzeResponse, ComparisonRow, ComparisonSummary

logger = logging.getLogger(__name__)
DELTA = 0.15

_pstats = None


def _perturbation_std(label: str) -> float | None:
    """Measured per-label instability (hflip/rotate/crop std), or None if not
    measured. A prior→current delta below k× this is inside measurement error."""
    global _pstats
    if config.COMPARE_MIN_DELTA_MODE != "perturbation_std":
        return None
    if _pstats is None:
        try:
            _pstats = (json.loads(config.PERTURBATION_STATS_PATH.read_text(encoding="utf-8"))
                       if config.PERTURBATION_STATS_PATH.exists() else {})
        except Exception:
            logger.exception("perturbation stats load failed")
            _pstats = {}
    entry = _pstats.get("per_label", {}).get(label)
    return float(entry["std"]) if entry and "std" in entry else None


def _classify(label: str, prior: float, current: float) -> tuple[str, bool]:
    """(change, within_noise). A change smaller than the label's measured
    perturbation noise floor is downgraded to 'stable' and flagged within_noise —
    we do not report progression that is inside our own measurement error."""
    std = _perturbation_std(label)
    floor = config.COMPARE_NOISE_K * std if std is not None else 0.0
    if abs(current - prior) <= floor:
        return "stable", True
    flagged_prior = prior >= config.FINDING_THRESHOLD
    flagged_now = current >= config.FINDING_THRESHOLD
    if not flagged_prior and flagged_now:
        return "new", False
    if flagged_prior and not flagged_now:
        return "resolved", False
    if current - prior >= DELTA:
        return "worsened", False
    if prior - current >= DELTA:
        return "improved", False
    return "stable", False


def compare(prior: AnalyzeResponse, current: AnalyzeResponse,
            prior_date: str | None = None) -> ComparisonSummary:
    prior_map = {f.label: f.probability for f in prior.findings}
    rows: list[ComparisonRow] = []

    n_noise = 0
    for f in current.findings:
        p_prob = prior_map.get(f.label, 0.0)
        if max(p_prob, f.probability) < config.FINDING_THRESHOLD:
            continue
        change, within_noise = _classify(f.label, p_prob, f.probability)
        if within_noise:
            n_noise += 1
        rows.append(ComparisonRow(
            label=f.label,
            prior_probability=round(p_prob, 4),
            current_probability=round(f.probability, 4),
            change=change,
        ))

    rows.sort(key=lambda r: r.current_probability, reverse=True)

    changed = [r for r in rows if r.change not in ("stable",)]
    noise_note = (" Deltas within the model's measured perturbation noise are reported "
                  "as stable, not progression." if n_noise else "")
    if not rows:
        summary = "No pathology exceeded the flag threshold on either study."
    elif not changed:
        summary = ("All flagged findings are stable in model confidence versus the prior "
                   "study." + noise_note)
    else:
        parts = [f"{r.label} ({r.change})" for r in changed]
        summary = ("Interval change in model confidence: " + ", ".join(parts) + "." + noise_note)

    return ComparisonSummary(prior_date=prior_date, rows=rows, summary=summary)
