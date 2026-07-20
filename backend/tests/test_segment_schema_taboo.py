"""The anatomy-overlay schema is TABOO-FREE by construction: no diagnosis-shaped
field can exist on a segment model, enforced at import by the _TabooFree guard."""
import pytest

from app.models.segment import Contour, Region, SegmentResponse, _TabooFree

_FORBIDDEN = ("finding", "probability", "score", "impression", "severity",
              "malignancy", "abnormal", "diagnosis", "coverage", "confidence",
              "flagged", "triage", "heatmap", "lesion", "tumor")


def _all_field_names(model):
    return set(model.model_fields)


def test_region_and_response_field_sets_are_clean():
    for model in (Region, SegmentResponse, Contour):
        for f in _all_field_names(model):
            low = f.lower()
            for bad in _FORBIDDEN:
                assert bad not in low, f"{model.__name__}.{f} contains forbidden token {bad!r}"


def test_defining_a_taboo_field_aborts_at_import():
    # The guard raises TypeError the moment a subclass declares a taboo field.
    with pytest.raises(TypeError):
        class _Bad(_TabooFree):
            probability: float = 0.0
    with pytest.raises(TypeError):
        class _Bad2(_TabooFree):
            malignancy_grade: int = 0


def test_region_rejects_non_clean_license():
    with pytest.raises(Exception):
        Region(structure_id=1, label="lung", color="#4da3ff", license="proprietary-secret")


def test_region_accepts_clean_baseline():
    r = Region(structure_id=1, label="lung field", color="#4da3ff",
               volume_ml=12.0, intensity_unit="HU")
    assert r.model == "classical-hu-threshold" and r.volume_ml == 12.0


def test_segment_response_requires_disclaimer():
    with pytest.raises(Exception):
        SegmentResponse(job_id="x", modality="CT")  # no disclaimer -> invalid
    ok = SegmentResponse(job_id="x", modality="CT", disclaimer="not a diagnosis; not a medical device")
    assert ok.status == "queued"


def test_response_recursive_json_has_no_diagnosis_key():
    resp = SegmentResponse(
        job_id="a" * 32, modality="CT", disclaimer="d",
        regions=[Region(structure_id=1, label="lung", color="#4da3ff")],
    )
    import json
    blob = json.loads(resp.model_dump_json())

    def keys(o):
        out = []
        if isinstance(o, dict):
            for k, v in o.items():
                out.append(k)
                out += keys(v)
        elif isinstance(o, list):
            for v in o:
                out += keys(v)
        return out

    for k in keys(blob):
        for bad in _FORBIDDEN:
            assert bad not in k.lower(), f"leaked diagnosis-shaped key {k!r}"
