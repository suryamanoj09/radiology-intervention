"""Patient-intake-stays-client-side invariant (issue #5), extended to EVERY
server response model — not just AnalyzeResponse.

The demo lets a clinician type patient name/age/phone for the printed report, but
those identifiers must never appear in a server request/response schema or be
persisted. This is a by-construction guard: no response model may declare an
identifier-looking field. If someone adds `patient_name`/`patient_age`/`phone`
to StudyResponse or a report model, this fails immediately.

Token-based matching (field name split on '_') so we flag `patient_age` but not
the legitimate `image_id` / `triage` / `patient` (plain-language section) fields.
"""

from app.models import schemas
from app.models import segment as segment_models

# Whole-token identifier hints. 'patient' is intentionally NOT here: a field
# literally named `patient` in ReportResponse is the plain-language SECTION, and
# real PHI fields (patient_name, patient_age) are already caught by name/age.
_IDENTIFIER_TOKENS = {
    "name", "phone", "dob", "birth", "birthdate", "mrn", "address",
    "ssn", "age", "email", "gender", "sex", "insurance",
}

# Every model the SERVER returns to the client. (Request-only models a clinician
# fills in — e.g. Attestation.reviewer_name — are excluded: reviewer identity is
# not patient PHI and is never persisted server-side.)
_RESPONSE_MODELS = [
    schemas.AnalyzeResponse,
    schemas.Finding,
    schemas.FusedFinding,
    schemas.StudyResponse,
    schemas.ReportResponse,
    schemas.CompletenessItem,
    schemas.ComparisonSummary,
    schemas.ComparisonRow,
    schemas.BBox,
    # Anatomy-overlay models are also returned to the client — hold them to the
    # same no-identifier-field bar.
    segment_models.Region,
    segment_models.SegmentResponse,
    segment_models.Contour,
]


def _looks_like_identifier(field: str) -> bool:
    return bool(set(field.lower().split("_")) & _IDENTIFIER_TOKENS)


def test_no_response_model_declares_a_patient_identifier_field():
    offenders = [
        f"{model.__name__}.{field}"
        for model in _RESPONSE_MODELS
        for field in model.model_fields
        if _looks_like_identifier(field)
    ]
    assert not offenders, (
        "Patient identifiers must stay client-side; these server-response fields "
        f"look like PHI: {offenders}")


def test_study_response_serializes_without_identifier_keys():
    resp = schemas.StudyResponse(study_id="deadbeef", disclaimer="d")
    dumped = resp.model_dump()
    assert not any(_looks_like_identifier(k) for k in dumped), (
        f"StudyResponse serialization leaked an identifier-shaped key: {list(dumped)}")
