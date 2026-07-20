"""Modality is hard-guarded (header-only, before pixel decode): /api/segment is
CT-only, /api/mr-segment is MR-only — the inverse of the CXR path, so a head CT can
never be silently MR-segmented and vice versa."""
import _dicom_factory as F


def test_ct_endpoint_refuses_mr(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    r = client.post("/api/segment", files=F.as_upload(F.mr_series(3)))
    assert r.status_code == 422, r.text
    assert "CT only" in r.json()["detail"]


def test_mr_endpoint_refuses_ct(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    r = client.post("/api/mr-segment", files=F.as_upload(F.ct_series(3)))
    assert r.status_code == 422, r.text
    assert "MR only" in r.json()["detail"]


def test_secondary_capture_only_is_rejected(client, monkeypatch):
    # An 'OT' Secondary-Capture (no CT/MR) satisfies neither endpoint's modality.
    F.enable_segmentation(monkeypatch)
    up = [("files", ("shot.dcm", F.secondary_capture(), "application/dicom"))]
    assert client.post("/api/segment", files=up).status_code == 422
    assert client.post("/api/mr-segment", files=up).status_code == 422


def test_correct_modality_is_accepted(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    assert client.post("/api/segment", files=F.as_upload(F.ct_series(3))).status_code == 200
    assert client.post("/api/mr-segment", files=F.as_upload(F.mr_series(3))).status_code == 200
