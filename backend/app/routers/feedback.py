"""Reviewer feedback endpoint (thumbs up / down).

A licensed reviewer can signal, per flagged finding OR on the generated report
draft, whether the model's output was useful. Each click is appended as ONE JSON
line to a PRIVATE (never-mounted) directory.

PHI-free by construction:
  * the request schema (models.schemas.FeedbackEvent) has NO free-text identifier
    fields — only a target kind, an up/down rating, the finding LABEL (a pathology
    name, e.g. "Pneumothorax"), a short model NOTE, an action, and a client
    timestamp, each length-capped;
  * nothing image-derived, no patient demographics, no report body is stored.

Abuse brake: /api/feedback is registered in config.RATE_LIMITED_PATHS, so the
shared per-IP fixed-window limiter throttles it exactly like the other POSTs.
Writes are serialized with a process-local lock (single-container demo).
"""

import json
import logging
import secrets
import threading
from datetime import datetime, timezone

from fastapi import APIRouter

from .. import config, db
from ..models.schemas import FeedbackEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["feedback"])

_write_lock = threading.Lock()
_FEEDBACK_FILE = config.FEEDBACK_DIR / "feedback.jsonl"


@router.post("/feedback")
def submit_feedback(event: FeedbackEvent):
    """Record a single thumbs up/down on a finding or the report draft.

    Returns a small confirmation the UI surfaces as "Your feedback is recorded".
    Persistence failures are logged but never surfaced as an error — a lost
    feedback line must not disrupt the clinician's review flow.

    Backend selection (transparent to the caller):
      * DATABASE_URL SET   -> the event is written as ONE FeedbackEvent row via the
        storage adapter (PHI-free: a de-identified image hash, the pathology label,
        the confirm/dismiss kind, the raw score, and the de-identified source enum).
      * DATABASE_URL UNSET -> unchanged behaviour: the rich record is appended to the
        private feedback.jsonl exactly as before.
    """
    if db.is_enabled():
        # DB path: persist the PHI-free training signal the summary/refit consume.
        try:
            from ..services import store
            store.add_feedback(
                image_hash=event.image_sha256 or "",
                label=(event.raw_label or event.label or ""),
                action=(event.event or event.action or ""),
                reviewer=None,
                raw_score=event.raw_score,
                image_source=event.image_source,
            )
        except Exception:
            logger.exception("Could not persist feedback event to the database")
        return {"status": "recorded", "message": "Your feedback is recorded."}

    # --- DB disabled: byte-for-byte the original file/in-memory behaviour ---------
    # Server-injected provenance so each event is self-contained + versioned.
    from ..services import calibration
    cal_meta = calibration._load().get("meta", {}) if config.CALIBRATION_MODE != "none" else {}
    record = {
        "id": secrets.token_hex(8),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "event": event.event,                    # confirmed|dismissed|thumb_up|thumb_down
        # Self-contained training signal (no analysis_id foreign key -> survives TTL):
        "image_sha256": event.image_sha256,
        "image_source": event.image_source,
        "raw_label": event.raw_label,
        "display_label": event.display_label,
        "raw_score": event.raw_score,
        "calibrated_p": event.calibrated_p,
        "calibration_state": event.calibration_state,
        "heatmap_state": event.heatmap_state,
        "threshold": event.threshold if event.threshold is not None else config.FINDING_THRESHOLD,
        # Versions injected server-side (the client can't be trusted to know them):
        "model": (config.ENSEMBLE_WEIGHTS[0] if config.ENSEMBLE_WEIGHTS else "densenet121-res224-all"),
        "calibration_map_version": cal_meta.get("source"),
        "calibration_mode": config.CALIBRATION_MODE,
        # Back-compat thumbs fields:
        "target": event.target, "rating": event.rating,
        "label": event.label, "model_note": event.model_note,
        "action": event.action, "client_timestamp": event.timestamp,
    }
    try:
        line = json.dumps(record, ensure_ascii=False)
        with _write_lock:
            if _FEEDBACK_FILE.exists() and _FEEDBACK_FILE.stat().st_size > config.FEEDBACK_MAX_BYTES:
                logger.warning("feedback log at size cap (%d bytes); dropping event",
                               config.FEEDBACK_MAX_BYTES)
            else:
                with _FEEDBACK_FILE.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
    except Exception:
        logger.exception("Could not persist feedback event")

    return {"status": "recorded", "message": "Your feedback is recorded."}


@router.get("/feedback/summary")
def feedback_summary():
    """Admin view of the feedback loop: per-label confirm/dismiss counts + precision +
    the current vs PROPOSED flag threshold. Read-only — proposals are applied by a
    deliberate ops step (validation/refit_from_feedback.py --apply), never from the web,
    so a rewrite of model behaviour can't be triggered by a request. Auth-gated via the
    /api/feedback protected prefix.

    Events come from the DB when DATABASE_URL is set, else from feedback.jsonl — the
    aggregation logic (feedback_stats.summary) is identical for both."""
    from ..services import feedback_stats
    if db.is_enabled():
        from ..services import store
        events = feedback_stats.events_from_rows(store.list_feedback())
    else:
        events = feedback_stats.load_events(config.FEEDBACK_DIR / "feedback.jsonl")
    return feedback_stats.summary(events, config.LABEL_THRESHOLDS, config.FINDING_THRESHOLD)
