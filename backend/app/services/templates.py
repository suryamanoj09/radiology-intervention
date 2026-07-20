"""Deterministic template report builder — the DEFAULT report path.

Produces the three sections from clinician-confirmed findings, with no API key
and no model-authored clinical reasoning. The differentials are a fixed,
human-curated association list (never model-generated) and are reused verbatim
by the LLM path too, so the LLM never authors a differential.

`finalize()` is the single assembler used by both this module and the LLM path:
it recomputes triage on the confirmed findings and attaches the completeness
check, so those safety behaviours can't diverge between paths.
"""

from .. import config
from ..models.schemas import ReportRequest, ReportResponse, StructuredFindings
from . import completeness, label_map, triage

DIFFERENTIALS_MAP = {
    "nodule": [
        "Granuloma (prior infection)",
        "Primary lung neoplasm",
        "Metastasis",
        "Hamartoma",
        "Intrapulmonary lymph node",
    ],
    "pleural_effusion": [
        "Congestive heart failure",
        "Parapneumonic effusion",
        "Malignant effusion",
        "Hypoalbuminemia",
    ],
    "pneumothorax": [
        "Spontaneous pneumothorax",
        "Traumatic pneumothorax",
        "Iatrogenic (post-procedure)",
    ],
    "consolidation": [
        "Community-acquired pneumonia",
        "Aspiration",
        "Pulmonary edema",
        "Atelectasis",
    ],
    "cardiomegaly": [
        "Dilated cardiomyopathy",
        "Pericardial effusion",
        "Multivalvular heart disease",
        "Technical factor (AP projection magnification)",
    ],
    "rib_fracture": [
        "Traumatic fracture",
        "Pathologic fracture (underlying lesion)",
        "Stress fracture (e.g., chronic cough)",
    ],
}

PATIENT_EXPLANATIONS = {
    "nodule": "a small spot was seen in your lung. Many lung spots are harmless scars "
              "from old infections, but your doctor may want follow-up imaging to be sure",
    "pleural_effusion": "there is some extra fluid in the space around your lung. This can "
                        "have many causes, and your doctor will look at it together with "
                        "your symptoms",
    "pneumothorax": "some air has leaked into the space around your lung, which can make "
                    "the lung less inflated than normal. Your care team will decide if it "
                    "needs treatment or just monitoring",
    "consolidation": "part of your lung looks denser than normal, which is often seen with "
                     "an infection such as pneumonia",
    "cardiomegaly": "the shadow of your heart looks larger than usual on this image. This "
                    "is a clue, not a diagnosis — sometimes it is just how the picture was "
                    "taken",
    "rib_fracture": "there may be a break in one of your ribs. Rib fractures usually heal "
                    "on their own, but pain control and follow-up matter",
}

NO_FINDINGS_PATIENT_CAVEAT = (
    "This does not mean your study is completely normal — only a limited set of "
    "conditions was checked, and your doctor interprets the full images."
)


def _active_keys(s: StructuredFindings) -> list[str]:
    keys = []
    if s.nodule_present:
        keys.append("nodule")
    if s.pleural_effusion:
        keys.append("pleural_effusion")
    if s.pneumothorax:
        keys.append("pneumothorax")
    if s.consolidation:
        keys.append("consolidation")
    if s.cardiomegaly:
        keys.append("cardiomegaly")
    if s.rib_fracture:
        keys.append("rib_fracture")
    return keys


def _clinical_section(req: ReportRequest) -> str:
    s = req.structured

    lungs = []
    if s.nodule_present:
        desc = "Pulmonary nodule"
        if s.nodule_size_mm:  # clinician-entered only
            desc += f" measuring approximately {s.nodule_size_mm:g} mm (clinician-measured)"
        if s.nodule_location:
            desc += f" in the {s.nodule_location}"
        lungs.append(desc + ".")
    if s.consolidation:
        loc = f" in the {s.consolidation_location}" if s.consolidation_location else ""
        lungs.append(f"Airspace opacity/consolidation is present{loc}.")
    if not lungs:
        lungs.append("No focal consolidation or discrete nodule identified.")

    pleura = []
    if s.pleural_effusion:
        side = f" {s.effusion_side}-sided" if s.effusion_side else ""
        pleura.append(f"There is a{side} pleural effusion.")
    if s.pneumothorax:
        side = f" {s.pneumothorax_side}-sided" if s.pneumothorax_side else ""
        pleura.append(f"There is a{side} pneumothorax.")
    if not pleura:
        pleura.append("No pleural effusion or pneumothorax.")

    heart = ("The cardiac silhouette is enlarged." if s.cardiomegaly
             else "The heart is normal in size and the mediastinal contours are unremarkable.")
    bones = ("Rib fracture identified." if s.rib_fracture
             else "No acute osseous abnormality.")

    # AI flags: UNCONFIRMED signals, ONE line per RAW model label (unique display
    # names => no duplicate lines), each showing the raw label + disposition. The
    # display name never adds specificity the model lacks ("Fracture (site
    # unspecified)", never "Rib fracture").
    # Defence in depth: re-apply the FULL analyze-time denial predicate (denylist
    # OR sub-AUROC), not just the denylist — a weak label smuggled in via
    # client-supplied vision_findings must not reach the report/PDF either.
    from . import vision_xray
    seen_labels = set()
    ai_lines = []
    for f in sorted((x for x in req.vision_findings if x.flagged),
                    key=lambda x: -x.probability):
        if f.label in seen_labels or vision_xray._denial(f.label):
            continue  # denied labels never reach the report
        seen_labels.add(f.label)
        # T2: never persist a bare raw % for an uncalibrated label — the frontend
        # suppresses it, so the report/PDF must too. Show the score only when the
        # label is calibrated; otherwise say so.
        if getattr(f, "calibration_state", "uncalibrated") == "calibrated":
            score_txt = f"model score {f.probability:.0%}"
        else:
            score_txt = "score not calibrated"
        ln = f"- {label_map.raw_display(f.label)} [{f.label}]: {score_txt}"
        if getattr(f, "disposition", None):
            ln += f" — {f.disposition}"
        ai_lines.append(ln)

    keys = _active_keys(s)
    impression = []
    for k in keys:
        if k == "nodule":
            # Fleischner criteria apply to CT-detected nodules, NOT radiographs;
            # a nodule seen on a chest X-ray is characterized with CT, not a
            # radiograph follow-up interval.
            imp = "Pulmonary nodule as described."
            if s.nodule_size_mm:
                imp += (" Recommend correlation and characterization with chest CT; "
                        "CT-based follow-up (e.g. Fleischner) is determined after CT, "
                        "not from the radiograph.")
            impression.append(imp)
        else:
            impression.append({
                "pleural_effusion": "Pleural effusion.",
                "pneumothorax": "Pneumothorax — clinical correlation for management urgency.",
                "consolidation": "Airspace opacity, which may represent infection in the "
                                 "appropriate clinical setting.",
                "cardiomegaly": "Enlarged cardiac silhouette.",
                "rib_fracture": "Rib fracture.",
            }[k])
    if not impression:
        if s.reviewed_no_acute:
            impression.append("No acute cardiopulmonary abnormality identified.")
        else:
            impression.append("No findings confirmed by the reviewing clinician.")

    comparison = "No prior study available for comparison."
    if req.comparison and req.comparison.rows:
        comparison = (
            "Comparison with prior study"
            + (f" dated {req.comparison.prior_date}" if req.comparison.prior_date else "")
            + " (change in model confidence, not confirmed progression):\n"
            + req.comparison.rows_text()
        )

    parts = [
        f"TECHNIQUE: {req.modality}.",
        f"CLINICAL HISTORY: {req.clinical_history.strip() or 'Not provided.'}",
        f"COMPARISON: {comparison}",
        "FINDINGS:",
        f"  Lungs: {' '.join(lungs)}",
        f"  Pleura: {' '.join(pleura)}",
        f"  Heart and Mediastinum: {heart}",
        f"  Bones: {bones}",
    ]
    if s.free_text.strip():
        parts.append(f"  Additional clinician notes: {s.free_text.strip()}")
    if ai_lines:
        parts.append("  AI model flags (unconfirmed signals for review, NOT confirmed "
                     "findings):\n    " + "\n    ".join(ai_lines))
    parts.append("IMPRESSION:\n  "
                 + "\n  ".join(f"{i + 1}. {t}" for i, t in enumerate(impression)))
    parts.append("RECOMMENDATIONS: Clinical correlation. All AI-flagged regions require "
                 "radiologist confirmation.")
    return "\n\n".join(parts)


def _patient_section(req: ReportRequest) -> str:
    keys = _active_keys(req.structured)
    lines = ["Here is what your imaging study showed, in plain language:", ""]
    if keys:
        for k in keys:
            text = PATIENT_EXPLANATIONS[k]
            lines.append(f"• {text[0].upper() + text[1:]}.")
    else:
        lines.append("• No specific problems were confirmed on this study by the "
                     "reviewing clinician.")
        lines.append(f"• {NO_FINDINGS_PATIENT_CAVEAT}")
    if req.comparison and req.comparison.rows:
        lines.append("• Your images were also compared with an earlier study; your doctor "
                     "will explain what has changed or stayed the same.")
    lines.append("")
    lines.append("Discuss these results with your doctor, who knows your full medical history.")

    # WHAT HAPPENS NEXT — the single thing patients most want to know. Adapts to
    # whether the reviewing clinician confirmed any findings, and adds an urgent
    # safety-netting line when triage is urgent. 6th-grade, anxiety-aware, and
    # careful not to promise "nothing is wrong".
    model_level, _ = triage.assess(req.vision_findings)
    conf_level, _ = triage.assess_confirmed(req.structured)
    level = triage.combine(model_level, conf_level)

    lines.append("")
    lines.append("WHAT HAPPENS NEXT")
    if keys:
        lines.append("• Your doctor will look at these results together with how you feel "
                     "and your health history, and then talk them over with you.")
        lines.append("• A follow-up may be advised — for example another scan, a test, or a "
                     "visit to check on things. Being asked for a follow-up is a normal, "
                     "careful step; it does not mean something is certain.")
    else:
        lines.append("• Your doctor will still go over these results with you.")
        lines.append("• Because only a limited set of conditions was checked here, your doctor "
                     "may review the full images or ask about your symptoms before deciding "
                     "if any follow-up is needed.")
    lines.append("• It is okay to write down your questions and ask your doctor to explain "
                 "anything that is unclear.")
    # Severity-gated safety-netting: a scary term at 11 pm should never leave the
    # patient with no next step. Any priority/urgent finding auto-inserts contact
    # guidance, escalating to emergency wording only when a finding is urgent.
    if level == "urgent":
        lines.append("")
        lines.append("• IMPORTANT: one finding may need to be looked at soon. If you have "
                     "trouble breathing, chest pain, or you feel very unwell, get medical "
                     "help right away or go to the nearest emergency department — do not wait "
                     "for your next appointment.")
    elif level == "priority":
        lines.append("")
        lines.append("• Please contact your care team to go over these results soon — sooner "
                     "than a routine check-up. If you start to feel unwell, do not wait: seek "
                     "medical advice.")
    return "\n".join(lines)


def _differentials_section(req: ReportRequest) -> str:
    keys = _active_keys(req.structured)
    lines = ["For physician review only — not a diagnosis.", ""]
    if not keys:
        lines.append("No confirmed findings; no differentials suggested.")
        return "\n".join(lines).strip()
    for k in keys:
        title = k.replace("_", " ").title()
        lines.append(f"{title}:")
        lines.extend(f"  - {d}" for d in DIFFERENTIALS_MAP[k])
        lines.append("")
    return "\n".join(lines).strip()


def finalize(req: ReportRequest, clinical: str, patient: str,
             differentials: str, generator: str) -> ReportResponse:
    """Attach recomputed triage + completeness; single assembler for both paths."""
    model_level, model_reasons = triage.assess(req.vision_findings)
    conf_level, conf_reasons = triage.assess_confirmed(req.structured)
    level = triage.combine(model_level, conf_level)
    reasons = conf_reasons + model_reasons
    return ReportResponse(
        clinical=clinical,
        patient=patient,
        differentials=differentials,
        comparison_summary=req.comparison.rows_text() if req.comparison else None,
        triage=level,
        triage_reasons=reasons,
        completeness=completeness.check(req),
        generator=generator,
        disclaimer=config.DISCLAIMER,
    )


def build_report(req: ReportRequest) -> ReportResponse:
    return finalize(
        req,
        _clinical_section(req),
        _patient_section(req),
        _differentials_section(req),
        generator="template",
    )
