"""CT/MRI research report schema — a SUMMARY of clinician-CONFIRMED research
candidates + anatomy measurements/ROI stats. It is deliberately sub-parity with the
chest X-ray report in CLAIMS: NOT a diagnosis, NOT triage, NOT a calibrated
probability, NO differentials-as-diagnosis, NO impression that asserts disease.

Honesty is structural (mirrors models/detect.py). The response guarantees:
  * `research_only` hard-True, `validated` hard-False;
  * `not_a_normal_result` hard-True with a machine-readable message — an empty report
    is NEVER a 'normal' read;
  * `disclaimer` is REQUIRED (no default) so a report cannot exist without it;
  * candidates carry NO probability — only a non-probabilistic salience band;
  * measurements are the clinician's OWN ROI/length/angle values, echoed verbatim
    (HU for CT, arbitrary a.u. for MR — never tissue-specific).
The service (services/ct_report.py) additionally REFUSES to emit any diagnostic or
probability phrasing (server-side guard), so an LLM formatter can only format supplied
content, never add a finding.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CtMeasurement(BaseModel):
    """One clinician-acquired measurement to echo into the report. ROI carries the
    16-bit intensity stats (HU for CT / a.u. for MR); length is mm; angle is degrees."""
    kind: Literal["roi", "length", "angle"]
    label: str = Field(default="", max_length=80)
    unit: str = Field(default="", max_length=16)          # HU | a.u. | mm | deg | mm^2
    value: Optional[float] = None                         # length (mm) / angle (deg)
    mean: Optional[float] = None                          # ROI intensity stats ...
    sd: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    area_mm2: Optional[float] = Field(default=None, ge=0)
    slice_index: Optional[int] = Field(default=None, ge=0)
    slice_position: Optional[float] = None


class CtConfirmedCandidate(BaseModel):
    """A research candidate the clinician CONFIRMED as a region worth reviewing — the
    only thing that reaches the report. Confirmation attests the REGION, not a disease.
    Carries NO probability: only a coarse, non-probabilistic salience band."""
    label: str = Field(max_length=80)
    kind: str = Field(default="", max_length=48)
    salience_band: Literal["low", "medium", "high"] = "low"
    est_max_mm: Optional[float] = Field(default=None, ge=0)
    mean_hu: Optional[float] = None                       # CT only; MR is a.u. -> None
    slice_index: Optional[int] = Field(default=None, ge=0)
    note: str = Field(default="", max_length=280)


class CtReportRequest(BaseModel):
    # Modality is forced by the endpoint (/ct-report -> CT, /mr-report -> MR); a body
    # value is ignored server-side.
    modality: Literal["CT", "MR"] = "CT"
    technique: str = Field(default="", max_length=240)    # series/protocol text
    clinical_history: str = Field(default="", max_length=2000)
    measurements: list[CtMeasurement] = Field(default_factory=list)
    # ONLY clinician-confirmed candidates. Raw detector output must never be passed
    # straight through — the frontend passes confirmed candidates here.
    candidates: list[CtConfirmedCandidate] = Field(default_factory=list)
    series_id: Optional[str] = Field(default=None, max_length=64)


class CtReportResponse(BaseModel):
    modality: Literal["CT", "MR"]
    technique: str
    technique_section: str
    measurements_section: str
    candidates_section: str
    patient_note: str
    report_text: str                                      # full assembled report
    candidate_count: int = 0
    research_only: bool = True                            # hard True
    validated: bool = False                               # hard False
    # #9 — the "absence is not normality" guarantee, in the CONTRACT.
    not_a_normal_result: bool = True
    not_a_normal_result_message: str
    generator: str = "template"                           # deterministic template
    disclaimer: str                                       # REQUIRED — no default
