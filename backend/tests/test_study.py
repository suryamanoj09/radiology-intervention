"""Real-time multi-image study endpoint /api/analyze-study (issues #13, #14).

The vision model is fully mocked (call-order iterator), load_any + self-audit are
stubbed, so this exercises the ROUTER + FUSION contract with no torch/weights:
  * per-image analyses are preserved (each view keeps its own findings);
  * fusion = MAX banded confidence across views, tagged with the winning view;
  * one bad/non-chest view degrades to an abstained slot (never fails the batch,
    never silently scored by the chest model);
  * the image-count cap returns 413.
"""

import numpy as np

from app import config
from app.models.schemas import AnalyzeResponse, Finding
from app.services import dicom_utils, self_audit, vision_xray


def _gray_load(*_a, **_k):
    return np.zeros((16, 16), dtype=np.uint8), None, "CR", "image", {}


def _read_audit(*_a, **_k):
    return {"competence": "read", "ood_score": 0.0, "reasons": []}


def _resp(findings, triage="routine", reasons=None):
    return AnalyzeResponse(
        image_id="",  # router/vision sets a real id; fusion keys on it, so give unique below
        image_url="/static/uploads/x.png",
        findings=findings,
        triage=triage,
        triage_reasons=reasons or [],
        competence="read",
        modality="CR",
        source_format="image",
        disclaimer=config.DISCLAIMER,
    )


def _multipart(files):
    return [("files", (name, data, "image/png")) for name, data in files]


def test_two_views_fuse_to_max_confidence_tagged_with_winning_view(client, monkeypatch):
    monkeypatch.setattr(dicom_utils, "load_any", _gray_load)
    monkeypatch.setattr(self_audit, "assess", _read_audit)

    pa = AnalyzeResponse(
        image_id="aaaaaaaaaaaa", image_url="/static/uploads/aaaaaaaaaaaa.png",
        findings=[Finding(label="Effusion", probability=0.60, flagged=True)],
        triage="priority", triage_reasons=["Effusion at 60% model confidence"],
        competence="read", modality="CR", source_format="image", disclaimer=config.DISCLAIMER)
    lat = AnalyzeResponse(
        image_id="bbbbbbbbbbbb", image_url="/static/uploads/bbbbbbbbbbbb.png",
        findings=[Finding(label="Effusion", probability=0.82, flagged=True)],
        triage="priority", triage_reasons=["Effusion at 82% model confidence"],
        competence="read", modality="CR", source_format="image", disclaimer=config.DISCLAIMER)
    seq = iter([pa, lat])
    monkeypatch.setattr(vision_xray, "analyze_xray", lambda *a, **k: next(seq))

    r = client.post(
        "/api/analyze-study",
        files=_multipart([("pa.png", b"pngpa"), ("lat.png", b"pnglat")]),
        data={"views": ["pa", "lateral"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["study_id"]
    assert len(body["images"]) == 2
    assert body["n_abstained"] == 0
    # Per-image views resolved from the `views` form.
    assert {im["view"] for im in body["images"]} == {"PA", "Lateral"}

    # Fusion: MAX across views (0.82), tagged with the Lateral view that produced it.
    fused = {f["label"]: f for f in body["fused"]}
    assert "Effusion" in fused
    assert fused["Effusion"]["probability"] == 0.82
    assert fused["Effusion"]["view"] == "Lateral"
    # per_view keeps BOTH views' bands so the UI can show a column each.
    assert set(fused["Effusion"]["per_view"].values()) == {0.6, 0.82}

    assert body["top_finding"] == "Effusion"
    assert body["triage"] == "priority"  # worst per-image triage


def test_non_chest_dicom_in_batch_becomes_abstain_slot_not_a_failure(client, monkeypatch):
    def load_any(data, filename, window):
        if filename == "ct.dcm":
            return np.zeros((16, 16), dtype=np.uint8), None, "CT", "dicom", {}
        return _gray_load()

    monkeypatch.setattr(dicom_utils, "load_any", load_any)
    monkeypatch.setattr(self_audit, "assess", _read_audit)

    good = AnalyzeResponse(
        image_id="cccccccccccc", image_url="/static/uploads/cccccccccccc.png",
        findings=[Finding(label="Cardiomegaly", probability=0.7, flagged=True)],
        triage="routine", competence="read", modality="CR",
        source_format="image", disclaimer=config.DISCLAIMER)
    # analyze_xray must run ONLY for the good film; the CT short-circuits before it.
    def _only_good(*a, **k):
        return good
    monkeypatch.setattr(vision_xray, "analyze_xray", _only_good)

    def _boom(*a, **k):
        raise AssertionError("chest model must not score a CT slot")
    monkeypatch.setattr(vision_xray, "abstain_response", _boom)  # not used; CT never scored

    r = client.post(
        "/api/analyze-study",
        files=_multipart([("cxr.png", b"png"), ("ct.dcm", b"dcm")]),
        data={"views": ["pa", "auto"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["images"]) == 2
    assert body["n_abstained"] == 1
    # The abstained CT slot carries a reason and no findings; fusion excludes it.
    abstained = [im for im in body["images"] if im["competence"] == "abstain"]
    assert abstained and abstained[0]["findings"] == []
    assert any("CT" in reason for reason in abstained[0]["audit_reasons"])
    # Fusion only reflects the good chest film.
    assert {f["label"] for f in body["fused"]} == {"Cardiomegaly"}


def test_empty_file_in_batch_is_an_abstain_slot(client, monkeypatch):
    monkeypatch.setattr(self_audit, "assess", _read_audit)
    r = client.post("/api/analyze-study", files=_multipart([("empty.png", b"")]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_abstained"] == 1
    assert body["images"][0]["competence"] == "abstain"


def test_too_many_images_is_413(client, monkeypatch):
    monkeypatch.setattr(config, "STUDY_MAX_IMAGES", 1)
    r = client.post(
        "/api/analyze-study",
        files=_multipart([("a.png", b"a"), ("b.png", b"b")]),
    )
    assert r.status_code == 413, r.text
    assert "max" in r.json()["detail"].lower()
