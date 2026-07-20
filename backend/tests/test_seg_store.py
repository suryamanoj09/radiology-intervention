"""The async job store: content-hash cache dedup (same key never re-runs), TTL
purge, and unknown-id status."""
import time

import pytest

from app.services import seg_store


@pytest.fixture(autouse=True)
def _clear_jobs():
    seg_store._jobs.clear()
    yield
    seg_store._jobs.clear()


def test_submit_dedupes_same_key():
    calls = {"n": 0}

    def work():
        calls["n"] += 1
        return {"ok": True}

    jid, is_new = seg_store.submit("k" * 32, work)
    assert is_new is True
    seg_store.run(jid)
    assert seg_store.status(jid)["state"] == "done"
    # Re-submitting the SAME key is a cache hit — never a new job, never re-runs.
    jid2, is_new2 = seg_store.submit("k" * 32, work)
    assert jid2 == jid and is_new2 is False
    seg_store.run(jid2)  # no-op (state already done)
    assert calls["n"] == 1


def test_unknown_job_status():
    st = seg_store.status("deadbeef" * 4)
    assert st["state"] == "unknown" and st["result"] is None


def test_error_state_on_work_exception():
    def boom():
        raise RuntimeError("kaboom")

    jid, _ = seg_store.submit("e" * 32, boom)
    seg_store.run(jid)
    st = seg_store.status(jid)
    assert st["state"] == "error" and st["result"] is None


def test_queue_full_raises():
    from app import config
    # Fill the queue with pending (never-run) jobs up to the cap.
    for i in range(config.SEGMENT_QUEUE_MAX):
        seg_store.submit(f"{i:032d}", lambda: None)
    with pytest.raises(seg_store.QueueFull):
        seg_store.submit("z" * 32, lambda: None)


def test_purge_old_jobs():
    jid, _ = seg_store.submit("p" * 32, lambda: {"ok": 1})
    seg_store.run(jid)
    # Age the job past the TTL and purge.
    seg_store._jobs[jid]["created"] = time.time() - 10_000_000
    removed = seg_store.purge_old_jobs(ttl=1)
    assert removed >= 1
    assert seg_store.status(jid)["state"] == "unknown"


def test_meta_is_remembered_for_poll():
    jid, _ = seg_store.submit("m" * 32, lambda: {"ok": 1}, meta={"modality": "MR"})
    assert seg_store.status(jid)["meta"]["modality"] == "MR"
