"""T9: feedback events are self-contained (survive the storage TTL) and PHI-free
(no free-text identifier field; every string is enum/hash/short-label, capped)."""
from app import config
from app.models.schemas import FeedbackEvent


def test_feedback_event_is_self_contained_no_analysis_fk():
    e = FeedbackEvent(event="dismissed", image_sha256="a" * 64, image_source="nih",
                      raw_label="Fracture", raw_score=0.51, calibration_state="insufficient_data",
                      heatmap_state="not_localized")
    d = e.model_dump()
    assert "analysis_id" not in d and "image_id" not in d  # no foreign key into TTL'd storage
    assert d["event"] == "dismissed" and d["raw_label"] == "Fracture"


def test_string_fields_are_length_capped_no_smuggling():
    import pytest
    from pydantic import ValidationError
    # A too-long value in any free-ish string field is rejected -> a 4KB identifier
    # blob cannot be smuggled through the feedback sink.
    for field, cap in [("raw_label", 64), ("display_label", 80),
                       ("model_note", 280), ("image_source", 32)]:
        with pytest.raises(ValidationError):
            FeedbackEvent(**{field: "x" * (cap + 50)})
    # A within-cap value is accepted.
    assert FeedbackEvent(raw_label="Pneumothorax").raw_label == "Pneumothorax"


def test_confirmed_and_dismissed_are_valid_events():
    for ev in ("confirmed", "dismissed", "thumb_up", "thumb_down"):
        assert FeedbackEvent(event=ev).event == ev


def test_feedback_dir_is_ttl_exempt():
    from app.services import storage
    # The sweeper enumerates only image-derived dirs; feedback + audit are excluded.
    import inspect
    src = inspect.getsource(storage.purge_old)
    assert "FEEDBACK_DIR" not in src.split("for d in")[1].split(")")[0]
