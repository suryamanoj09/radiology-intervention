"""In-process async job store for the anatomy-overlay segmentation (opt-in AI).

Mirrors the localizer._jobs idiom: a module-level dict + lock, plus a single run
lock so a minutes-long, multi-GB segmentation never fans out (concurrency 1). Jobs
are keyed by content-hash+params, so re-submitting the SAME volume+params is an
instant cache hit and never recomputes. Per-process / single-container (lost on
restart) — same posture as localizer._jobs; documented in docs/SEGMENT_OVERLAY.md.
"""
import logging
import threading
import time

from .. import config

logger = logging.getLogger(__name__)

_jobs: dict[str, dict] = {}      # job_id -> {state, result?, detail?, created, work?}
_jobs_lock = threading.Lock()
_run_lock = threading.Lock()     # concurrency 1: one segmentation at a time


class QueueFull(Exception):
    """The bounded segmentation queue is saturated (router -> 429)."""


def submit(job_id: str, work, meta: dict | None = None) -> tuple[str, bool]:
    """Register a job keyed by `job_id` (== content-hash+params). Returns
    (job_id, is_new). A job already queued/running/done is a CACHE HIT (is_new
    False) and never re-runs. `meta` (e.g. {'modality': 'CT'}) is remembered so the
    poll can build a modality-correct response even before the work completes.
    Raises QueueFull if too many jobs are pending."""
    now = time.time()
    with _jobs_lock:
        existing = _jobs.get(job_id)
        if existing and existing.get("state") in ("queued", "running", "done"):
            return job_id, False
        pending = sum(1 for j in _jobs.values() if j.get("state") in ("queued", "running"))
        if pending >= config.SEGMENT_QUEUE_MAX:
            raise QueueFull("segmentation queue is saturated")
        _jobs[job_id] = {"state": "queued", "result": None, "detail": None,
                         "created": now, "work": work, "meta": dict(meta or {})}
    return job_id, True


def status(job_id: str) -> dict:
    """Locked snapshot: {state in unknown|queued|running|done|error, result?, detail?, meta}."""
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j:
            return {"state": "unknown", "result": None, "detail": None, "meta": {}}
        return {"state": j["state"], "result": j.get("result"),
                "detail": j.get("detail"), "meta": dict(j.get("meta") or {})}


def run(job_id: str) -> None:
    """Background-task body. Holds _run_lock across the whole run (concurrency 1) so a
    heavy job never blocks the event loop or fans out. Releases the captured closure
    (and its file blobs) when done."""
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j or j["state"] != "queued":
            return
        work = j.get("work")
        j["state"] = "running"
    with _run_lock:
        try:
            result = work() if work else None
            state, detail = "done", None
        except Exception:
            logger.exception("segmentation job %s failed", job_id)
            result, state, detail = None, "error", "segmentation failed"
        with _jobs_lock:
            jj = _jobs.get(job_id)
            if jj is not None:
                jj.update(state=state, result=result, detail=detail, work=None)


def purge_old_jobs(ttl: int | None = None) -> int:
    """Drop jobs older than the TTL (called by the storage sweeper daemon)."""
    ttl = config.SEGMENT_JOB_TTL_SECONDS if ttl is None else ttl
    now = time.time()
    with _jobs_lock:
        stale = [k for k, j in _jobs.items() if now - j.get("created", now) > ttl]
        for k in stale:
            _jobs.pop(k, None)
    return len(stale)


def warm_up() -> None:
    """No-op unless enabled (parity with localizer.warm_up)."""
    return
