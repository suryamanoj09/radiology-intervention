"""Report-safety invariants: patient-summary readability, the provenance
(no-unbacked-measurement) guard, and the confidence→action disposition layer."""
from app.models.schemas import (Finding, ReportRequest, StructuredFindings)
from app.services import provenance, readability, reliability, templates, triage

# Patient-material reading-level ceiling. 6th grade is ideal but unavoidable
# medical nouns (pneumothorax, effusion) inflate Flesch-Kincaid; this is the
# realistic band for safe patient material, and the grade is asserted, not hoped.
PATIENT_GRADE_CEILING = 9.0


def _req(**structured):
    return ReportRequest(structured=StructuredFindings(**structured))


def test_patient_summary_reading_level_is_gated():
    # A summary WITH findings (worst case for reading level: it names conditions).
    req = _req(pleural_effusion=True, effusion_side="right", cardiomegaly=True)
    report = templates.build_report(req)
    grade = readability.flesch_kincaid_grade(report.patient)
    assert grade <= PATIENT_GRADE_CEILING, (
        f"patient summary Flesch-Kincaid grade {grade} exceeds {PATIENT_GRADE_CEILING}")


def test_empty_and_normal_summaries_are_readable():
    for req in (_req(), _req(reviewed_no_acute=True)):
        grade = readability.flesch_kincaid_grade(templates.build_report(req).patient)
        assert grade <= PATIENT_GRADE_CEILING


def test_provenance_blocks_unbacked_measurement():
    s = StructuredFindings(nodule_present=True)  # no nodule_size_mm entered
    bad = "There is a pulmonary nodule measuring 12 mm in the right upper lobe."
    assert provenance.measurement_violations(bad, s), "unbacked '12 mm' must be flagged"
    assert not provenance.is_backed(bad, s)


def test_provenance_allows_backed_measurement():
    s = StructuredFindings(nodule_present=True, nodule_size_mm=12.0)  # clinician-entered
    ok = "There is a pulmonary nodule measuring 12 mm."
    assert provenance.measurement_violations(ok, s) == []
    assert provenance.is_backed(ok, s)


def test_provenance_ignores_percentages_and_years():
    s = StructuredFindings()
    txt = "Model confidence 85%. Compared with the 2019 study, no change."
    assert provenance.measurement_violations(txt, s) == []


def test_disposition_pneumothorax_advisory_when_not_reliably_measured():
    # FIX #3 — pneumothorax is NOT reliably measured on the current validation set
    # (only 9 positives), so even a high score is an ADVISORY "cannot exclude", never
    # a confident "Urgent" finding.
    for p in (0.5, 0.7):
        d = triage.finding_disposition(Finding(label="Pneumothorax", probability=p, flagged=True)) or ""
        assert "Cannot exclude" in d and "advisory" in d.lower()
        assert not d.startswith("Urgent")


def test_disposition_pneumothorax_tiered_when_reliably_measured(monkeypatch):
    # When a label IS reliably measured, the score-tiered disposition applies again:
    # a mid score is a non-red "cannot exclude", a genuinely high score -> Urgent.
    monkeypatch.setattr(reliability, "label_reliability",
                        lambda l: {"reliable": True, "state": "measured",
                                   "positives": 50, "auroc": 0.9, "reason": None})
    mid = triage.finding_disposition(Finding(label="Pneumothorax", probability=0.5, flagged=True)) or ""
    assert "Cannot exclude" in mid and not mid.startswith("Urgent")
    hi = triage.finding_disposition(Finding(label="Pneumothorax", probability=0.7, flagged=True)) or ""
    assert hi.startswith("Urgent")


def test_disposition_borderline_near_operating_point():
    # A RELIABLY-measured label just above its operating point is 'Borderline'.
    f = Finding(label="Atelectasis", probability=0.51, flagged=True)
    assert "Borderline" in (triage.finding_disposition(f) or "")


def test_disposition_advisory_for_unreliable_label():
    # FIX #3 — Nodule (7 positives) is not reliably measured, so its flag is ADVISORY,
    # not a confident 'Borderline'/'Flagged for review'.
    d = triage.finding_disposition(Finding(label="Nodule", probability=0.51, flagged=True)) or ""
    assert "not reliably measured" in d.lower() and "advisory" in d.lower()


def test_disposition_none_when_not_flagged():
    f = Finding(label="Nodule", probability=0.3, flagged=False)
    assert triage.finding_disposition(f) is None


def test_distinct_raw_labels_are_never_collapsed_into_one_card():
    # T1 invariant: Pneumonia and Lung Opacity are DISTINCT model labels and must
    # each get their own unique display name — never merged into one 'consolidation
    # /opacity' card (the display layer must not assert a grouping the model lacks).
    from app.services import label_map
    assert label_map.raw_display("Pneumonia") != label_map.raw_display("Lung Opacity")
    # And group_flagged (the old collapsing helper) is gone, so it can't come back.
    assert not hasattr(label_map, "group_flagged")


def test_report_suppresses_raw_score_for_uncalibrated_label():
    # T2 (report/PDF surface): an uncalibrated flagged label must NOT persist a bare
    # raw % into the clinical report — it says "not calibrated" instead.
    req = ReportRequest(
        structured=StructuredFindings(),
        vision_findings=[Finding(label="Mass", probability=0.71, flagged=True,
                                 calibration_state="uncalibrated")],
    )
    clinical = templates.build_report(req).clinical.lower()
    assert "mass" in clinical
    assert "not calibrated" in clinical
    assert "model score 71%" not in clinical  # the raw % must not leak


def test_report_withholds_denylisted_client_finding():
    # Defence-in-depth: templates re-applies the FULL _denial predicate, so a
    # denylisted label (Fracture) smuggled in via client vision_findings NEVER
    # reaches the report — regardless of AUROC reliability.
    req = ReportRequest(
        structured=StructuredFindings(),
        vision_findings=[Finding(label="Fracture", probability=0.9, flagged=True,
                                 calibration_state="calibrated")],
    )
    clinical = templates.build_report(req).clinical.lower()
    assert "model score" not in clinical


def test_report_withholds_reliable_sub_auroc_client_finding(monkeypatch):
    # The AUROC branch of the report's defence-in-depth still fires for a below-floor
    # label when reliability is not required (proves templates re-applies _denial's
    # AUROC branch, not just the denylist). Confidence-aware by default (a noisy
    # small-sample sub-floor AUROC no longer hides a label — see test_label_fidelity).
    from app.services import vision_xray
    monkeypatch.setattr(vision_xray.config, "LABEL_MIN_AUROC_REQUIRE_RELIABLE", False)
    req = ReportRequest(
        structured=StructuredFindings(),
        vision_findings=[Finding(label="Nodule", probability=0.9, flagged=True,
                                 calibration_state="calibrated")],
    )
    clinical = templates.build_report(req).clinical.lower()
    assert "model score" not in clinical


def test_banner_gates_on_calibrated_p_not_raw_score():
    # Uncalibrated pneumothorax at raw 54% -> NO banner (can't justify an alarm).
    lvl, _ = triage.assess([Finding(label="Pneumothorax", probability=0.54, flagged=True)])
    assert lvl == "routine"
    # Calibrated P below the 0.30 floor (the ~5% case the user flagged) -> NO banner.
    lvl2, _ = triage.assess([Finding(label="Pneumothorax", probability=0.54,
                                     calibrated_probability=0.05, flagged=True)])
    assert lvl2 == "routine"
    # A calibrated, RELIABLY-measured priority label above the floor -> amber priority.
    lvl4, _ = triage.assess([Finding(label="Effusion", probability=0.84,
                                     calibrated_probability=0.45, flagged=True)])
    assert lvl4 == "priority"


def test_unreliable_snap_tail_pneumothorax_never_escalates_banner():
    # FIX #3/#4 — pneumothorax is not reliably measured (9 positives) AND its isotonic
    # map snaps its tail to 1.0 on sparse support, so even a maxed calibrated P must
    # NOT manufacture an 'urgent' banner.
    lvl, reasons = triage.assess([Finding(label="Pneumothorax", probability=0.95,
                                          calibrated_probability=1.0, flagged=True)])
    assert lvl == "routine" and reasons == []


def test_reliable_supported_label_escalates_with_clamped_p(monkeypatch):
    # When the label IS reliable and its map has knot support, a high calibrated P
    # escalates — but the banner reason shows the CLAMPED P (<= 0.90), never 100%.
    monkeypatch.setattr(reliability, "is_reliable", lambda l: True)
    from app.services import calibration
    monkeypatch.setattr(calibration, "enough_knots", lambda l: True)
    lvl, reasons = triage.assess([Finding(label="Pneumothorax", probability=0.95,
                                          calibrated_probability=1.0, flagged=True)])
    assert lvl == "urgent"
    assert any("90%" in r for r in reasons)  # 1.0 clamped to TRIAGE_MAX_CALIBRATED_P
