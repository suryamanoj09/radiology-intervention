"""Measurement / caliper safety contract (issue #2 — caliper must show mm, and mm
must only ever come from a human/caliper, never fabricated by the AI).

Backend-testable slice:
  * schema DEFAULTS keep every mm/area field empty by construction, so a refactor
    can't start emitting fake millimetres on a PNG that has no pixel spacing;
  * the deterministic report surfaces a CLINICIAN-entered nodule size (labelled
    'clinician-measured') but NEVER promotes an AI/model size estimate into the
    report text.
"""

from app.models.schemas import AnalyzeResponse, Finding


def test_finding_measurement_fields_default_to_empty():
    f = Finding(label="Nodule", probability=0.7)
    # No pixel spacing => no mm/area/contour fabricated.
    assert f.est_max_2d_mm is None
    assert f.est_area_mm2 is None
    assert f.attention_contour is None
    # size_mm is caliper-only; the model never populates it.
    assert f.size_mm is None
    assert f.size_note is None


def test_analyze_response_pixel_spacing_defaults_to_none():
    r = AnalyzeResponse(image_id="abcdef012345", image_url="/x.png", disclaimer="d")
    # None => the UI must calibrate (mm) client-side rather than show fake mm.
    assert r.pixel_spacing_mm is None


def test_clinician_measured_nodule_size_is_labelled_in_report(client):
    payload = {"structured": {"nodule_present": True, "nodule_size_mm": 12,
                              "nodule_location": "RUL"}}
    r = client.post("/api/generate-report", json=payload)
    clinical = r.json()["clinical"]
    assert "12 mm" in clinical
    assert "clinician-measured" in clinical
    # A sized nodule triggers the Fleischner follow-up note.
    assert "Fleischner" in clinical


def test_ai_size_estimate_is_never_emitted_as_a_report_measurement(client):
    # The AI flag carries an attention-region size estimate; the report must NOT
    # present it as a measurement (mm only from the clinician's caliper).
    # Use a CALIBRATED, above-AUROC-floor label (Mass) so the flag actually
    # surfaces with its honest "model score" wording — a sub-floor label (Nodule)
    # or an uncalibrated one is deliberately withheld/anonymised by T2/T3.
    payload = {
        "structured": {},  # clinician confirmed / measured nothing
        "vision_findings": [
            {"label": "Mass", "probability": 0.71, "flagged": True,
             "calibration_state": "calibrated", "calibrated_probability": 0.55,
             "est_max_2d_mm": 25.0, "est_area_mm2": 480.0, "size_mm": 25.0}
        ],
    }
    r = client.post("/api/generate-report", json=payload)
    clinical = r.json()["clinical"]
    # AI appears only as an unconfirmed model-score flag (honest wording: a SCORE,
    # not a probability), carrying the raw label...
    assert "model score" in clinical.lower()
    assert "mass" in clinical.lower()
    # ...and NO fabricated millimetre measurement leaks in.
    assert "25 mm" not in clinical
    assert "clinician-measured" not in clinical
    assert "measuring approximately" not in clinical
