"""Safety fixes (torch-free):
  * FIX #1 — "no flag" is NOT a normal read, as an API contract, + measured NPV.
  * FIX #3 — per-label reliability gating driven by the measured behaviour card.
  * FIX #4 — triage/calibration tail safety (clamp + knot support).
"""
import io

import numpy as np
from PIL import Image

from app import config
from app.models.schemas import AnalyzeResponse, Finding
from app.services import calibration, reliability, triage


def _png(arr) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return buf.getvalue()


# ---- FIX #1: not-a-normal-read contract -----------------------------------
def test_analyze_response_defaults_carry_not_normal_contract():
    # The schema itself encodes the non-claim, so no response can omit it.
    resp = AnalyzeResponse(disclaimer="d", image_id="a", image_url="u")
    assert resp.normal_read is False
    assert resp.read_disposition == "not_a_normal_read"


def test_abstain_is_explicitly_not_a_normal_read(client):
    # A refused (out-of-distribution) image is explicitly NOT a normal/negative read.
    col = np.zeros((120, 140, 3), dtype=np.uint8)
    col[..., 0], col[..., 1], col[..., 2] = 210, 40, 40
    r = client.post("/api/analyze", files={"file": ("dog.png", _png(col), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["competence"] == "abstain"
    assert body["normal_read"] is False
    assert body["read_disposition"] == "not_a_normal_read"
    assert body["read_disposition_message"]  # non-empty human message
    assert "not a normal read" in body["read_disposition_message"].lower()


def test_behavior_card_exposes_measured_no_flag_npv(client):
    card = client.get("/api/behavior-card").json()
    npv = card.get("no_flag_npv")
    assert npv and npv.get("available") is True
    study = npv["study_level"]
    # A real, in-distribution measurement (not fabricated, not null): 0 < NPV < 1 and
    # the miss count is carried alongside so "no flag" can never read as "normal".
    assert 0.0 < study["npv"] < 1.0
    assert study["missed_disease"] >= 1
    assert "in-distribution" in npv["note"].lower()
    # Per-label NPV is present with its positives + false-negative support.
    assert any(row["pathology"] == "Effusion" and row["npv"] is not None
               for row in npv["per_label"])


def test_per_class_ece_has_positives_count(client):
    # FIX #7 (already satisfied) — per-class ECE is only shown alongside positives.
    per = client.get("/api/behavior-card").json()["calibration"]["per_class"]
    for name, blk in per.items():
        assert "ece" in blk and "positives" in blk


# ---- FIX #3: reliability gating -------------------------------------------
def test_reliability_flags_sparse_and_below_chance_labels():
    # Below-chance AUROC (Pneumonia) and sparse positives (Pneumothorax 9, Nodule 7,
    # Mass 18, Cardiomegaly 16) are NOT reliably measured; well-supported above-chance
    # labels are.
    for lb in ("Pneumonia", "Pneumothorax", "Nodule", "Mass", "Cardiomegaly", "Hernia"):
        assert reliability.is_reliable(lb) is False, lb
    for lb in ("Effusion", "Consolidation", "Infiltration", "Atelectasis"):
        assert reliability.is_reliable(lb) is True, lb


def test_reliability_reason_is_explicit():
    r = reliability.label_reliability("Pneumonia")
    assert r["state"] == "not_reliably_measured"
    assert "chance" in r["reason"].lower()
    r2 = reliability.label_reliability("Pneumothorax")
    assert "positive" in r2["reason"].lower()  # sparse-support reason


def test_unreliable_label_does_not_escalate_triage():
    # Even with a high calibrated P, an unreliable label stays routine (advisory only).
    findings = [Finding(label="Pneumonia", probability=0.9,
                        calibrated_probability=0.8, flagged=True)]
    level, reasons = triage.assess(findings)
    assert level == "routine" and reasons == []


# ---- FIX #4: tail clamp + knot support ------------------------------------
def test_calibration_knot_support_blocks_snap_tail():
    # Pneumothorax's shipped isotonic map snaps to 1.0 on few knots -> not trusted.
    assert calibration.enough_knots("Pneumothorax") is False
    # Effusion's map has ample distinct knots.
    assert calibration.enough_knots("Effusion") is True


def test_triage_clamps_calibrated_p(monkeypatch):
    # A calibrated 1.0 on a reliable, well-supported label is clamped to <= 0.90 for
    # triage, so the banner never presents a snapped tail as certainty.
    monkeypatch.setattr(reliability, "is_reliable", lambda l: True)
    monkeypatch.setattr(calibration, "enough_knots", lambda l: True)
    level, reasons = triage.assess([Finding(label="Effusion", probability=0.9,
                                            calibrated_probability=1.0, flagged=True)])
    assert level == "priority"
    assert any("90%" in r for r in reasons) and not any("100%" in r for r in reasons)
    assert config.TRIAGE_MAX_CALIBRATED_P == 0.90
