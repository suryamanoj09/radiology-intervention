"""Anatomy-overlay segmentation schema — TABOO-FREE BY CONSTRUCTION.

The CT/MRI anatomy overlay labels/segments anatomy and measures regions ONLY; it
never detects, characterizes, or excludes disease. To make that boundary STRUCTURAL
rather than a matter of copy discipline, every model here subclasses `_TabooFree`,
whose import-time guard raises TypeError if ANY field name/alias is (or contains) a
diagnosis-shaped token. So a field like `probability`, `finding`, `severity`, or
`malignancy` cannot be added to a segment model even by mistake — the module fails
to import. This is the schema-level half of the guarantee; the config whitelist
(commercial_ok AND anatomy_only) is the license/behaviour half.

These models deliberately do NOT reuse schemas.Finding / AnalyzeResponse — sharing
that code would re-introduce probability/flagged/triage fields into this path.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import config

# Diagnosis-shaped tokens. Split-on-nonalnum whole tokens (exact) + substrings
# (containment) are both checked, so neither `probability` nor `xprobabilityy`
# can slip through. `coverage`/`confidence` are intentionally forbidden so no
# probability-shaped field can masquerade as "segmentation coverage".
FORBIDDEN_TOKENS = frozenset({
    "finding", "findings", "probability", "prob", "score", "scores", "impression",
    "severity", "severe", "malignancy", "malignant", "benign", "abnormal", "abnormality",
    "diagnosis", "diagnostic", "diagnose", "positive", "negative", "suspicious", "suspect",
    "detected", "detect", "found", "lesion", "tumor", "tumour", "cancer", "mass", "nodule",
    "bleed", "hemorrhage", "haemorrhage", "infarct", "stroke", "aneurysm", "effusion",
    "edema", "oedema", "fracture", "stenosis", "pathology", "disease", "normal",
    "confidence", "likelihood", "risk", "grade", "birads", "lirads", "pirads",
    "flag", "flagged", "triage", "urgent", "coverage", "heatmap",
})
FORBIDDEN_SUBSTRINGS = (
    "finding", "probab", "impression", "malign", "abnormal", "diagnos", "suspic",
    "lesion", "tumor", "tumour", "cancer", "hemorrha", "haemorrha", "infarct",
    "patholog", "birads", "lirads", "pirads", "heatmap", "coverage", "confidence",
)


def _assert_clean_name(name: str, owner: str) -> None:
    low = name.lower()
    tokens = [t for t in low.replace("-", "_").split("_") if t]
    for t in tokens:
        if t in FORBIDDEN_TOKENS:
            raise TypeError(
                f"{owner}.{name}: diagnosis-shaped field token '{t}' is forbidden on an "
                f"anatomy-overlay model (the overlay labels anatomy, never disease).")
    for sub in FORBIDDEN_SUBSTRINGS:
        if sub in low:
            raise TypeError(
                f"{owner}.{name}: field name contains forbidden substring '{sub}' — "
                f"anatomy-overlay models must carry no diagnosis-shaped field.")


class _TabooFree(BaseModel):
    """Base whose subclasses are scanned at import; any diagnosis-shaped field name
    aborts the import."""
    # `model` is a mandated provenance field name; silence pydantic's protected-namespace warning.
    model_config = ConfigDict(protected_namespaces=())

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs):
        super().__pydantic_init_subclass__(**kwargs)
        for fname, finfo in cls.model_fields.items():
            _assert_clean_name(fname, cls.__name__)
            # Scan every alias form — a diagnosis-shaped serialization_alias would be
            # the emitted JSON key (FastAPI serializes by_alias), so it must be caught
            # too, not just `alias`.
            for attr in ("alias", "serialization_alias", "validation_alias"):
                al = getattr(finfo, attr, None)
                if isinstance(al, str):
                    _assert_clean_name(al, cls.__name__)


class Contour(_TabooFree):
    """A single-slice boundary polygon in ORIGINAL-raster pixel coords ([col, row])."""
    slice_index: int = Field(ge=0)
    polygon: list[list[int]] = Field(default_factory=list, max_length=8192)


class Region(_TabooFree):
    """One labeled anatomical/tissue region + its GEOMETRIC measurements. The unified
    shape for classical-CT (HU band), classical-MR (intensity band), and any future
    organ-segmentation model. Colors encode tissue/organ IDENTITY only, never alarm."""
    structure_id: int = Field(ge=0)
    label: str = Field(max_length=64)  # anatomy/tissue noun from a closed vocabulary
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    volume_ml: Optional[float] = Field(default=None, ge=0)
    voxel_count: Optional[int] = Field(default=None, ge=0)
    area_mm2: Optional[float] = Field(default=None, ge=0)
    # A measurement (HU or a.u.), NOT a score. MR intensity is arbitrary/relative.
    mean_intensity: Optional[float] = None
    intensity_unit: Literal["HU", "a.u."] = "HU"
    # Classical-CT band bounds [lo, hi] HU; None for MR / organ models.
    hu_range: Optional[list[float]] = Field(default=None, max_length=2)
    n_components: Optional[int] = Field(default=None, ge=0)
    contours: list[Contour] = Field(default_factory=list)
    mask_url: Optional[str] = None
    method: str = "hu-threshold-v1"
    model: str = "classical-hu-threshold"
    license: str = "no-model (scipy/numpy BSD-3-Clause)"
    timestamp: Optional[str] = None

    @field_validator("license")
    @classmethod
    def _license_must_be_clean(cls, v: str) -> str:
        if v not in config.CLEAN_LICENSES:
            raise ValueError(f"license '{v}' is not in CLEAN_LICENSES (license-clean weights only)")
        return v


class SegmentResponse(_TabooFree):
    """The anatomy-overlay response. Contains NO diagnosis-shaped field; a required
    `disclaimer` (router injects the CT/MR overlay disclaimer) travels with every
    response so the boundary is never dropped."""
    job_id: str
    view_id: Optional[str] = None
    status: Literal["queued", "running", "done", "error", "unknown"] = "queued"
    modality: Literal["CT", "MR"]
    intensity_unit: Literal["HU", "a.u."] = "HU"
    regions: list[Region] = Field(default_factory=list)
    structure_count: int = 0
    model: str = "classical-hu-threshold"
    license: str = "no-model (scipy/numpy BSD-3-Clause)"
    method: str = "hu-threshold-v1"
    provenance: Optional[str] = None
    identifiers_removed: int = 0
    n_quarantined: int = 0
    burned_in: Literal["YES", "NO", "UNKNOWN"] = "UNKNOWN"
    computed: bool = False
    n_slices: int = 0
    # Opaque id of the series that was segmented (== the viewer's series_id), so the
    # frontend refuses to paint a mask onto a DIFFERENT series.
    series_id: Optional[str] = None
    # Ordered geometric positions, one per mask slice, so the overlay aligns to the
    # viewer BY POSITION (the two paths cap/downscale differently, so array offsets
    # do not correspond).
    slice_positions: Optional[list[float]] = None
    # Indexed label PNG per slice (mode L; pixel value == structure_id, 0 = unlabeled).
    # The frontend recolors it through the categorical legend. One entry per slice
    # index, aligned to the segmented series' geometric ordering.
    mask_urls: Optional[list[str]] = None
    mask_edge: Optional[int] = None  # native mask pixel size (frontend scales to fit)
    timestamp: Optional[str] = None
    detail: Optional[str] = None  # human-readable job/error note (never a diagnosis)
    disclaimer: str  # REQUIRED — no default; router injects CT/MR_OVERLAY_DISCLAIMER
