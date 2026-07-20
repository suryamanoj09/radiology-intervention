"""Label-contract regression guard.

Two failure modes this catches:
  1. Someone edits label_map so a vision label maps to a structured key that no
     longer exists on StructuredFindings (silent prefill / template drift).
  2. TorchXRayVision renames a pathology out from under LABEL_TO_KEY, so the map
     silently stops matching (the model live-check below).
"""

import pytest

from app.models.schemas import StructuredFindings
from app.services import label_map

# Canonical densenet121-res224-all label set, frozen here so a torchxrayvision
# rename OR an accidental LABEL_TO_KEY edit is caught even without torch installed.
# Keep in sync intentionally: changing this is a conscious contract change.
XRV_ALL_PATHOLOGIES = {
    "Atelectasis", "Consolidation", "Infiltration", "Pneumothorax", "Edema",
    "Emphysema", "Fibrosis", "Effusion", "Pneumonia", "Pleural_Thickening",
    "Cardiomegaly", "Nodule", "Mass", "Hernia", "Lung Lesion", "Fracture",
    "Lung Opacity", "Enlarged Cardiomediastinum",
}


def test_every_mapped_key_is_a_real_structured_field():
    fields = set(StructuredFindings.model_fields)
    for label, key in label_map.LABEL_TO_KEY.items():
        assert key in fields, f"LABEL_TO_KEY[{label!r}] -> {key!r} is not a StructuredFindings field"


def test_key_display_covers_every_mapped_key():
    for label, key in label_map.LABEL_TO_KEY.items():
        assert key in label_map.KEY_DISPLAY, f"KEY_DISPLAY missing {key!r} (for label {label!r})"


def test_key_synonyms_cover_every_mapped_key():
    for key in set(label_map.LABEL_TO_KEY.values()):
        assert key in label_map.KEY_SYNONYMS, f"KEY_SYNONYMS missing {key!r}"


def test_mapped_labels_are_known_xrv_pathologies_frozen():
    # Offline guard (no torch): every source label must be a real xrv pathology.
    for label in label_map.LABEL_TO_KEY:
        assert label in XRV_ALL_PATHOLOGIES, (
            f"{label!r} is not in the frozen TorchXRayVision label set — "
            f"a label rename or typo in LABEL_TO_KEY."
        )


def test_mapped_labels_match_live_torchxrayvision_pathologies():
    # Live guard: if torchxrayvision is importable, assert the map still lines up
    # with the actual model vocabulary. Skips (never fails) when torch is absent,
    # and reads only the module-level constant — no weights are downloaded.
    xrv = pytest.importorskip("torchxrayvision")
    live = set(xrv.datasets.default_pathologies)
    for label in label_map.LABEL_TO_KEY:
        assert label in live, (
            f"{label!r} is no longer a TorchXRayVision pathology "
            f"(default_pathologies renamed?). Update LABEL_TO_KEY."
        )
    # And keep the frozen offline list honest against the live one.
    assert XRV_ALL_PATHOLOGIES.issubset(live), (
        "Frozen XRV_ALL_PATHOLOGIES has drifted from torchxrayvision.default_pathologies."
    )
