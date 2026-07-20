"""Per-label reliability gating (FIX #3), driven by the MEASURED behaviour card.

A label is "reliably measured" only when the validation set had enough POSITIVE
support (config.RELIABILITY_MIN_POSITIVES) AND the measured AUROC is above the
chance floor (config.RELIABILITY_MIN_AUROC). A label failing either bar is
"not_reliably_measured": it is surfaced as an ADVISORY "cannot exclude" signal,
never as a confident finding, and it must NOT drive an urgent triage escalation.

The positives/AUROC come from the real behaviour_card.json (`detection` rows), so
this is data-driven, not a hardcoded weak-label list. A label the card does not
measure at all is treated as not-reliably-measured (we have no evidence it is).
"""
import json
import logging
import threading

from .. import config

logger = logging.getLogger(__name__)

_cache: dict | None = None
_lock = threading.Lock()


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        out: dict[str, dict] = {}
        try:
            if config.BEHAVIOR_CARD_PATH.exists():
                card = json.loads(config.BEHAVIOR_CARD_PATH.read_text(encoding="utf-8"))
                for row in card.get("detection", []):
                    name = row.get("pathology")
                    if not name:
                        continue
                    out[name] = {
                        "auroc": row.get("auroc"),
                        "positives": int(row.get("positives", 0) or 0),
                    }
        except Exception:
            logger.exception("reliability: behaviour card load failed")
        _cache = out
    return _cache


def reset_cache() -> None:
    """Drop the cached card (tests that monkeypatch the card path call this)."""
    global _cache
    _cache = None


def label_reliability(label: str) -> dict:
    """{state, reliable, positives, auroc, reason} for a label.

    state is 'measured' (reliable) or 'not_reliably_measured'. reason is a short
    human explanation when NOT reliable, else None.
    """
    info = _load().get(label)
    positives = info["positives"] if info else 0
    auroc = info["auroc"] if info else None
    min_pos = config.RELIABILITY_MIN_POSITIVES
    min_auroc = config.RELIABILITY_MIN_AUROC

    reliable = (
        info is not None
        and positives >= min_pos
        and auroc is not None
        and auroc > min_auroc
    )

    reasons: list[str] = []
    if info is None:
        reasons.append("no measured validation support for this label")
    else:
        if positives < min_pos:
            reasons.append(f"only {positives} positive example(s) in validation "
                           f"(< {min_pos})")
        if auroc is None:
            reasons.append("AUROC not evaluable (no positives)")
        elif auroc <= min_auroc:
            reasons.append(f"AUROC {auroc} at or below the chance floor {min_auroc}")

    return {
        "state": "measured" if reliable else "not_reliably_measured",
        "reliable": reliable,
        "positives": positives,
        "auroc": auroc,
        "reason": "; ".join(reasons) if reasons else None,
    }


def is_reliable(label: str) -> bool:
    return label_reliability(label)["reliable"]
