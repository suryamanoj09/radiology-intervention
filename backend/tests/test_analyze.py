"""/api/analyze router: the upload guard rail + modality-routing safety, with the
vision model fully mocked (no torch, no weights)."""

import numpy as np

from app import config
from app.models.schemas import AnalyzeResponse, Finding
from app.services import dicom_utils, vision_xray


def _canned_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        image_id="abcdef012345",
        image_url="/static/uploads/abcdef012345.png",
        heatmap_url="/static/heatmaps/abcdef012345.png",
        top_finding="Effusion",
        findings=[Finding(label="Effusion", probability=0.82, flagged=True)],
        triage="priority",
        triage_reasons=["Effusion at 82% model confidence"],
        modality="CR",
        source_format="image",
        disclaimer=config.DISCLAIMER,
    )


def test_analyze_happy_path_returns_findings_and_disclaimer(client, monkeypatch, png_bytes):
    # Mock the model at the analyze_xray boundary so no torch/weights are touched.
    monkeypatch.setattr(vision_xray, "analyze_xray",
                        lambda *a, **k: _canned_response())

    r = client.post("/api/analyze", files={"file": ("cxr.png", png_bytes, "image/png")})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["findings"], "expected at least one finding"
    assert body["findings"][0]["label"] == "Effusion"
    # The safety disclaimer must ride along on every analysis response.
    assert body["disclaimer"]
    assert "not a diagnosis" in body["disclaimer"].lower()


def test_non_cxr_dicom_modality_is_refused_422(client, monkeypatch):
    # A CT DICOM must be refused, never silently scored by the chest model.
    def fake_load_any(data, filename, window):
        return np.zeros((8, 8), dtype=np.uint8), None, "CT", "dicom", {}

    monkeypatch.setattr(dicom_utils, "load_any", fake_load_any)

    def _boom(*a, **k):  # analyze_xray must NOT be reached for a refused modality
        raise AssertionError("analyze_xray should not run for a non-CXR modality")

    monkeypatch.setattr(vision_xray, "analyze_xray", _boom)

    r = client.post("/api/analyze", files={"file": ("scan.dcm", b"not-a-real-dicom", "application/dicom")})

    assert r.status_code == 422, r.text
    assert "CT" in r.json()["detail"]


def test_ot_secondary_capture_dicom_is_refused_422(client, monkeypatch):
    # FIX #5 — an "OT" (Other/Secondary-Capture) DICOM is NOT a chest radiograph and
    # must be routed away, never scored by the chest model.
    assert "OT" not in config.CXR_MODALITIES

    def fake_load_any(data, filename, window):
        return np.zeros((8, 8), dtype=np.uint8), None, "OT", "dicom", {}

    monkeypatch.setattr(dicom_utils, "load_any", fake_load_any)

    def _boom(*a, **k):
        raise AssertionError("analyze_xray must not run for an OT/secondary-capture DICOM")

    monkeypatch.setattr(vision_xray, "analyze_xray", _boom)
    r = client.post("/api/analyze", files={"file": ("sc.dcm", b"x", "application/dicom")})
    assert r.status_code == 422, r.text
    assert "OT" in r.json()["detail"]


def test_oversized_upload_413(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 8)
    r = client.post("/api/analyze",
                    files={"file": ("big.png", b"0123456789ABCDEF", "image/png")})
    assert r.status_code == 413, r.text


def test_empty_upload_400(client):
    r = client.post("/api/analyze", files={"file": ("empty.png", b"", "image/png")})
    assert r.status_code == 400, r.text
    assert "empty" in r.json()["detail"].lower()
