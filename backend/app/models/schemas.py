from typing import Literal, Optional

from pydantic import BaseModel, Field


class BBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class Finding(BaseModel):
    label: str
    probability: float  # raw banded SCORE (drives flag threshold; not a probability)
    # Calibrated P(disease) from the isotonic/Platt map, when available. The raw
    # score is overconfident (ECE~0.24); this is the honest number for display.
    calibrated_probability: Optional[float] = None
    # calibrated | uncalibrated | insufficient_data. When NOT 'calibrated' the UI
    # must NOT render the raw score as a probability (a bare score reads as a
    # coin-flip); it shows a "not calibrated — read independently" state instead.
    calibration_state: str = "uncalibrated"
    # FIX #3 — is this label RELIABLY MEASURED on the validation set (enough positive
    # support AND above-chance AUROC)? When False the finding is ADVISORY ("cannot
    # exclude"), not a confident finding, and it does not drive an urgent triage
    # escalation. reliability_state mirrors this as 'measured'|'not_reliably_measured'.
    reliably_measured: Optional[bool] = None
    reliability_state: Optional[str] = None
    flagged: bool = False
    urgent: bool = False
    bbox: Optional[BBox] = None
    heatmap_url: Optional[str] = None  # per-finding Grad-CAM attention overlay
    size_mm: Optional[float] = None  # never populated by the model; caliper-only
    size_note: Optional[str] = None
    # Coarse size ESTIMATE of the high-attention region (NOT a lesion measurement).
    # Populated only when pixel spacing is known; None for PNG/JPG (no fake mm).
    est_max_2d_mm: Optional[float] = None  # longest caliper (max Feret) diameter, mm
    est_area_mm2: Optional[float] = None   # high-attention pixel area, mm^2
    # Simplified polygon of the attention region in ORIGINAL-image pixel coords
    # (for a contour overlay). Each point is [x, y] = [col, row].
    attention_contour: Optional[list[list[int]]] = None
    # Set when the model's attention fell on non-anatomical background (flag
    # suppressed or cautioned as unreliable).
    reliability_note: Optional[str] = None
    # Localization state of THIS finding's Grad-CAM, so a blank/soft map is never
    # ambiguous to the reader:
    #   localized  = focal region of attention (a soft gradient; a crisp contour is
    #                drawn only when the CAM grid is >= CONTOUR_MIN_GRID, since a
    #                7x7 map upsampled to 1000px has no real boundary)
    #   diffuse       = attention spread across the image; non-localizing (no outline)
    #   suppressed    = flag dropped by the anatomy/background gate (see reliability_note)
    #   none          = no attention map (all-zero CAM / could not localize)
    #   not_localized = flagged by score but no CAM computed (below latency budget)
    #   abstained     = whole image was out-of-distribution; not scored
    #   error         = Grad-CAM raised; region unavailable
    # A reader can therefore always tell "confident-nothing" (unflagged, no map)
    # from "abstained" from "all-zero" from "crashed".
    heatmap_state: Optional[str] = None
    heatmap_caption: Optional[str] = None
    # Explicit clinical disposition for a flagged finding — the confidence→action
    # bridge (urgent / recommend correlation / borderline-below-threshold / flagged
    # for review). None when not flagged. Set by triage.apply_dispositions.
    disposition: Optional[str] = None


class AnalyzeResponse(BaseModel):
    image_id: str
    image_url: str
    heatmap_url: Optional[str] = None
    top_finding: Optional[str] = None
    findings: list[Finding] = Field(default_factory=list)
    # FIX #1 — "no flag" is NOT a normal read, as an API contract (not just a frontend
    # string). normal_read is ALWAYS False (the tool never asserts a normal study);
    # read_disposition is machine-readable; read_disposition_message is the human note.
    # These are present on EVERY analysis, and especially on a zero-flag result — the
    # absence of a flag must never be read as "normal". See the behaviour card's
    # `no_flag_npv` for the measured negative predictive value of this state.
    normal_read: bool = False
    read_disposition: str = "not_a_normal_read"
    read_disposition_message: str = ""
    # Self-audit / abstention gate.
    competence: str = "read"  # read | down-weight | abstain
    ood_score: float = 0.0
    audit_reasons: list[str] = Field(default_factory=list)
    triage: str = "routine"  # routine | priority | urgent
    triage_reasons: list[str] = Field(default_factory=list)
    pixel_spacing_mm: Optional[float] = None  # ROW spacing (mm/px)
    # COLUMN spacing (mm/px). Differs from row spacing on anisotropic pixels; the
    # interactive caliper must scale dx by this and dy by pixel_spacing_mm, or a
    # diagonal measurement is wrong. None => square pixels (use pixel_spacing_mm).
    pixel_spacing_col_mm: Optional[float] = None
    modality: str = "CR"
    source_format: str = "image"  # image | dicom | camera_photo
    # Projection/view of THIS image within a study: PA | AP | Lateral | Frontal | Other.
    # Auto-detected from DICOM ViewPosition, or set by the clinician at upload.
    view: str = "Frontal"
    # Raw DICOM ViewPosition (e.g. PA/AP/LL/RL) when available; None for PNG/JPG
    # uploads, which carry no reliable projection tag (UI shows "unknown — confirm").
    view_position: Optional[str] = None
    identifiers_removed: int = 0  # DICOM direct identifiers scrubbed at ingest
    # Labels deliberately NOT surfaced as findings (denylisted or AUROC too low).
    # Shown only in the "what we didn't check" panel as an honest scope statement.
    not_assessed: list[dict] = Field(default_factory=list)
    # True when a higher-resolution (res512, 16x16) localization is being computed in
    # the background; the frontend polls /api/localize-hires/{image_id} and swaps in
    # the sharper map with a "sharpening..." chip. False when the localizer is off.
    hires_pending: bool = False
    # Content hash of the uploaded image, so a feedback event can identify the (public)
    # source image without a foreign key into TTL'd storage. PHI-free (a hash).
    content_sha256: Optional[str] = None
    disclaimer: str


class FusedFinding(BaseModel):
    """One label's fused result across a multi-view study.

    `probability` is the MAX banded confidence across the study's non-abstained
    views (safety-favouring: a one-view finding is not diluted). `view`/`image_id`
    name the projection that produced that max; `per_view` maps image_id -> that
    image's banded confidence for the label (for a per-view findings table).
    """
    label: str
    probability: float
    calibrated_probability: Optional[float] = None
    flagged: bool = False
    view: str = "Frontal"
    image_id: str = ""
    per_view: dict[str, float] = Field(default_factory=dict)
    fusion_mode: str = "max"  # how `probability` was combined across views


class StudyResponse(BaseModel):
    """Result of /api/analyze-study: per-image analyses + the fused block."""
    study_id: str
    images: list[AnalyzeResponse] = Field(default_factory=list)
    fused: list[FusedFinding] = Field(default_factory=list)
    top_finding: Optional[str] = None
    triage: str = "routine"  # worst per-image triage
    triage_reasons: list[str] = Field(default_factory=list)
    n_abstained: int = 0  # images the self-audit gate refused (excluded from fusion)
    disclaimer: str


class StructuredFindings(BaseModel):
    # Positive attestation so an all-negative form is a reviewed "no acute
    # abnormality", distinguishable from an untouched/unreviewed form.
    reviewed_no_acute: bool = False

    nodule_present: bool = False
    nodule_size_mm: Optional[float] = None  # clinician-entered (caliper), not AI
    nodule_location: Optional[str] = None  # RUL/RML/RLL/LUL/LLL
    pleural_effusion: bool = False
    effusion_side: Optional[str] = None  # right/left/bilateral
    pneumothorax: bool = False
    pneumothorax_side: Optional[str] = None  # right/left
    consolidation: bool = False
    consolidation_location: Optional[str] = None
    cardiomegaly: bool = False
    rib_fracture: bool = False  # clinician-entered; no AI rib-fracture claim
    free_text: str = ""


class Attestation(BaseModel):
    """Explicit human sign-off. No sign-off => no final report / export."""
    attested: bool = False
    reviewer_name: str = ""


class ComparisonRow(BaseModel):
    label: str
    prior_probability: float
    current_probability: float
    change: str  # stable | new | worsened | improved | resolved


class ComparisonSummary(BaseModel):
    prior_date: Optional[str] = None
    rows: list[ComparisonRow] = Field(default_factory=list)
    summary: str = ""

    def rows_text(self) -> str:
        if not self.rows:
            return ""
        return "\n".join(
            f"- {r.label}: {r.change} (prior model confidence {r.prior_probability:.0%} "
            f"→ current {r.current_probability:.0%})"
            for r in self.rows
        )


class ReportRequest(BaseModel):
    modality: str = "Chest X-ray (PA)"
    clinical_history: str = ""
    # `structured` = clinician-CONFIRMED findings only. AI suggestions live in
    # `vision_findings` and are never treated as confirmed unless the clinician
    # adopted them into `structured`.
    structured: StructuredFindings = Field(default_factory=StructuredFindings)
    vision_findings: list[Finding] = Field(default_factory=list)
    comparison: Optional[ComparisonSummary] = None
    triage: str = "routine"
    attestation: Attestation = Field(default_factory=Attestation)


class CompletenessItem(BaseModel):
    severity: str  # info | warn
    category: str  # discordance | empty-section | borderline
    label: str
    message: str


class ReportResponse(BaseModel):
    clinical: str
    patient: str
    differentials: str
    comparison_summary: Optional[str] = None
    triage: str = "routine"
    triage_reasons: list[str] = Field(default_factory=list)
    completeness: list[CompletenessItem] = Field(default_factory=list)
    generator: str  # which LLM produced it, or "template"
    disclaimer: str


class FeedbackEvent(BaseModel):
    """A single reviewer signal. SELF-CONTAINED by design: it carries no foreign key
    into TTL'd storage (so it survives the storage sweep) and is PHI-free by
    construction — every field is an enum, number, content-hash, or short pathology
    label, all length-capped, with NO free-text identifier field.

    The most valuable signal is `confirmed` / `dismissed` (labeled ground truth from
    a clinician), not the thumbs. Model + calibration versions are injected
    server-side. The public-image content hash lets a training flywheel close on
    NIH/Open-i images (documented limitation: user uploads are TTL'd, so their events
    are auditable but not trainable)."""
    # Event kind — confirm/dismiss are the labeled-ground-truth training signal.
    event: Literal["confirmed", "dismissed", "thumb_up", "thumb_down"] = "thumb_up"
    # Self-contained context (all optional; enums/numbers/hash/short label only):
    image_sha256: Optional[str] = Field(default=None, max_length=64)
    image_source: Optional[str] = Field(default=None, max_length=32)  # nih|openi|user_upload
    raw_label: Optional[str] = Field(default=None, max_length=64)
    display_label: Optional[str] = Field(default=None, max_length=80)
    raw_score: Optional[float] = None
    calibrated_p: Optional[float] = None
    calibration_state: Optional[str] = Field(default=None, max_length=24)
    heatmap_state: Optional[str] = Field(default=None, max_length=24)
    threshold: Optional[float] = None
    # Back-compat thumbs fields (optional; superseded by `event`).
    target: Optional[Literal["finding", "report"]] = None
    rating: Optional[Literal["up", "down"]] = None
    label: Optional[str] = Field(default=None, max_length=64)
    model_note: Optional[str] = Field(default=None, max_length=280)
    action: Optional[str] = Field(default=None, max_length=32)
    timestamp: Optional[str] = Field(default=None, max_length=40)
