"""Classical CT HU-threshold labeler: deterministic + reads the 16-bit HU volume
(never the 8-bit windowed PNG) + geometry-correct volumes + anatomy-only labels."""
import numpy as np
import pytest

from app.services import tissue_seg


def _phantom(z=4, size=48):
    """Two well-separated pure-HU slabs on an air field (no nesting, so morphology
    can't distort the means): soft tissue (50 HU) and cortical bone (800 HU)."""
    hu = np.full((z, size, size), -1000, np.int16)
    hu[:, 6:20, 6:42] = 50    # soft-tissue slab
    hu[:, 28:42, 6:42] = 800  # bone slab (air gap between them)
    return hu


def test_labeler_refuses_non_ct():
    with pytest.raises(ValueError):
        tissue_seg.label_tissue(_phantom(), (1.0, 1.0, 2.0), is_ct=False)


def test_mean_intensity_is_the_true_HU_not_a_windowed_value():
    regions, _ = tissue_seg.label_tissue(_phantom(), (1.0, 1.0, 2.0), is_ct=True)
    soft = next(r for r in regions if "soft tissue" in r["label"])
    bone = next(r for r in regions if "cortical bone" in r["label"])
    # Exact HU means prove the labeler read the int16 HU array, not an 8-bit PNG
    # (a windowed PNG could never round-trip 50 and 800 HU exactly).
    assert soft["mean_intensity"] == 50.0
    assert bone["mean_intensity"] == 800.0
    assert soft["intensity_unit"] == "HU"


def test_deterministic_byte_identical_across_runs():
    hu = _phantom()
    r1, lv1 = tissue_seg.label_tissue(hu, (1.0, 1.0, 2.0), is_ct=True)
    r2, lv2 = tissue_seg.label_tissue(hu, (1.0, 1.0, 2.0), is_ct=True)
    assert np.array_equal(lv1, lv2)
    assert r1 == r2


def test_volume_scales_with_anisotropic_z_spacing():
    hu = _phantom()
    r2, _ = tissue_seg.label_tissue(hu, (1.0, 1.0, 2.0), is_ct=True)
    r4, _ = tissue_seg.label_tissue(hu, (1.0, 1.0, 4.0), is_ct=True)
    b2 = next(r for r in r2 if "cortical bone" in r["label"])
    b4 = next(r for r in r4 if "cortical bone" in r["label"])
    assert b2["voxel_count"] == b4["voxel_count"]        # same voxels
    assert abs(b4["volume_ml"] - 2 * b2["volume_ml"]) < 1e-9  # z doubled -> volume doubled


def test_volume_none_when_spacing_absent():
    regions, _ = tissue_seg.label_tissue(_phantom(), (None, None, None), is_ct=True)
    assert all(r["volume_ml"] is None and r["area_mm2"] is None for r in regions)


def test_labels_are_anatomy_nouns_only():
    regions, _ = tissue_seg.label_tissue(_phantom(), (1.0, 1.0, 2.0), is_ct=True)
    bad = ("finding", "probab", "lesion", "tumor", "cancer", "abnormal",
           "diagnos", "disease", "malign", "suspic", "score")
    for r in regions:
        low = r["label"].lower()
        assert not any(b in low for b in bad), f"non-anatomy label: {r['label']}"


def test_label_vol_and_region_counts_agree():
    # Stats come from the final label_vol, so painted mask area == reported voxel_count.
    regions, lv = tissue_seg.label_tissue(_phantom(), (1.0, 1.0, 2.0), is_ct=True)
    for r in regions:
        assert int((lv == r["structure_id"]).sum()) == r["voxel_count"]
