"""T1: the display layer must never assert more (or less) than the model's label
set, and never SPECIALIZE a generic label (no fabricated 'Rib')."""
from app.services import label_map

# Contract: densenet121-res224-all pathologies (kept here so the test is torch-free;
# a startup check in vision_xray asserts the live model still matches this set).
MODEL_PATHOLOGIES = {
    "Atelectasis", "Consolidation", "Infiltration", "Pneumothorax", "Edema",
    "Emphysema", "Fibrosis", "Effusion", "Pneumonia", "Pleural_Thickening",
    "Cardiomegaly", "Nodule", "Mass", "Hernia", "Lung Lesion", "Fracture",
    "Lung Opacity", "Enlarged Cardiomediastinum",
}


def test_raw_display_covers_model_pathologies_exactly():
    assert set(label_map.RAW_DISPLAY.keys()) == MODEL_PATHOLOGIES


def test_raw_display_names_are_unique():
    vals = list(label_map.RAW_DISPLAY.values())
    assert len(vals) == len(set(vals)), "two raw labels share a display name (would duplicate cards)"


def test_no_display_name_fabricates_a_site():
    # 'Rib' is the canonical fabrication — the model's Fracture label has no site.
    assert all("rib" not in v.lower() for v in label_map.RAW_DISPLAY.values())
    assert label_map.raw_display("Fracture") == "Fracture (site unspecified)"


def test_structured_keys_are_a_subset_of_pathologies():
    assert set(label_map.LABEL_TO_KEY.keys()) <= MODEL_PATHOLOGIES


def test_denylisted_label_never_reaches_the_report():
    from app.models.schemas import Finding, ReportRequest, StructuredFindings
    from app.services import templates
    from app import config
    assert "Fracture" in config.LABEL_DENYLIST
    req = ReportRequest(structured=StructuredFindings(), vision_findings=[
        Finding(label="Fracture", probability=0.9, flagged=True),
        Finding(label="Effusion", probability=0.8, flagged=True)])
    clinical = templates.build_report(req).clinical.lower()
    assert "fracture" not in clinical
    assert "pleural effusion" in clinical or "effusion" in clinical


def test_denial_helper_flags_fracture():
    from app.services import vision_xray
    d = vision_xray._denial("Fracture")
    assert d is not None and "unreliable" in d[0]


def test_sub_floor_but_unreliable_auroc_does_not_hide_label(monkeypatch):
    # Pneumonia scored AUROC 0.46 on only ~2 positives (reliable=False). That is
    # statistical noise, not evidence the label is weak, so it must NOT be hidden
    # when we require a reliable measurement to deny.
    from app.services import vision_xray
    monkeypatch.setattr(vision_xray.config, "LABEL_MIN_AUROC_REQUIRE_RELIABLE", True)
    info = vision_xray._label_auroc().get("Pneumonia")
    if info and not info["reliable"] and info["auroc"] < vision_xray.config.LABEL_MIN_AUROC:
        assert vision_xray._denial("Pneumonia") is None, "noisy small-sample AUROC hid a label"


def test_sub_floor_unreliable_is_denied_when_reliability_not_required(monkeypatch):
    # Toggling the knob off restores the old behaviour: any sub-floor AUROC denies.
    from app.services import vision_xray
    monkeypatch.setattr(vision_xray.config, "LABEL_MIN_AUROC_REQUIRE_RELIABLE", False)
    info = vision_xray._label_auroc().get("Pneumonia")
    if info and info["auroc"] < vision_xray.config.LABEL_MIN_AUROC:
        d = vision_xray._denial("Pneumonia")
        assert d is not None and "below the" in d[0]
