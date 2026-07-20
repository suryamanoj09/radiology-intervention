"""Pure feedback -> threshold-proposal logic, shared by the admin-summary endpoint
(routers/feedback.py) and the refit CLI (validation/refit_from_feedback.py).

Turns reviewer confirm/dismiss feedback into per-label FLAG-THRESHOLD proposals — an
operating-point move, not model retraining. Deterministic and bounded; nothing here
mutates state (the caller decides whether to apply a proposal).
"""
import json
from collections import defaultdict
from pathlib import Path

MIN_T, MAX_T = 0.15, 0.90     # keep thresholds in a sane band (banded score space)
STEP = 0.05
MIN_EVENTS = 8                # need enough feedback on a label before moving it
LOW_PRECISION = 0.50          # > half dismissed -> raise
HIGH_PRECISION = 0.85         # mostly confirmed -> may lower


# Feedback from the RESEARCH CADe detectors must NEVER move the production CXR
# classifier's operating point — they are a different, unvalidated label space.
_NON_CXR_SOURCES = frozenset({"ct-detect", "mr-detect"})


def aggregate(events) -> dict:
    """raw_label -> {confirmed, dismissed} counts for the CXR classifier only (thumbs-
    only events and research-CADe votes are excluded)."""
    agg = defaultdict(lambda: {"confirmed": 0, "dismissed": 0})
    for e in events:
        if e.get("image_source") in _NON_CXR_SOURCES:
            continue  # research CADe feedback never refits the production CXR thresholds
        lbl = e.get("raw_label") or e.get("label")
        ev = e.get("event")
        if lbl and ev in ("confirmed", "dismissed"):
            agg[lbl][ev] += 1
    return dict(agg)


def propose_thresholds(events, current: dict, default_threshold: float) -> dict:
    """{label: {from, to, n, precision, reason}} for labels whose threshold should move."""
    proposals = {}
    for lbl, c in sorted(aggregate(events).items()):
        n = c["confirmed"] + c["dismissed"]
        if n < MIN_EVENTS:
            continue
        precision = c["confirmed"] / n
        cur = float(current.get(lbl, default_threshold))
        new = cur
        if precision < LOW_PRECISION:
            new = min(MAX_T, round(cur + STEP, 3))
        elif precision >= HIGH_PRECISION:
            new = max(MIN_T, round(cur - STEP, 3))
        if new != cur:
            proposals[lbl] = {"from": cur, "to": new, "n": n, "precision": round(precision, 3),
                              "reason": "raise (over-flagging: reviewers dismiss it)" if new > cur
                              else "lower (reliable: reviewers confirm it)"}
    return proposals


def events_from_rows(rows) -> list:
    """Map storage-adapter FeedbackEvent rows (store.list_feedback() dicts) into the
    event-dict shape aggregate()/summary()/propose_thresholds() consume, so the DB path
    and the file path (load_events) are interchangeable. Pure — no I/O, no app imports.

    The row's `action` column holds the event kind (confirmed|dismissed|thumb_*); the
    `label` column holds the raw pathology label; `image_source` preserves the CXR vs
    research-CADe split so the exclusion in aggregate() applies identically off the DB."""
    out = []
    for r in rows:
        out.append({
            "raw_label": r.get("label"),
            "label": r.get("label"),
            "event": r.get("action"),
            "image_source": r.get("image_source"),
            "raw_score": r.get("raw_score"),
        })
    return out


def load_events(path: Path) -> list:
    events = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def summary(events, current: dict, default_threshold: float) -> dict:
    """Admin view: per-label counts + precision + current/proposed threshold."""
    agg = aggregate(events)
    proposals = propose_thresholds(events, current, default_threshold)
    rows = []
    for lbl in sorted(agg):
        c = agg[lbl]
        n = c["confirmed"] + c["dismissed"]
        rows.append({
            "label": lbl, "confirmed": c["confirmed"], "dismissed": c["dismissed"],
            "precision": round(c["confirmed"] / n, 3) if n else None,
            "current_threshold": round(float(current.get(lbl, default_threshold)), 3),
            "proposed_threshold": proposals.get(lbl, {}).get("to"),
            "reason": proposals.get(lbl, {}).get("reason"),
        })
    return {"n_events": len(events), "labels": rows, "n_proposals": len(proposals)}
