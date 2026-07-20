"""Per-label probability calibration.

The displayed banded op_norm confidence is a RANKING SCORE, not a calibrated
probability (measured ECE ~= 0.24; the 0.50-0.60 band was ~8% positive). This maps
that raw score -> a calibrated P(disease) per label, using an isotonic (default) or
Platt map fitted on held-out NIH data by the validation harness and written to
CALIBRATION_MAP_PATH. CALIBRATION_MODE=none => identity.

We SHIP BOTH: findings keep `probability` (the raw score, still what flag thresholds
use, so calibration can NEVER silently move a flag) and gain `calibrated_probability`
(the honest P for display / disposition / fusion).
"""
import json
import logging
import math
import threading

from .. import config

logger = logging.getLogger(__name__)

_map = None
_lock = threading.Lock()


def _load() -> dict:
    global _map
    if _map is not None:
        return _map
    with _lock:
        if _map is not None:
            return _map
        data = {"mode": "none", "per_label": {}}
        try:
            if config.CALIBRATION_MODE != "none" and config.CALIBRATION_MAP_PATH.exists():
                data = json.loads(config.CALIBRATION_MAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("calibration map load failed; using identity")
        _map = data
    return _map


def available() -> bool:
    return config.CALIBRATION_MODE != "none" and bool(_load().get("per_label"))


def state(label: str) -> str:
    """calibrated | insufficient_data | uncalibrated. Drives whether the UI may show
    the score as a probability at all."""
    if config.CALIBRATION_MODE == "none":
        return "uncalibrated"
    m = _load()
    if label in m.get("per_label", {}):
        return "calibrated"
    if label in m.get("excluded", {}):
        return "insufficient_data"
    return "uncalibrated"


def n_knots(label: str) -> int:
    """Number of DISTINCT calibrated (y) values in the isotonic map for a label — a
    proxy for how much support the map has. A sparse-label map fitted on a handful of
    positives collapses to a few distinct steps (often 0 -> ... -> 1.0), so a low knot
    count marks a map whose tail cannot be trusted to escalate triage (FIX #4)."""
    per = _load().get("per_label", {}).get(label)
    if not per:
        return 0
    ys = per.get("y", [])
    if ys:
        return len({round(float(y), 4) for y in ys})
    # Platt maps are smooth (no snap tail); treat as fully-supported for this check.
    return config.CALIBRATION_MIN_KNOTS if per else 0


def enough_knots(label: str) -> bool:
    """True if the label's calibration map has enough distinct knots to trust its tail
    for TRIAGE escalation. False for uncalibrated labels or degenerate/sparse maps."""
    if config.CALIBRATION_MODE == "none":
        return False
    return n_knots(label) >= config.CALIBRATION_MIN_KNOTS


def calibrate(label: str, score: float) -> float | None:
    """Map a raw score in [0,1] to a calibrated probability, or None when there is
    no map for this label (caller keeps the raw score)."""
    if config.CALIBRATION_MODE == "none":
        return None
    per = _load().get("per_label", {}).get(label)
    if not per:
        return None
    mode = _load().get("mode", "isotonic")
    x = max(0.0, min(1.0, float(score)))
    if mode == "platt":
        a, b = float(per.get("a", 1.0)), float(per.get("b", 0.0))
        try:
            return 1.0 / (1.0 + math.exp(-(a * x + b)))
        except OverflowError:
            return 0.0 if (a * x + b) < 0 else 1.0
    # isotonic: piecewise-linear interpolation over sorted (xs -> ys)
    xs, ys = per.get("x", []), per.get("y", [])
    if not xs:
        return None
    if x <= xs[0]:
        return float(ys[0])
    if x >= xs[-1]:
        return float(ys[-1])
    for i in range(1, len(xs)):
        if x <= xs[i]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            return float(y1) if x1 == x0 else float(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return float(ys[-1])
