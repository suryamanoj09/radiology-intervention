"""Data-minimization sweeper.

Ephemeral demo storage: purge rendered images and analysis JSON older than the
configured TTL. Disk is NOT a durability or security control — this just bounds
how long any image-derived content lingers on the box.
"""

import logging
import threading
import time

from .. import config

logger = logging.getLogger(__name__)


def purge_old(ttl_seconds: int | None = None) -> int:
    ttl = config.STORAGE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    now = time.time()
    removed = 0
    # NOTE: FEEDBACK_DIR and AUDIT_DIR are DELIBERATELY excluded from the sweep.
    # Feedback events are self-contained + PHI-free (no analysis foreign key), so
    # they must survive the storage TTL to be usable for model improvement; the
    # audit trail must be retained. Only image-derived artefacts are TTL'd here.
    for d in (config.UPLOADS_DIR, config.HEATMAPS_DIR, config.ANALYSIS_DIR, config.SEGMENTS_DIR):
        for p in d.glob("*"):
            try:
                if p.is_file() and now - p.stat().st_mtime > ttl:
                    p.unlink()
                    removed += 1
            except OSError:
                pass
    # Prune the in-memory segmentation job dict on the same daemon/cadence so a
    # completed mask's job entry expires alongside its (TTL'd) mask PNGs.
    try:
        from . import seg_store
        seg_store.purge_old_jobs()
    except Exception:
        logger.exception("segment job purge failed")
    if removed:
        logger.info("Storage sweep removed %d expired file(s)", removed)
    return removed


def start_sweeper() -> None:
    """Purge once now (clears stale files from a prior run), then periodically."""
    purge_old()

    def _loop():
        # Sweep at least every 10 min (not just TTL/6 = hourly for a 6h TTL) so a burst
        # of rendered PNGs can't fill the ephemeral disk far ahead of reclamation.
        interval = min(600, max(60, config.STORAGE_TTL_SECONDS // 6))
        while True:
            time.sleep(interval)
            try:
                purge_old()
            except Exception:
                logger.exception("Storage sweep failed")

    threading.Thread(target=_loop, daemon=True, name="storage-sweeper").start()
