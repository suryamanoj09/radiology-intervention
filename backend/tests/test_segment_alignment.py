"""Overlay/series alignment + the verification-round fixes: segment the REQUESTED
series (not always the largest), return series_id + slice_positions, classical stays
available under whitelist narrowing, and multi-frame z-spacing is not faked."""
import numpy as np
import pydicom
from pydicom.uid import generate_uid

import _dicom_factory as F
from app import config
from app.services import dicom_utils


def test_build_seg_volume_returns_series_id_and_positions():
    files = F.ct_series(5)
    v = dicom_utils.build_seg_volume(files)
    assert v["series_id"] and isinstance(v["series_id"], str)
    assert v["slice_positions"] and len(v["slice_positions"]) == v["n_slices"]
    # positions are sorted ascending (geometric order)
    assert v["slice_positions"] == sorted(v["slice_positions"])


def test_build_seg_volume_segments_requested_series_not_largest():
    # small series A (2 slices) + large series B (6 slices). Requesting A must segment A.
    a = F.ct_series(2)
    b = F.ct_series(6)
    sid_a = dicom_utils._opaque(str(pydicom.dcmread(__import__("io").BytesIO(a[0])).SeriesInstanceUID))
    v = dicom_utils.build_seg_volume(a + b, series_id=sid_a)
    assert v["series_id"] == sid_a
    assert v["n_slices"] == 2  # the requested (smaller) series, not the 6-slice one


def test_endpoint_reports_series_id(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    r = client.post("/api/segment", files=F.as_upload(F.ct_series(4)))
    res = F.poll_segment(client, r.json()["job_id"])
    assert res["series_id"] and res["slice_positions"]
    assert len(res["slice_positions"]) == res["n_slices"]


def test_dicom_view_returns_slice_positions(client, monkeypatch):
    # The CT viewer path must expose ordered positions so the overlay aligns by position.
    r = client.post("/api/dicom-view", files=F.as_upload(F.ct_series(4)))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("slice_positions") and len(body["slice_positions"]) == body["n_slices_shown"]


def test_classical_survives_whitelist_narrowing(monkeypatch):
    # An operator narrowing the whitelist to only heavy tasks must NOT disable the
    # weight-free classical baseline (defect #3 from the verification round).
    monkeypatch.setattr(config, "TOTALSEG_TASK_WHITELIST", frozenset({"total"}))
    config.assert_task_allowed("classical-hu-threshold")   # must not raise
    config.assert_task_allowed("classical-mr-intensity")


def test_classical_is_always_in_active_whitelist():
    assert "classical-hu-threshold" in config.TOTALSEG_TASK_WHITELIST
    assert "classical-mr-intensity" in config.TOTALSEG_TASK_WHITELIST
