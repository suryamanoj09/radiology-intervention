"""Triage safety: a clinician-CONFIRMED pneumothorax escalates to urgent even
when no model finding drove it (assess_confirmed / finalize / the report route)."""

from app.models.schemas import Finding, ReportRequest, StructuredFindings
from app.services import templates, triage


def test_assess_confirmed_pneumothorax_is_urgent():
    level, reasons = triage.assess_confirmed(StructuredFindings(pneumothorax=True))
    assert level == "urgent"
    assert any("pneumothorax" in r.lower() for r in reasons)


def test_confirmed_pneumothorax_overrides_low_model_confidence():
    # Model was NOT confident (nothing flagged), but the clinician confirmed it.
    req = ReportRequest(
        structured=StructuredFindings(pneumothorax=True, pneumothorax_side="right"),
        vision_findings=[Finding(label="Pneumothorax", probability=0.10, flagged=False)],
    )
    resp = templates.finalize(req, "c", "p", "d", generator="template")
    assert resp.triage == "urgent"


def test_report_route_reports_urgent_for_confirmed_pneumothorax(client):
    payload = {"structured": {"pneumothorax": True, "pneumothorax_side": "left"}}
    r = client.post("/api/generate-report", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["triage"] == "urgent"


def test_confirmed_effusion_is_priority_not_urgent():
    level, _ = triage.assess_confirmed(StructuredFindings(pleural_effusion=True))
    assert level == "priority"


def test_combine_takes_the_higher_level():
    assert triage.combine("routine", "urgent") == "urgent"
    assert triage.combine("priority", "routine") == "priority"
