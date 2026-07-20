"""Self-audit / abstention gate + behaviour-card endpoint (AE disabled in tests)."""

import io

import numpy as np
from PIL import Image

from app.services import dicom_utils, self_audit


def _png(arr) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return buf.getvalue()


def test_color_photo_is_refused():
    # A coherent color image (high saturation) is not a radiograph -> ABSTAIN.
    col = np.zeros((120, 140, 3), dtype=np.uint8)
    col[..., 0], col[..., 1], col[..., 2] = 200, 60, 30
    img8, _s, _m, _f, meta = dicom_utils.load_any(_png(col), "photo.png")
    r = self_audit.assess(img8, meta.get("color_saturation", 0.0))
    assert r["competence"] == "abstain"
    assert any("color" in x.lower() for x in r["reasons"])


def test_plausible_grayscale_reads():
    rng = np.random.default_rng(1)
    g = rng.integers(30, 220, (256, 256)).astype(np.uint8)
    img8, _s, _m, _f, meta = dicom_utils.load_any(_png(g), "cxr.png")
    r = self_audit.assess(img8, meta.get("color_saturation", 0.0))
    assert r["competence"] == "read"


def test_blank_image_is_not_read():
    blank = np.full((256, 256), 128, dtype=np.uint8)
    img8, _s, _m, _f, meta = dicom_utils.load_any(_png(blank), "blank.png")
    r = self_audit.assess(img8, meta.get("color_saturation", 0.0))
    assert r["competence"] in ("down-weight", "abstain")  # never a confident READ


def test_analyze_refuses_color_photo_end_to_end(client):
    col = np.zeros((120, 140, 3), dtype=np.uint8)
    col[..., 0], col[..., 1], col[..., 2] = 210, 40, 40
    r = client.post("/api/analyze", files={"file": ("dog.png", _png(col), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["competence"] == "abstain"
    assert body["findings"] == []


def _synthetic_square() -> np.ndarray:
    """A white square on a mid-grey field with a black border — the exact class of
    non-anatomical test image that must NOT be scored as a chest radiograph."""
    a = np.zeros((256, 256), dtype=np.uint8)
    a[40:216, 40:216] = 128   # grey field
    a[96:160, 96:160] = 255   # white square
    return a


def test_synthetic_shape_is_refused():
    # A grayscale geometric test pattern (flat fills, few grey levels) is NOT a
    # radiograph -> ABSTAIN, even though it is grey and high-contrast (so the color
    # and AE signals do not fire).
    r = self_audit.assess(_synthetic_square(), 0.0)
    assert r["competence"] == "abstain", r
    assert any("synthetic" in x.lower() or "flat" in x.lower() for x in r["reasons"])


def test_analyze_refuses_synthetic_shape_end_to_end(client):
    r = client.post("/api/analyze",
                    files={"file": ("shape.png", _png(_synthetic_square()), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["competence"] == "abstain"
    assert body["findings"] == []   # no disease reported on a non-radiograph


def test_plausible_grayscale_still_reads_after_structure_gate():
    # Guard against over-blocking: organic-texture grayscale must still READ.
    rng = np.random.default_rng(7)
    g = rng.integers(30, 220, (256, 256)).astype(np.uint8)
    assert self_audit.assess(g, 0.0)["competence"] == "read"


def _smooth_ramp() -> np.ndarray:
    """A near-perfectly smooth grayscale gradient — obviously NOT a radiograph, yet
    it is NOT flat (values vary) and has HIGH entropy, so the flat/entropy detectors
    miss it. It has no radiographic high-frequency texture, which the smoothness
    signal catches (FIX #5)."""
    return np.tile(np.linspace(0, 255, 256).astype(np.uint8), (256, 1))


def test_smooth_gradient_non_chest_is_refused():
    # FIX #5 — a rendered smooth gradient (obviously non-radiograph) must ABSTAIN.
    r = self_audit.assess(_smooth_ramp(), 0.0)
    assert r["competence"] == "abstain", r
    assert any("smooth" in x.lower() for x in r["reasons"])


def test_smooth_gradient_refused_end_to_end(client):
    r = client.post("/api/analyze",
                    files={"file": ("ramp.png", _png(_smooth_ramp()), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["competence"] == "abstain"
    assert body["findings"] == []


def test_smoothness_gate_does_not_over_abstain_textured_film():
    # Guard against over-blocking: a textured (aperiodic) grayscale image still READs;
    # the smoothness bar is deliberately extreme so real films are not refused.
    rng = np.random.default_rng(11)
    g = rng.integers(20, 235, (256, 256)).astype(np.uint8)
    assert self_audit.assess(g, 0.0)["competence"] == "read"


def test_behavior_card_endpoint(client):
    r = client.get("/api/behavior-card")
    assert r.status_code == 200
    assert "available" in r.json()
