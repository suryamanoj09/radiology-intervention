"""Research CADe (disease-candidate) detection: deterministic classical detectors,
opt-in + abstain + RESEARCH disclaimer, modality guard, PHI-safe, and every candidate
framed as unvalidated."""
import json

import numpy as np

import _dicom_factory as F
from app import config
from app.services import ct_cade


def _enable(monkeypatch):
    monkeypatch.setattr(config, "CT_DETECT_ENABLED", True)


def _phantom(nodule=True):
    hu = np.full((20, 64, 64), -1000, np.int16)
    hu[:, 8:56, 8:56] = -30
    hu[3:17, 16:48, 16:30] = -800
    hu[3:17, 16:48, 34:48] = -800
    if nodule:
        hu[8:13, 26:34, 20:26] = 50
    return {"is_ct": True, "hu": hu, "spacing_mm": (1.0, 1.0, 2.0)}


def test_detector_finds_nodule_and_is_deterministic():
    v = _phantom(nodule=True)
    c1 = ct_cade.detect(v)
    c2 = ct_cade.detect(v)
    assert c1 == c2, "detector must be deterministic"
    assert any(c["kind"] == "pulmonary nodule" for c in c1)
    nod = next(c for c in c1 if c["kind"] == "pulmonary nodule")
    assert 3.0 <= nod["est_max_mm"] <= 30.0
    assert 0.0 <= nod["score"] <= 1.0


def test_detector_quiet_on_clean_lungs():
    assert ct_cade.detect(_phantom(nodule=False)) == []  # no nodule -> no nodule candidate


def test_detector_skips_non_ct():
    v = _phantom(); v["is_ct"] = False
    assert ct_cade.detect(v) == []


def test_endpoint_503_when_disabled(client):
    r = client.post("/api/ct-detect", files=F.as_upload(F.ct_chest_series(6)))
    assert r.status_code == 503


def test_endpoint_detects_and_is_research_framed(client, monkeypatch):
    _enable(monkeypatch)
    r = client.post("/api/ct-detect", files=F.as_upload(F.ct_chest_series(14, with_nodule=True)))
    assert r.status_code == 200, r.text
    res = F.poll_detect(client, r.json()["job_id"])
    assert res["status"] == "done", res
    # Research framing is structural, not optional.
    assert res["research_only"] is True and res["validated"] is False
    d = res["disclaimer"].lower()
    assert "research use only" in d and "not a diagnosis" in d and "not a medical device" in d
    assert res["slice_urls"] and len(res["slice_urls"]) == res["n_slices"]
    # A nodule candidate is surfaced, unvalidated.
    assert res["candidate_count"] >= 1
    for c in res["candidates"]:
        assert c["validated"] is False
        assert "confirm" in c["disposition"].lower()
        # #9 — the response exposes a non-probabilistic salience (renamed from `score`),
        # never a 0-1 probability-shaped field, plus a band + boolean the UI renders.
        assert "score" not in c
        assert 0.0 <= c["salience"] <= 1.0
        assert c["salience_band"] in ("low", "medium", "high")
        assert c["detected"] is True and c["is_probability"] is False


def test_endpoint_modality_guard_refuses_mr(client, monkeypatch):
    _enable(monkeypatch)
    r = client.post("/api/ct-detect", files=F.as_upload(F.mr_series(4)))
    assert r.status_code == 422


def test_endpoint_no_phi_leak(client, monkeypatch):
    _enable(monkeypatch)
    r = client.post("/api/ct-detect", files=F.as_upload(F.ct_chest_series(8)))
    res = F.poll_detect(client, r.json()["job_id"])
    blob = json.dumps(res)
    assert "DOE" not in blob and "SECRET123" not in blob
    assert res["identifiers_removed"] >= 2


def test_detector_registry_fails_closed():
    config.assert_detector_allowed("classical-lung-nodule-cade")  # ok
    import pytest
    with pytest.raises(config.DetectorNotAllowed):
        config.assert_detector_allowed("made-up-detector")


def _chest_with(feature):
    hu = np.full((28, 80, 80), -1000, np.int16)
    hu[:, 10:70, 10:70] = -30
    hu[4:18, 18:58, 16:36] = -850
    hu[4:18, 18:58, 44:64] = -850
    if feature == "calc":
        hu[8:12, 28:34, 68:72] = 400
    elif feature == "effusion":
        hu[18:26, 22:56, 18:38] = 10
    elif feature == "pneumo":
        hu[4:20, 22:54, 11:21] = -1000
    return {"is_ct": True, "hu": hu, "spacing_mm": (1.0, 1.0, 2.0)}


def test_all_five_detectors_registered_and_clean():
    for d in ("classical-lung-nodule-cade", "classical-hyperdensity-cade",
              "classical-calcification-cade", "classical-effusion-cade",
              "classical-pneumothorax-cade"):
        config.assert_detector_allowed(d)
        assert config.DETECTOR_REGISTRY[d]["validated"] is False  # none are validated


def test_calcification_detector():
    cands = ct_cade.detect(_chest_with("calc"), detectors=["classical-calcification-cade"])
    assert any(c["kind"] == "calcification" for c in cands)


def test_effusion_detector():
    cands = ct_cade.detect(_chest_with("effusion"), detectors=["classical-effusion-cade"])
    assert any("fluid" in c["kind"] for c in cands)


def test_pneumothorax_detector():
    cands = ct_cade.detect(_chest_with("pneumo"), detectors=["classical-pneumothorax-cade"])
    assert any("air" in c["kind"] for c in cands)


def test_new_detectors_deterministic():
    v = _chest_with("effusion")
    assert ct_cade.detect(v) == ct_cade.detect(v)


def test_mr_detect_503_when_disabled(client):
    r = client.post("/api/mr-detect", files=F.as_upload(F.mr_series(4)))
    assert r.status_code == 503


def test_mr_detect_research_framed(client, monkeypatch):
    monkeypatch.setattr(config, "MR_DETECT_ENABLED", True)
    r = client.post("/api/mr-detect", files=F.as_upload(F.mr_series(6)))
    assert r.status_code == 200, r.text
    res = F.poll_detect(client, r.json()["job_id"])  # shared job store; poll path differs
    res = client.get(f"/api/mr-detect/{r.json()['job_id']}").json()
    assert res["status"] == "done", res
    assert res["modality"] == "MR" and res["research_only"] is True and res["validated"] is False
    d = res["disclaimer"].lower()
    assert "research use only" in d and "a.u." in d
    for c in res["candidates"]:
        assert c["mean_hu"] is None  # MR never claims HU
        assert c["validated"] is False


def test_mr_detect_refuses_ct(client, monkeypatch):
    monkeypatch.setattr(config, "MR_DETECT_ENABLED", True)
    r = client.post("/api/mr-detect", files=F.as_upload(F.ct_chest_series(4)))
    assert r.status_code == 422
