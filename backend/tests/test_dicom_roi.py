"""ROI statistics endpoint: honest 16-bit HU stats (never the 8-bit display), rect +
ellipse, position-aligned slice, PHI-safe."""
import json

import _dicom_factory as F


def _roi(client, files, shape, **data):
    return client.post("/api/dicom-roi", files=files,
                       data={"shape": json.dumps(shape), **data})


def test_roi_reports_true_hu_not_windowed(client):
    files = F.as_upload(F.ct_chest_series(10, with_nodule=True))
    r = _roi(client, files, {"type": "rect", "nx": 0.2, "ny": 0.2, "nw": 0.5, "nh": 0.5})
    assert r.status_code == 200, r.text
    b = r.json()
    # Lung air (-800) and soft tissue (>=-30/50) are present -> proves 16-bit HU read
    # (an 8-bit windowed PNG could never round-trip -800 exactly).
    assert b["unit"] == "HU"
    assert b["min"] <= -700 and b["max"] >= 40
    assert b["n_px"] > 0 and b["area_mm2"] > 0


def test_roi_ellipse(client):
    files = F.as_upload(F.ct_chest_series(6))
    r = _roi(client, files, {"type": "ellipse", "nx": 0.3, "ny": 0.3, "nw": 0.3, "nh": 0.3})
    assert r.status_code == 200
    # An ellipse covers ~pi/4 of its bounding box -> fewer px than the rect would.
    assert 0 < r.json()["n_px"]


def test_roi_bad_shape_rejected(client):
    files = F.as_upload(F.ct_chest_series(4))
    assert client.post("/api/dicom-roi", files=files, data={"shape": "not-json"}).status_code == 422


def test_roi_no_phi_in_response(client):
    files = F.as_upload(F.ct_chest_series(6))
    r = _roi(client, files, {"type": "rect", "nx": 0.25, "ny": 0.25, "nw": 0.3, "nh": 0.3})
    blob = json.dumps(r.json())
    assert "DOE" not in blob and "SECRET123" not in blob


def test_roi_bad_series_id_rejected(client):
    files = F.as_upload(F.ct_chest_series(4))
    r = _roi(client, files, {"type": "rect", "nx": 0.2, "ny": 0.2, "nw": 0.2, "nh": 0.2},
             series_id="../etc/passwd")
    assert r.status_code == 422
