"""CT/MRI research report (#9 / WF7) + safety hardening.

Guarantees pinned here:
  * a CT report contains NO diagnostic assertion / no probability, and carries the
    machine-readable not_a_normal_result guarantee;
  * the report is composed only from confirmed candidates + measurements, framed as
    unvalidated research candidates (never a diagnosis, never differentials);
  * the server-side guard REFUSES a report that lost its framing (missing disclaimer /
    not_a_normal_result) or whose body contains diagnostic/probability phrasing;
  * the detect candidate response exposes a non-probability-shaped salience (never a
    `score`), plus a machine-readable not_a_normal_result;
  * the MR abstain gate refuses clearly-inappropriate volumes.
"""
import re

import numpy as np
import pytest

from app import config
from app.models.ct_report import (CtConfirmedCandidate, CtMeasurement, CtReportRequest,
                                  CtReportResponse)
from app.routers.detect import _mr_competence, _salience_band
from app.services import ct_report

# ASSERTIVE diagnostic/probability phrasing that must never appear in a report BODY.
# (The body legitimately uses NEGATED framing — "not a diagnosis", "non-probabilistic"
# — so we assert the absence of assertive constructions, not the bare words.)
_DIAGNOSTIC = re.compile(
    r"\d\s*%|\bprobability of\b|\bdiagnosis of\b|\bdiagnostic of\b|\bis diagnostic\b"
    r"|\bimpression\b|\bdifferential\b|\bconsistent with\b",
    re.I)


def _ct_req(**kw):
    return CtReportRequest(modality="CT", **kw)


# --- 1. CT report: no diagnostic assertion, carries not_a_normal_result ------

def test_ct_report_endpoint_no_diagnosis_and_not_normal(client):
    payload = {
        "technique": "Chest CT, 1.25 mm, portal venous",
        "clinical_history": "Cough.",
        "measurements": [
            {"kind": "roi", "label": "left upper lobe", "unit": "HU",
             "mean": 42.0, "sd": 12.0, "min": 5.0, "max": 88.0, "area_mm2": 210.0,
             "slice_index": 7},
            {"kind": "length", "label": "nodule long axis", "unit": "mm",
             "value": 8.4, "slice_index": 7},
        ],
        "candidates": [
            {"label": "Candidate pulmonary nodule", "kind": "pulmonary nodule",
             "salience_band": "medium", "est_max_mm": 8.4, "mean_hu": 50.0,
             "slice_index": 7, "note": "confirm on follow-up"},
        ],
    }
    r = client.post("/api/ct-report", json=payload)
    assert r.status_code == 200, r.text
    j = r.json()
    # Contract fields.
    assert j["modality"] == "CT"
    assert j["research_only"] is True and j["validated"] is False
    assert j["not_a_normal_result"] is True and j["not_a_normal_result_message"]
    assert "research use only" in j["disclaimer"].lower()
    # The clinician's real measurements are echoed.
    assert "42" in j["measurements_section"] and "HU" in j["measurements_section"]
    assert "8.4 mm" in j["measurements_section"]
    # The candidate is framed as unvalidated research, not a diagnosis.
    assert "unvalidated research candidate" in j["candidates_section"].lower()
    assert "not a diagnosis" in j["candidates_section"].lower()
    # Patient-friendly note names the research-tool framing.
    assert "not a diagnostic device" in j["patient_note"].lower()
    assert "discuss these results with your doctor" in j["patient_note"].lower()
    # NO diagnostic assertion / probability anywhere in the composed BODY.
    body = "\n".join([j["technique_section"], j["measurements_section"],
                      j["candidates_section"], j["patient_note"]])
    assert not _DIAGNOSTIC.search(body), f"diagnostic phrasing leaked: {body!r}"


def test_ct_report_empty_candidates_is_not_normal(client):
    r = client.post("/api/ct-report", json={"technique": "Head CT"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["candidate_count"] == 0
    # An empty report is NEVER 'normal' — the non-claim is present in the body and flag.
    assert j["not_a_normal_result"] is True
    assert "not a normal or negative result" in j["candidates_section"].lower()


def test_mr_report_uses_au_never_hu(client):
    payload = {
        "measurements": [
            {"kind": "roi", "label": "lesion", "unit": "a.u.", "mean": 812.0, "sd": 40.0,
             "min": 700.0, "max": 950.0, "slice_index": 3},
        ],
        "candidates": [
            {"label": "Candidate focal signal abnormality", "kind": "relative hyperintensity",
             "salience_band": "high", "est_max_mm": 6.2, "slice_index": 3},
        ],
    }
    r = client.post("/api/mr-report", json=payload)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["modality"] == "MR"
    assert "a.u." in j["measurements_section"]
    # MR disclaimer forbids absolute/tissue-specific claims.
    assert "a.u." in j["disclaimer"].lower()


def test_ct_report_is_deterministic(client):
    payload = {"technique": "Chest CT",
               "candidates": [{"label": "Candidate hyperdensity", "salience_band": "low"}]}
    a = client.post("/api/ct-report", json=payload).json()
    b = client.post("/api/ct-report", json=payload).json()
    assert a["report_text"] == b["report_text"]
    assert a["generator"] == b["generator"] == "template"


# --- 2. The server-side guard REFUSES on missing framing / bad body ----------

def _good_response() -> CtReportResponse:
    return ct_report.build_ct_report(_ct_req(technique="Chest CT"))


def test_guard_passes_a_well_framed_report():
    ct_report.assert_report_safe(_good_response())  # must not raise


def test_guard_refuses_when_disclaimer_missing():
    resp = _good_response()
    resp.disclaimer = ""
    with pytest.raises(ct_report.CtReportUnsafe):
        ct_report.assert_report_safe(resp)


def test_guard_refuses_when_not_normal_flag_dropped():
    resp = _good_response()
    resp.not_a_normal_result = False
    with pytest.raises(ct_report.CtReportUnsafe):
        ct_report.assert_report_safe(resp)


def test_guard_refuses_when_research_framing_flipped():
    resp = _good_response()
    resp.validated = True
    with pytest.raises(ct_report.CtReportUnsafe):
        ct_report.assert_report_safe(resp)


def test_guard_refuses_diagnostic_phrasing_in_body():
    resp = _good_response()
    resp.candidates_section = "- Nodule: findings are diagnostic of malignancy (probability 88%)."
    with pytest.raises(ct_report.CtReportUnsafe):
        ct_report.assert_report_safe(resp)


# --- 3. Detect candidate response exposes NO probability-shaped score --------

def test_salience_band_buckets():
    assert _salience_band(0.2) == "low"
    assert _salience_band(0.6) == "medium"
    assert _salience_band(0.9) == "high"


def test_candidate_finding_has_no_score_field():
    from app.models.detect import CandidateFinding
    fields = set(CandidateFinding.model_fields)
    assert "score" not in fields, "the probability-shaped `score` field must be gone"
    assert {"salience", "salience_band", "detected", "is_probability"} <= fields


def test_detect_response_carries_not_a_normal_result(client, monkeypatch):
    import _dicom_factory as F
    monkeypatch.setattr(config, "CT_DETECT_ENABLED", True)
    r = client.post("/api/ct-detect", files=F.as_upload(F.ct_chest_series(8)))
    res = F.poll_detect(client, r.json()["job_id"])
    assert res["not_a_normal_result"] is True
    assert "not a normal" in res["not_a_normal_result_message"].lower()


# --- 4. MR competence / abstain gate -----------------------------------------

def test_mr_gate_abstains_on_degenerate_volume():
    flat = {"hu": np.full((6, 32, 32), 300.0, np.float32)}
    state, reasons = _mr_competence(flat)
    assert state == "abstain" and reasons


def test_mr_gate_abstains_on_non_3d_input():
    state, reasons = _mr_competence({"hu": np.zeros((32, 32), np.float32)})
    assert state == "abstain" and reasons


def test_mr_gate_abstains_on_near_empty_foreground():
    # Almost all background (0), with a small hot tail giving a real dynamic range but
    # <2% imaged tissue above the robust floor -> abstain (not a usable MR volume).
    vol = np.zeros((6, 40, 40), np.float32)
    flat = vol.reshape(-1)
    flat[:180] = 5000.0                 # ~1.9% of 9600 voxels are the only bright signal
    state, reasons = _mr_competence({"hu": vol})
    assert state == "abstain" and reasons


def test_mr_gate_reads_a_plausible_volume():
    rng = np.random.default_rng(0)
    vol = rng.normal(100, 5, size=(6, 48, 48)).astype(np.float32)  # background
    vol[:, 12:36, 12:36] = 800.0                                   # imaged tissue
    state, _ = _mr_competence({"hu": vol})
    assert state == "read"


def test_mr_endpoint_abstain_emits_no_candidates(client, monkeypatch):
    """End-to-end: a flat/degenerate MR volume abstains -> zero candidates, still
    framed not-a-normal-result."""
    import _dicom_factory as F
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import (ExplicitVRLittleEndian, MRImageStorage, generate_uid)
    import io
    import pydicom

    monkeypatch.setattr(config, "MR_DETECT_ENABLED", True)

    def flat_mr_slice(z, suid):
        ds = Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.MediaStorageSOPClassUID = MRImageStorage
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.SOPClassUID = MRImageStorage
        ds.Modality = "MR"
        ds.PatientName = "DOE^JOHN"
        ds.PatientID = "SECRET123"
        ds.Rows = ds.Columns = 48
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.PixelRepresentation = 0
        ds.SeriesInstanceUID = suid
        ds.FrameOfReferenceUID = "1.2.3"
        ds.ScanningSequence = "SE"
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 3.0
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.ImagePositionPatient = [0, 0, float(z)]
        arr = np.full((48, 48), 100, np.uint16)   # constant -> no dynamic range
        ds.PixelData = arr.astype("<u2").tobytes()
        ds.is_little_endian = True
        ds.is_implicit_VR = False
        b = io.BytesIO()
        pydicom.dcmwrite(b, ds, write_like_original=False)
        return b.getvalue()

    suid = generate_uid()
    blobs = [flat_mr_slice(z, suid) for z in range(6)]
    r = client.post("/api/mr-detect", files=F.as_upload(blobs))
    assert r.status_code == 200, r.text
    res = client.get(f"/api/mr-detect/{r.json()['job_id']}").json()
    assert res["status"] == "done", res
    assert res["competence"] == "abstain"
    assert res["candidate_count"] == 0
    assert res["not_a_normal_result"] is True
