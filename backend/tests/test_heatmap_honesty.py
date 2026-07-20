"""Heatmap-honesty invariants — the guards that keep a Grad-CAM overlay from
lying: explicit localization state, no crisp contour at a coarse grid, no
whole-frame haze, and burned-in markers inpainted before inference.

All pure numpy/cv2 — no torch, no model weights — so they run in CI. The
end-to-end marker-ablation delta (needs the real model) stays in
tools/marker_ablation.py, run against real films."""
import numpy as np

from app import config
from app.services import vision_xray as vx


def _focal_cam(size=224, cx=0.5, cy=0.5, sigma=8):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    return np.exp(-(((yy - cy * size) ** 2 + (xx - cx * size) ** 2) / (2 * sigma ** 2)))


def test_classify_empty_cam_is_none():
    state, contour_ok = vx._classify_cam(np.zeros((224, 224), np.float32), 7)
    assert state == "none"
    assert contour_ok is False


def test_classify_spread_cam_is_diffuse():
    # A CAM hot across most of the frame is non-specific -> diffuse, never outlined.
    cam = np.ones((224, 224), np.float32)
    state, contour_ok = vx._classify_cam(cam, 7)
    assert state == "diffuse"
    assert contour_ok is False


def test_tight_blob_at_7x7_is_diffuse_no_overlay():
    # T7: a hot blob spanning fewer than min_cells NATIVE cells at 7x7 is the
    # upsampler ("diamond"), NOT structure -> classified 'diffuse' -> no overlay.
    state, contour_ok = vx._classify_cam(_focal_cam(sigma=8), native_grid=7)
    assert state == "diffuse"
    assert contour_ok is False


def test_broad_focal_at_7x7_is_localized_but_no_contour():
    # A blob spanning >= min_cells cells (but not diffuse) is 'localized' — a soft
    # gradient, never a crisp contour at 7x7.
    state, contour_ok = vx._classify_cam(_focal_cam(sigma=45), native_grid=7)
    assert state == "localized"
    assert contour_ok is False


def test_contour_only_allowed_at_fine_grid():
    # The same focal map at a 16x16 grid MAY be outlined.
    _state, contour_ok = vx._classify_cam(_focal_cam(sigma=28), native_grid=16)
    assert contour_ok is True


def test_marker_masking_removes_corner_and_preserves_center():
    img = np.full((512, 512), 90, np.uint8)
    # A bright focal 'finding' in the centre must survive.
    img[240:270, 240:270] = 250
    center_before = int((img[235:275, 235:275] >= 235).sum())
    # A burned-in white marker in the top-right corner must be inpainted away.
    img[20:60, 430:495] = 255
    out, n = vx._mask_burned_in_markers(img)
    assert n > 0, "should inpaint the corner marker"
    assert int((out[:70, 420:] >= 235).sum()) < center_before, "marker should be gone"
    assert int((out[235:275, 235:275] >= 235).sum()) >= center_before, "centre finding preserved"


def test_overlay_diffuse_map_does_not_haze_whole_frame(tmp_path):
    import cv2
    img = np.full((256, 256), 90, np.uint8)
    flat = np.full((256, 256), 0.2, np.float32)  # no contrast -> no manufactured heat
    out = tmp_path / "flat.png"
    vx._save_overlay(img, flat, None, out, contour=None, draw_contour=False)
    ov = cv2.imread(str(out))
    base = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR).astype(int)
    tint = (np.abs(ov.astype(int) - base).sum(2) > 25).mean()
    assert tint < 0.05, "a flat/uncertain CAM must not tint the whole frame"


def test_colormap_is_never_jet():
    # Only inferno or cividis — never jet/rainbow (measured higher diagnostic error).
    import cv2
    assert vx._colormap() in (cv2.COLORMAP_INFERNO, cv2.COLORMAP_CIVIDIS)


def test_native_grid_never_faked_without_localizer():
    # The grid must reflect the ACTUAL densenet CAM (7), never be inferred as 16
    # from an env var while the CAM is still 7x7 (which would fake crisp contours).
    assert config.native_cam_grid() == 7
