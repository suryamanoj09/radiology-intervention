"""Close the feedback loop — turn reviewer confirm/dismiss feedback into updated
per-label FLAG THRESHOLDS.

This is an OPERATING-POINT move, NOT model retraining (which would need a GPU and a
labelled dataset). It reads the PHI-free, self-contained events that /api/feedback
writes to feedback.jsonl and, per raw label, nudges the flag threshold:

  * many DISMISSES (low reviewer precision)  -> RAISE the threshold (flag less often);
  * consistently CONFIRMED (high precision)   -> allow a small DROP (flag a touch more).

Everything is transparent, deterministic, and bounded. It writes a PROPOSED file for a
human to review before deployment — it never silently overwrites the live thresholds.
Run:  python -m validation.refit_from_feedback  [--apply]
"""
import argparse
import json
import sys
from pathlib import Path

# Ensure `app` is importable when run as `python -m validation.refit_from_feedback`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The pure logic lives in the shared service so the admin endpoint and this CLI agree.
from app.services.feedback_stats import (  # noqa: E402
    aggregate, events_from_rows, load_events, propose_thresholds)


def main():
    from app import config, db

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--feedback", default=None,
                    help="path to a feedback.jsonl (default: the DB when DATABASE_URL is "
                         "set, else the standard feedback.jsonl file)")
    ap.add_argument("--out", default=str(config.BASE_DIR / "calibration.proposed.json"))
    ap.add_argument("--apply", action="store_true",
                    help="write directly to the live calibration.json (default: propose only)")
    args = ap.parse_args()

    # Source of truth: an explicit --feedback file wins; otherwise the DB if enabled,
    # else the standard file — so the refit reads exactly what /api/feedback wrote.
    if args.feedback:
        events = load_events(Path(args.feedback))
    elif db.is_enabled():
        from app.services import store
        events = events_from_rows(store.list_feedback())
    else:
        events = load_events(config.FEEDBACK_DIR / "feedback.jsonl")
    current = config.LABEL_THRESHOLDS
    proposals = propose_thresholds(events, current, config.FINDING_THRESHOLD)

    print(f"Read {len(events)} feedback event(s); {len(proposals)} threshold change(s) proposed.")
    for lbl, p in proposals.items():
        print(f"  {lbl:22} {p['from']:.2f} -> {p['to']:.2f}  "
              f"(n={p['n']}, precision={p['precision']}) — {p['reason']}")

    merged = dict(current)
    for lbl, p in proposals.items():
        merged[lbl] = p["to"]
    target = config.CALIBRATION_PATH if args.apply else Path(args.out)
    payload = {"thresholds": merged,
               "meta": {"source": "feedback-refit", "n_events": len(events),
                        "n_changed": len(proposals)}}
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"{'Applied to' if args.apply else 'Proposed thresholds written to'} {target}")


if __name__ == "__main__":
    main()
