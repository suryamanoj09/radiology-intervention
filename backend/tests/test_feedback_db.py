"""Feedback persistence through the storage-adapter seam.

Two backends, one behaviour contract:
  * DATABASE_URL SET   -> each /api/feedback event is a FeedbackEvent row, and
    /api/feedback/summary (+ the refit inputs) are computed from the DB.
  * DATABASE_URL UNSET -> byte-for-byte the original feedback.jsonl file path.

PHI-safety is preserved: only the de-identified image hash, the pathology label, the
confirm/dismiss kind, the raw score and the source enum reach the row.
"""
import json

import pytest

from app import config, db
from app.models.schemas import FeedbackEvent
from app.routers import feedback as feedback_router
from app.services import feedback_stats


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def db_on(tmp_path, monkeypatch):
    """Enable the opt-in DB on a throwaway SQLite file for the duration of a test."""
    url = f"sqlite:///{(tmp_path / 'fb.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)   # auto-restored by monkeypatch on teardown
    db.reset_engine_for_tests()
    assert db.is_enabled() and db.init_db() is True
    yield
    db.reset_engine_for_tests()               # dispose the engine before the file vanishes


@pytest.fixture()
def db_off(tmp_path, monkeypatch):
    """DB disabled + feedback.jsonl redirected to a temp dir (never touch the real log)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.reset_engine_for_tests()
    monkeypatch.setattr(config, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(feedback_router, "_FEEDBACK_FILE", tmp_path / "feedback.jsonl")
    assert db.is_enabled() is False
    yield tmp_path
    db.reset_engine_for_tests()


def _confirm(label, source="nih", score=0.6):
    return FeedbackEvent(event="confirmed", image_sha256="a" * 64, image_source=source,
                         raw_label=label, raw_score=score)


def _dismiss(label, source="nih", score=0.4):
    return FeedbackEvent(event="dismissed", image_sha256="b" * 64, image_source=source,
                         raw_label=label, raw_score=score)


# --------------------------------------------------------------------------- #
# DB ON                                                                        #
# --------------------------------------------------------------------------- #
def test_db_on_persists_each_event_as_a_row(db_on):
    from app.services import store

    feedback_router.submit_feedback(_confirm("Pneumonia"))
    feedback_router.submit_feedback(_dismiss("Pneumonia"))

    rows = store.list_feedback()
    assert len(rows) == 2
    r = rows[0]
    # PHI-free shape: hash + label + kind + score + source only, plus server-set id/ts.
    assert r["image_hash"] == "a" * 64
    assert r["label"] == "Pneumonia"
    assert r["action"] == "confirmed"       # event kind lands in the `action` column
    assert r["raw_score"] == 0.6
    assert r["image_source"] == "nih"
    assert r["reviewer"] is None
    assert r["created_at"] is not None


def test_db_on_summary_counts_from_db(db_on):
    for _ in range(3):
        feedback_router.submit_feedback(_confirm("Effusion"))
    for _ in range(2):
        feedback_router.submit_feedback(_dismiss("Effusion"))

    out = feedback_router.feedback_summary()
    assert out["n_events"] == 5
    row = next(r for r in out["labels"] if r["label"] == "Effusion")
    assert row["confirmed"] == 3 and row["dismissed"] == 2
    assert row["precision"] == round(3 / 5, 3)


def test_db_on_summary_matches_file_summary_exactly(db_on):
    # The DB summary must equal what the pure file-path aggregator would produce for the
    # same events -> the two backends are drop-in interchangeable.
    events = ([_confirm("Nodule")] * 6) + ([_dismiss("Nodule")] * 2)
    for e in events:
        feedback_router.submit_feedback(e)

    db_summary = feedback_router.feedback_summary()

    file_events = [{"raw_label": e.raw_label, "event": e.event,
                    "image_source": e.image_source} for e in events]
    file_summary = feedback_stats.summary(file_events, config.LABEL_THRESHOLDS,
                                          config.FINDING_THRESHOLD)
    assert db_summary["labels"] == file_summary["labels"]
    assert db_summary["n_proposals"] == file_summary["n_proposals"]


def test_db_on_frequently_dismissed_label_raises_threshold(db_on):
    # 2 confirmed / 8 dismissed -> low precision -> summary proposes a HIGHER threshold.
    for _ in range(2):
        feedback_router.submit_feedback(_confirm("Mass"))
    for _ in range(8):
        feedback_router.submit_feedback(_dismiss("Mass"))

    row = next(r for r in feedback_router.feedback_summary()["labels"]
               if r["label"] == "Mass")
    assert row["proposed_threshold"] is not None
    assert row["proposed_threshold"] > row["current_threshold"]
    assert "raise" in row["reason"]


def test_db_on_research_cade_feedback_excluded_from_cxr_summary(db_on):
    # A research-CADe (ct-detect) vote is persisted but must NOT move a CXR label's
    # operating point — the exclusion in aggregate() has to work off the DB too.
    for _ in range(10):
        feedback_router.submit_feedback(_dismiss("CadeCandidate", source="ct-detect"))
    feedback_router.submit_feedback(_confirm("Pneumothorax"))

    out = feedback_router.feedback_summary()
    labels = {r["label"] for r in out["labels"]}
    assert "CadeCandidate" not in labels          # research CADe never enters CXR refit
    assert "Pneumothorax" in labels
    assert out["n_events"] == 11                   # all events counted, CADe still excluded


def test_db_on_does_not_write_the_feedback_file(db_on, monkeypatch, tmp_path):
    # With the DB enabled, the legacy jsonl sink is never touched.
    fpath = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(config, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(feedback_router, "_FEEDBACK_FILE", fpath)
    feedback_router.submit_feedback(_confirm("Cardiomegaly"))
    assert not fpath.exists()


# --------------------------------------------------------------------------- #
# DB OFF (unchanged legacy behaviour)                                          #
# --------------------------------------------------------------------------- #
def test_db_off_appends_to_file_and_summarizes_from_file(db_off):
    tmp = db_off
    feedback_router.submit_feedback(_confirm("Atelectasis"))
    feedback_router.submit_feedback(_dismiss("Atelectasis"))

    fpath = tmp / "feedback.jsonl"
    assert fpath.exists()
    lines = [json.loads(l) for l in fpath.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    # The rich, self-contained file record is preserved exactly as before.
    assert lines[0]["event"] == "confirmed" and lines[0]["raw_label"] == "Atelectasis"
    assert lines[0]["image_sha256"] == "a" * 64

    out = feedback_router.feedback_summary()
    row = next(r for r in out["labels"] if r["label"] == "Atelectasis")
    assert row["confirmed"] == 1 and row["dismissed"] == 1
    assert out["n_events"] == 2


def test_db_off_never_calls_the_store_adapter(db_off, monkeypatch):
    # Route stays entirely on the file path; the store's not-yet-wired fallback
    # (NotImplementedError) must never be reached when the DB is disabled.
    from app.services import store

    def _boom(*a, **k):
        raise AssertionError("store must not be used when DATABASE_URL is unset")

    monkeypatch.setattr(store, "add_feedback", _boom)
    monkeypatch.setattr(store, "list_feedback", _boom)
    feedback_router.submit_feedback(_confirm("Edema"))
    feedback_router.feedback_summary()   # both must complete without hitting the store
