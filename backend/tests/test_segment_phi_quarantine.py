"""Segmentation respects the ingest spine: Secondary-Capture files are quarantined
BEFORE decode, identifiers are scrubbed, and no PHI reaches the response or the
opaque mask filenames."""
import json

import _dicom_factory as F


def test_secondary_capture_is_dropped_before_decode(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    # one real CT series + one SC screenshot; the SC must be quarantined, CT segmented.
    up = F.as_upload(F.ct_series(4)) + [("files", ("shot.dcm", F.secondary_capture(), "application/dicom"))]
    r = client.post("/api/segment", files=up)
    assert r.status_code == 200, r.text
    res = F.poll_segment(client, r.json()["job_id"])
    assert res["status"] == "done"
    assert res["n_quarantined"] >= 1
    assert res["identifiers_removed"] >= 2  # PatientName + PatientID at least


def test_no_phi_in_response_or_mask_urls(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    r = client.post("/api/segment", files=F.as_upload(F.ct_series(4)))
    res = F.poll_segment(client, r.json()["job_id"])
    blob = json.dumps(res)
    assert "DOE" not in blob and "SECRET123" not in blob and "JOHN" not in blob
    for u in res["mask_urls"]:
        # opaque token filenames only — no patient string in the path.
        assert "DOE" not in u and "SECRET" not in u


def test_pure_secondary_capture_upload_yields_no_segmentation(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    up = [("files", ("shot.dcm", F.secondary_capture(), "application/dicom"))]
    # 422 (modality guard sees 'OT', not CT) — never renders/segments the SC pixels.
    assert client.post("/api/segment", files=up).status_code == 422
