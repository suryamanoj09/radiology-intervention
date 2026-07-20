"""Segmentation is OPT-IN: default OFF, and when off the endpoint 503s WITHOUT
touching the provider."""
import _dicom_factory as F
from app import config


def test_default_flags_are_off():
    # The shipped default is opt-in for BOTH modalities.
    import importlib
    import os
    # Re-read the raw env default the module was built from: both must be false unless
    # explicitly enabled. (conftest does not set them.)
    assert os.getenv("SEGMENT_ENABLED") in (None, "0", "false", "")
    assert os.getenv("MR_SEGMENT_ENABLED") in (None, "0", "false", "")
    assert config.SEGMENT_ENABLED is False
    assert config.MR_SEGMENT_ENABLED is False


def test_ct_endpoint_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "SEGMENT_ENABLED", False)
    called = {"n": 0}
    from app.services import segmentation
    orig = segmentation.segment
    monkeypatch.setattr(segmentation, "segment", lambda *a, **k: called.__setitem__("n", called["n"] + 1) or orig(*a, **k))
    r = client.post("/api/segment", files=F.as_upload(F.ct_series(2)))
    assert r.status_code == 503
    assert called["n"] == 0, "provider was invoked despite the feature flag being off"


def test_mr_endpoint_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "MR_SEGMENT_ENABLED", False)
    r = client.post("/api/mr-segment", files=F.as_upload(F.mr_series(2)))
    assert r.status_code == 503


def test_enabled_flag_lets_it_run(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    r = client.post("/api/segment", files=F.as_upload(F.ct_series(2)))
    assert r.status_code == 200
