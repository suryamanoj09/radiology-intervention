"""Research CADe schema — disease-CANDIDATE detection on CT/MRI.

Unlike the anatomy-overlay models (models/segment.py, which are taboo-free), these
models INTENTIONALLY carry disease-shaped candidate labels — that is the whole point
of the research detector. What keeps them defensible is the framing, enforced here:

  * `validated` defaults False and the classical detectors never set it True — the UI
    can never imply a validated result;
  * `score` is documented as a DETECTOR score, never a probability of disease;
  * `disclaimer` is REQUIRED on the response (the router injects the RESEARCH-ONLY
    string) and `research_only` is hard-True;
  * every candidate carries the "unvalidated candidate — radiologist must confirm"
    caption.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CandidateRegion(BaseModel):
    """Where a candidate sits, on ONE slice (aligned to the viewer by position)."""
    slice_index: int = Field(ge=0)
    slice_position: Optional[float] = None
    # bbox in the mask's native pixel coords [x, y, w, h].
    bbox: Optional[list[int]] = Field(default=None, min_length=4, max_length=4)
    centroid: Optional[list[int]] = Field(default=None, min_length=2, max_length=2)


class CandidateFinding(BaseModel):
    label: str = Field(max_length=80)          # e.g. "Candidate pulmonary nodule"
    kind: str = Field(max_length=48)           # nodule | hyperdensity | lesion ...
    # NON-PROBABILISTIC detector SALIENCE in [0,1] — a geometric/statistical strength
    # of the heuristic, NOT a probability of disease and NOT calibrated. Renamed from
    # `score` (#9) so it can never read as, or be rendered as, a probability chip.
    salience: float = Field(ge=0, le=1)
    # Coarse salience BAND for the UI to render "candidate detected" WITHOUT a
    # percentage (a bare % next to a disease name reads as a calibrated probability).
    salience_band: Literal["low", "medium", "high"] = "low"
    # A plain boolean the frontend uses to render "candidate detected" — no number.
    detected: bool = True
    # This is a research candidate, never a probability of disease (belt-and-suspenders
    # so the non-probabilistic nature travels with each finding in the contract).
    is_probability: bool = False
    validated: bool = False                    # classical detectors never set this True
    region: Optional[CandidateRegion] = None
    # Geometry only (from voxel spacing), never a claimed pathological measurement.
    est_max_mm: Optional[float] = Field(default=None, ge=0)
    est_volume_ml: Optional[float] = Field(default=None, ge=0)
    mean_hu: Optional[float] = None
    disposition: str = "Unvalidated candidate — radiologist must confirm"
    method: str = ""
    model: str = ""
    license: str = ""


class CandidateResponse(BaseModel):
    job_id: str
    modality: Literal["CT", "MR"]
    status: Literal["queued", "running", "done", "error", "unknown"] = "queued"
    # Abstain gate outcome, mirroring the CXR self-audit path.
    competence: Literal["read", "down-weight", "abstain"] = "read"
    reasons: list[str] = Field(default_factory=list)
    candidates: list[CandidateFinding] = Field(default_factory=list)
    candidate_count: int = 0
    model: str = ""
    license: str = ""
    method: str = ""
    validated: bool = False                    # hard False for the classical demo
    research_only: bool = True                 # hard True — never a device claim
    # #9 — the "absence of candidates is NOT a normal result" guarantee, in the API
    # CONTRACT (not only a frontend string). ALWAYS True; the message is machine-
    # readable so any consumer polling candidate_count==0 cannot read it as "clear".
    not_a_normal_result: bool = True
    not_a_normal_result_message: str = ""
    n_slices: int = 0
    slice_urls: Optional[list[str]] = None     # rendered CT slices for review context
    slice_positions: Optional[list[float]] = None
    series_id: Optional[str] = None
    identifiers_removed: int = 0
    n_quarantined: int = 0
    burned_in: Literal["YES", "NO", "UNKNOWN"] = "UNKNOWN"
    content_sha256: Optional[str] = None       # hash of the upload, so feedback is keyed
    timestamp: Optional[str] = None
    detail: Optional[str] = None
    disclaimer: str                            # REQUIRED — router injects the research string
