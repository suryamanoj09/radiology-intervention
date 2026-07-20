"""Anatomy-overlay segmentation provider seam (opt-in, NON-DIAGNOSTIC).

The CLASSICAL providers (tissue_seg for CT, mr_classical_seg for MR) are ALWAYS
available and are the ship-now, CPU-instant, weight-free baseline. A heavy provider
(TotalSegmentator / SynthSeg) is a DESIGNED, wired seam that is NOT installed in this
build: `_heavy_available()` self-gates on the optional import (exactly like
localizer.available()), so the dispatcher safely falls back to classical whenever the
heavy weights are absent. Every provider returns (regions, label_vol) — regions is a
list of taboo-free Region dicts, label_vol is a (Z,H,W) uint8 volume of structure_ids.

License/anatomy enforcement (config.assert_task_allowed) happens BEFORE any heavy
weight loads; the router also enforces it at the API boundary for any explicit task.
"""
import logging

from .. import config

logger = logging.getLogger(__name__)

_heavy_failed = False
_heavy_warned = False


def _heavy_available() -> bool:
    """The heavy TotalSegmentator/SynthSeg provider is a documented seam that is NOT
    implemented/installed in this build, so this is False. Enabling it is a follow-up
    (install requirements-segment.txt + implement _heavy_segment). Kept as the single
    gate so the rest of the pipeline is already wired for it."""
    global _heavy_failed, _heavy_warned
    if _heavy_failed:
        return False
    try:
        import totalsegmentator  # noqa: F401  (optional; absent in the classical ship)
        # Import succeeded but the execution seam is intentionally not implemented yet.
        if not _heavy_warned:
            logger.warning("TotalSegmentator is importable but the heavy provider seam "
                           "is not implemented in this build; using the classical baseline.")
            _heavy_warned = True
        return False
    except Exception:
        _heavy_failed = True
        return False


def available(modality: str) -> bool:
    """Whether segmentation can run for `modality`. Classical is always available for
    CT and MR; the heavy provider self-gates on its optional import."""
    if config.SEGMENT_MODEL == "classical":
        return True
    return _heavy_available()


def active_provider(is_ct: bool) -> tuple[str, str, str]:
    """(method, model, license) of the provider that WILL run — makes the response
    transparent about what produced the regions."""
    if config.SEGMENT_MODEL != "classical" and _heavy_available():
        return ("totalsegmentator", "total" if is_ct else "total_mr", "Apache-2.0")
    if is_ct:
        return ("hu-threshold-v1", "classical-hu-threshold", "no-model (scipy/numpy BSD-3-Clause)")
    return ("mr-intensity-cluster-v1", "classical-mr-intensity",
            "no-model (scipy/numpy/scikit-image BSD-3-Clause)")


def segment(volume: dict, *, task: str | None = None, roi_subset=None):
    """Run the active provider on a build_seg_volume() dict. Returns (regions, label_vol).

    Fails closed: if a heavy task is selected, config.assert_task_allowed(task) runs
    FIRST (before any weight loads) and ModelNotAllowed propagates to the router (403).
    In the classical ship this always dispatches to the deterministic HU/intensity
    baseline."""
    hu = volume["hu"]
    spacing = volume["spacing_mm"]
    is_ct = volume["is_ct"]

    if config.SEGMENT_MODEL != "classical" and _heavy_available():
        t = task or ("total" if is_ct else "total_mr")
        config.assert_task_allowed(t)  # ModelNotAllowed -> router 403
        return _heavy_segment(volume, t, roi_subset)

    # Classical baseline (always available). Guard is still asserted so the
    # always-allowed classical model is on the same code path.
    if is_ct:
        config.assert_model_allowed("classical-hu-threshold")
        from . import tissue_seg
        return tissue_seg.label_tissue(hu, spacing, is_ct=True)
    config.assert_model_allowed("classical-mr-intensity")
    from . import mr_classical_seg
    return mr_classical_seg.label_mr(hu, spacing)


def _heavy_segment(volume, task, roi_subset):
    """Designed seam for TotalSegmentator/SynthSeg — not implemented in the classical
    ship (never reached, since _heavy_available() is False). Left explicit so the
    integration points (temp NIfTI, --fast/--ml/--roi_subset/--statistics, categorical
    mask PNG) are documented for the follow-up."""
    raise NotImplementedError("heavy segmentation provider is not installed in this build")
