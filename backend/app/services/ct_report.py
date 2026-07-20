"""Deterministic CT/MRI research report builder + server-side safety guard.

Composes a report from clinician-CONFIRMED research candidates and anatomy
measurements ONLY. It is a SUMMARY of unvalidated candidates + measurements — never a
diagnosis, never triage, never a probability. There are four sections:

    TECHNIQUE     — modality / series / protocol string (+ clinical history)
    MEASUREMENTS  — the clinician's own ROI (HU/a.u.) + length/angle values, verbatim
    RESEARCH CANDIDATES — each confirmed candidate, framed "unvalidated research
                    candidate — not a diagnosis"; salience BAND, never a percentage
    PATIENT NOTE  — plain-language "this used a research tool that is not a diagnostic
                    device; discuss with your doctor"

There is NO impression that asserts disease and NO differentials-as-diagnosis.

`assert_report_safe()` is the server-side guard: it REFUSES (raises CtReportUnsafe) any
report that lost its framing fields OR whose body contains diagnostic/probability
phrasing. It runs on every build, so even an LLM formatter (which may ONLY reformat the
supplied text) cannot inject a finding, a percentage, or a diagnosis.
"""
import re

from .. import config
from ..models.ct_report import (CtConfirmedCandidate, CtMeasurement, CtReportRequest,
                                CtReportResponse)


class CtReportUnsafe(Exception):
    """The composed CT/MRI report violated a framing/no-diagnosis invariant."""


# Phrasings that would make the report read as a diagnosis or a probability. The
# deterministic template never emits these; the guard is defence-in-depth against a
# future LLM formatter. IMPORTANT: the report legitimately uses NEGATED framing
# ("not a diagnosis", "not a diagnostic device", "non-probabilistic", "not a
# probability"), so the guard bans only the ASSERTIVE constructions — ones that can
# never appear in that framing — never the bare words "diagnosis"/"probability".
_BANNED = [
    re.compile(r"\d\s*%"),                                    # any percentage
    re.compile(r"\bprobability of\b", re.I),                 # "probability of disease"
    re.compile(r"\bdiagnosis of\b", re.I),                   # assertive dx (not "a diagnosis")
    re.compile(r"\bdiagnostic of\b", re.I),                  # "diagnostic of X"
    re.compile(r"\bis diagnostic\b", re.I),                  # "is diagnostic"
    re.compile(r"\bimpression\b", re.I),                      # no disease impression
    re.compile(r"\bdifferential\b", re.I),                    # no differentials
    re.compile(r"\bconsistent with\b", re.I),
    re.compile(r"\bcompatible with\b", re.I),
    re.compile(r"\brepresents (a |an )?(malignan|cancer|tumou?r|metasta|haemorrhage|hemorrhage)", re.I),
]

_BAND_WORD = {"low": "low", "medium": "medium", "high": "high"}


def _fmt_num(x) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return f"{x:g}"


def _slice_txt(m) -> str:
    if m.slice_index is None:
        return ""
    return f" (slice {int(m.slice_index) + 1})"


def _technique_section(req: CtReportRequest) -> str:
    tech = req.technique.strip() or ("CT study" if req.modality == "CT" else "MR study")
    lines = [f"TECHNIQUE: {req.modality} — {tech}."]
    if req.series_id:
        lines.append(f"Series: {req.series_id}.")
    hist = req.clinical_history.strip()
    lines.append(f"CLINICAL HISTORY: {hist or 'Not provided.'}")
    return "\n".join(lines)


def _measurement_line(m: CtMeasurement) -> str:
    label = m.label.strip() or m.kind
    sl = _slice_txt(m)
    if m.kind == "roi":
        parts = [f"mean {_fmt_num(m.mean)} {m.unit}".rstrip()]
        if m.sd is not None:
            parts.append(f"SD {_fmt_num(m.sd)}")
        if m.min is not None or m.max is not None:
            parts.append(f"range {_fmt_num(m.min)}–{_fmt_num(m.max)}")
        if m.area_mm2 is not None:
            parts.append(f"area {_fmt_num(m.area_mm2)} mm^2")
        return f"- ROI {label}{sl}: " + ", ".join(parts) + "."
    if m.kind == "length":
        return f"- Length {label}{sl}: {_fmt_num(m.value)} {m.unit or 'mm'}."
    # angle
    return f"- Angle {label}{sl}: {_fmt_num(m.value)} {m.unit or 'deg'}."


def _measurements_section(req: CtReportRequest) -> str:
    au = "HU (Hounsfield)" if req.modality == "CT" else "arbitrary a.u. (not tissue-specific)"
    head = (f"MEASUREMENTS (clinician-acquired on the 16-bit intensity; ROI intensity "
            f"is {au}):")
    if not req.measurements:
        return head + "\n- No measurements were recorded."
    return head + "\n" + "\n".join(_measurement_line(m) for m in req.measurements)


def _candidate_line(c: CtConfirmedCandidate) -> str:
    bits = []
    if c.slice_index is not None:
        bits.append(f"slice {int(c.slice_index) + 1}")
    if c.est_max_mm is not None:
        bits.append(f"~{_fmt_num(c.est_max_mm)} mm (geometry est.)")
    if c.mean_hu is not None:
        bits.append(f"{_fmt_num(c.mean_hu)} HU (est.)")
    ctx = f" [{', '.join(bits)}]" if bits else ""
    note = f" Clinician note: {c.note.strip()}" if c.note.strip() else ""
    band = _BAND_WORD.get(c.salience_band, "low")
    return (f"- {c.label}{ctx}: unvalidated research candidate — not a diagnosis. "
            f"Detector salience: {band} (non-probabilistic; not a chance of disease)."
            + note)


def _candidates_section(req: CtReportRequest) -> str:
    head = ("RESEARCH CANDIDATES (unvalidated; a licensed radiologist confirmed the "
            "REGION only, not any disease. Each is a research candidate, NOT a "
            "diagnosis and NOT triage):")
    if not req.candidates:
        return (head + "\n- No research candidates were confirmed. "
                + config.DETECT_NOT_NORMAL_MESSAGE)
    return head + "\n" + "\n".join(_candidate_line(c) for c in req.candidates)


def _patient_note(modality: str) -> str:
    return (
        "PATIENT NOTE: This summary used a research tool that is not a diagnostic "
        "device. It points out areas and measurements for a doctor to review; it does "
        "not diagnose any condition, and it can miss real problems or mark normal areas. "
        "Nothing here is a result on its own. Please discuss these results with your "
        "doctor, who knows your full medical history and can order any tests you need."
    )


def assert_report_safe(resp: CtReportResponse) -> None:
    """Server-side guard — REFUSE to emit a report that lost its framing or contains
    diagnostic/probability language. Raises CtReportUnsafe on violation."""
    # 1) Framing fields must be present and correct.
    if not resp.disclaimer or "research use only" not in resp.disclaimer.lower():
        raise CtReportUnsafe("report is missing the required research disclaimer")
    if resp.research_only is not True or resp.validated is not False:
        raise CtReportUnsafe("report lost its research_only/validated framing")
    if resp.not_a_normal_result is not True or not resp.not_a_normal_result_message:
        raise CtReportUnsafe("report lost the 'not a normal result' guarantee")
    if not resp.patient_note.strip():
        raise CtReportUnsafe("report is missing the patient-friendly note")
    # 2) The BODY (not the disclaimer) must contain no diagnostic/probability phrasing.
    body = "\n".join([resp.technique_section, resp.measurements_section,
                      resp.candidates_section, resp.patient_note])
    for pat in _BANNED:
        if pat.search(body):
            raise CtReportUnsafe(
                f"report body contains forbidden diagnostic/probability phrasing "
                f"matching /{pat.pattern}/")


def build_ct_report(req: CtReportRequest) -> CtReportResponse:
    """Deterministic template report for CT/MRI. Identical input -> identical output."""
    modality = req.modality
    disclaimer = (config.CT_DETECT_DISCLAIMER if modality == "CT"
                  else config.MR_DETECT_DISCLAIMER)
    technique = req.technique.strip() or ("CT study" if modality == "CT" else "MR study")
    tech_sec = _technique_section(req)
    meas_sec = _measurements_section(req)
    cand_sec = _candidates_section(req)
    patient = _patient_note(modality)
    report_text = "\n\n".join([tech_sec, meas_sec, cand_sec, patient,
                               "DISCLAIMER: " + disclaimer])
    resp = CtReportResponse(
        modality=modality, technique=technique,
        technique_section=tech_sec, measurements_section=meas_sec,
        candidates_section=cand_sec, patient_note=patient,
        report_text=report_text, candidate_count=len(req.candidates),
        research_only=True, validated=False,
        not_a_normal_result=True,
        not_a_normal_result_message=config.DETECT_NOT_NORMAL_MESSAGE,
        generator="template", disclaimer=disclaimer,
    )
    assert_report_safe(resp)                    # refuse to emit if framing/guard fails
    return resp
