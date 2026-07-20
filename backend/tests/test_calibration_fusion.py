"""Calibration + fusion + compare-noise-floor + password-hashing invariants.
All torch-free."""
from app import auth
from app.models.schemas import AnalyzeResponse, Finding
from app.services import calibration, compare, fusion


# ---- calibration ----------------------------------------------------------
def test_isotonic_interpolation(monkeypatch):
    monkeypatch.setattr(calibration.config, "CALIBRATION_MODE", "isotonic")
    calibration._map = {"mode": "isotonic",
                        "per_label": {"Effusion": {"x": [0.0, 0.5, 1.0], "y": [0.0, 0.1, 0.8]}}}
    assert abs(calibration.calibrate("Effusion", 0.5) - 0.1) < 1e-6
    assert abs(calibration.calibrate("Effusion", 0.25) - 0.05) < 1e-6  # midpoint interp
    assert calibration.calibrate("Unknown", 0.5) is None
    calibration._map = None  # reset for other tests


def test_calibration_none_mode(monkeypatch):
    monkeypatch.setattr(calibration.config, "CALIBRATION_MODE", "none")
    assert calibration.calibrate("Effusion", 0.5) is None


# ---- fusion ---------------------------------------------------------------
def _img(view, comp, findings):
    return AnalyzeResponse(image_id=view.lower(), image_url="", competence=comp,
                           view=view, findings=findings, disclaimer="d")


def test_fusion_max_never_dilutes(monkeypatch):
    monkeypatch.setattr(fusion.config, "FUSION_MODE", "max")
    imgs = [_img("PA", "read", [Finding(label="Mass", probability=0.9, flagged=True)]),
            _img("Lateral", "read", [Finding(label="Mass", probability=0.2)])]
    fused = fusion.fuse_findings(imgs)
    assert fused[0].probability == 0.9 and fused[0].flagged is True


def test_downweighted_view_cannot_drive_fusion(monkeypatch):
    monkeypatch.setattr(fusion.config, "FUSION_MODE", "max")
    monkeypatch.setattr(fusion.config, "DOWNWEIGHT_FUSION_FACTOR", 0.5)
    imgs = [_img("PA", "read", [Finding(label="Edema", probability=0.4, flagged=False)]),
            _img("Lateral", "down-weight", [Finding(label="Edema", probability=0.8, flagged=True)])]
    fused = fusion.fuse_findings(imgs)
    # 0.8 * 0.5 = 0.4 -> the down-weighted view no longer exceeds the read view.
    assert fused[0].probability <= 0.4001
    # per_view still shows the raw 0.8 for transparency.
    assert fused[0].per_view.get("lateral") == 0.8


def test_fusion_calibrated_mean(monkeypatch):
    monkeypatch.setattr(fusion.config, "FUSION_MODE", "calibrated_mean")
    imgs = [_img("PA", "read", [Finding(label="Mass", probability=0.9,
                                        calibrated_probability=0.3, flagged=True)]),
            _img("AP", "read", [Finding(label="Mass", probability=0.7,
                                        calibrated_probability=0.1)])]
    fused = fusion.fuse_findings(imgs)
    assert fused[0].fusion_mode == "calibrated_mean"
    assert abs(fused[0].probability - 0.2) < 1e-6  # mean(0.3, 0.1)


# ---- compare noise floor --------------------------------------------------
def test_compare_suppresses_within_noise(monkeypatch):
    monkeypatch.setattr(compare.config, "COMPARE_MIN_DELTA_MODE", "perturbation_std")
    monkeypatch.setattr(compare.config, "COMPARE_NOISE_K", 2.0)
    compare._pstats = {"per_label": {"Effusion": {"std": 0.03}}}
    # 0.49 -> 0.53 crosses threshold but is within 2*0.03=0.06 noise -> stable.
    change, within = compare._classify("Effusion", 0.49, 0.53)
    assert change == "stable" and within is True
    # A large delta is still reported.
    change2, within2 = compare._classify("Effusion", 0.49, 0.75)
    assert change2 == "new" and within2 is False
    compare._pstats = None


# ---- password hashing -----------------------------------------------------
def test_scrypt_roundtrip_and_legacy_compat():
    h = auth.hash_password("s3cret")
    assert h.startswith("scrypt$")
    assert auth._verify_password("s3cret", h) is True
    assert auth._verify_password("wrong", h) is False
    # legacy unsalted sha256 still verifies (backward compat).
    legacy = auth._sha256_hex("old")
    assert auth._verify_password("old", legacy) is True
