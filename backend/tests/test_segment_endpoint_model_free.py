"""The segment endpoints return anatomy labels + geometry ONLY — no diagnosis-shaped
field anywhere in the JSON, and the disclaimer states the boundary. Classical
(torch-free) path only."""
import _dicom_factory as F

_FORBIDDEN = ("findings", "probability", "impression", "severity", "malignancy",
              "abnormal", "diagnosis", "heatmap_url", "triage", "flagged",
              "lesion", "tumor", "score")


def _keys(o):
    out = []
    if isinstance(o, dict):
        for k, v in o.items():
            out.append(k)
            out += _keys(v)
    elif isinstance(o, list):
        for v in o:
            out += _keys(v)
    return out


def test_ct_segment_response_is_model_free(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    r = client.post("/api/segment", files=F.as_upload(F.ct_series(4)))
    assert r.status_code == 200, r.text
    res = F.poll_segment(client, r.json()["job_id"])
    assert res["status"] == "done", res
    # Not one diagnosis-shaped KEY anywhere (incl. every regions[] item).
    for k in _keys(res):
        assert not any(b in k.lower() for b in _FORBIDDEN), f"leaked key {k}"
    assert res["regions"], "classical CT labeler produced no regions"
    assert res["structure_count"] == len(res["regions"])
    # Region labels are anatomy nouns; the disclaimer states the boundary.
    for reg in res["regions"]:
        assert not any(b in reg["label"].lower() for b in _FORBIDDEN)
    assert "not a diagnosis" in res["disclaimer"] and "not a medical device" in res["disclaimer"]
    assert res["intensity_unit"] == "HU" and res["modality"] == "CT"


def test_mr_segment_response_is_model_free_and_au(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    r = client.post("/api/mr-segment", files=F.as_upload(F.mr_series(4)))
    assert r.status_code == 200, r.text
    res = F.poll_segment(client, r.json()["job_id"])
    assert res["status"] == "done", res
    for k in _keys(res):
        assert not any(b in k.lower() for b in _FORBIDDEN), f"leaked key {k}"
    assert res["intensity_unit"] == "a.u." and res["modality"] == "MR"
    # MR regions must never claim HU.
    for reg in res["regions"]:
        assert reg["hu_range"] is None and reg["intensity_unit"] == "a.u."


def test_response_carries_masks_and_provenance(client, monkeypatch):
    F.enable_segmentation(monkeypatch)
    r = client.post("/api/segment", files=F.as_upload(F.ct_series(4)))
    res = F.poll_segment(client, r.json()["job_id"])
    assert res["mask_urls"] and len(res["mask_urls"]) == res["n_slices"]
    assert all(u.startswith("/static/segments/") for u in res["mask_urls"])
    assert "classical-hu-threshold" in res["model"]
    assert "not a finding" in (res["provenance"] or "")
