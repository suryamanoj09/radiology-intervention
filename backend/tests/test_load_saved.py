"""load_saved / GET /api/analysis: strict image-id validation defeats path
traversal, and a legitimately stored analysis round-trips."""

from app import config
from app.models.schemas import AnalyzeResponse, Finding
from app.services import vision_xray


def _store(image_id: str) -> AnalyzeResponse:
    resp = AnalyzeResponse(
        image_id=image_id,
        image_url=f"/static/uploads/{image_id}.png",
        findings=[Finding(label="Effusion", probability=0.7, flagged=True)],
        triage="priority",
        disclaimer=config.DISCLAIMER,
    )
    (config.ANALYSIS_DIR / f"{image_id}.json").write_text(
        resp.model_dump_json(), encoding="utf-8")
    return resp


def test_load_saved_rejects_traversal_ids():
    assert vision_xray.load_saved("../../x") is None
    assert vision_xray.load_saved("../../../etc/passwd") is None
    assert vision_xray.load_saved("..\\..\\secret") is None
    assert vision_xray.load_saved("") is None
    assert vision_xray.load_saved("BADUPPER0000") is None  # uppercase not allowed
    assert vision_xray.load_saved("short") is None          # wrong length


def test_load_saved_round_trips_a_valid_id():
    image_id = "abcdef012345"
    _store(image_id)
    loaded = vision_xray.load_saved(image_id)
    assert loaded is not None
    assert loaded.image_id == image_id
    assert loaded.findings[0].label == "Effusion"


def test_analysis_endpoint_returns_stored(client):
    image_id = "0123456789ab"
    _store(image_id)
    r = client.get(f"/api/analysis/{image_id}")
    assert r.status_code == 200, r.text
    assert r.json()["image_id"] == image_id


def test_analysis_endpoint_unknown_id_404(client):
    r = client.get("/api/analysis/ffffffffffff")
    assert r.status_code == 404
