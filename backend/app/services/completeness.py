"""Completeness / consistency checker — "detect missing findings".

Flags (never auto-edits): AI-flagged pathologies the clinician neither confirmed
nor addressed in free text (discordance), near-threshold findings worth a look
(borderline), and empty/unattested sections. The clinician reviews these; the
tool only surfaces them.
"""

from .. import config
from ..models.schemas import CompletenessItem, ReportRequest
from . import label_map

BORDERLINE_LOW = 0.40


def check(req: ReportRequest) -> list[CompletenessItem]:
    items: list[CompletenessItem] = []
    s = req.structured
    struct = s.model_dump()

    # (a) Discordance: AI flagged it, clinician neither confirmed nor mentioned it.
    for f in req.vision_findings:
        if not f.flagged:
            continue
        key = label_map.key_for_label(f.label)
        if not key:
            continue
        confirmed = bool(struct.get(key))
        mentioned = label_map.mentioned_in_text(key, s.free_text)
        if not confirmed and not mentioned:
            items.append(CompletenessItem(
                severity="warn",
                category="discordance",
                label=f.label,
                message=(f"AI flagged {label_map.KEY_DISPLAY.get(key, f.label)} "
                         f"({f.probability:.0%} model confidence) — not confirmed or "
                         f"addressed in your findings. Confirm or explicitly dismiss it."),
            ))

    # (b) Borderline: below the flag threshold but not negligible.
    seen_keys = set()
    for f in req.vision_findings:
        if f.flagged:
            continue
        if BORDERLINE_LOW <= f.probability < config.FINDING_THRESHOLD:
            key = label_map.key_for_label(f.label) or f.label
            if key in seen_keys:
                continue
            seen_keys.add(key)
            items.append(CompletenessItem(
                severity="info",
                category="borderline",
                label=f.label,
                message=(f"{f.label} is near the flag threshold "
                         f"({f.probability:.0%}) — consider reviewing."),
            ))

    # (c) Empty / unattested sections.
    if not req.clinical_history.strip():
        items.append(CompletenessItem(
            severity="info", category="empty-section", label="Clinical history",
            message="No clinical history/indication provided.",
        ))

    any_positive = any(struct.get(k) for k in (
        "nodule_present", "pleural_effusion", "pneumothorax",
        "consolidation", "cardiomegaly", "rib_fracture"))
    if not any_positive and not s.reviewed_no_acute:
        items.append(CompletenessItem(
            severity="warn", category="empty-section", label="Attestation",
            message=("No findings confirmed and 'reviewed — no acute abnormality' is "
                     "not attested. Mark it to record that the study was reviewed."),
        ))

    # Laterality prompts for side-specific findings.
    if s.pleural_effusion and not s.effusion_side:
        items.append(CompletenessItem(
            severity="warn", category="empty-section", label="Effusion side",
            message="Pleural effusion confirmed but no side specified (wrong-side risk).",
        ))
    if s.pneumothorax and not s.pneumothorax_side:
        items.append(CompletenessItem(
            severity="warn", category="empty-section", label="Pneumothorax side",
            message="Pneumothorax confirmed but no side specified (wrong-side risk).",
        ))

    return items
