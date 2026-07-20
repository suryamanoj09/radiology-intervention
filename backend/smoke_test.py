"""End-to-end smoke test without HTTP: vision pipeline + report generator.

Run:  .venv\\Scripts\\python smoke_test.py
Exercises the Phase-0 trust-chain behaviours (opt-in confirmed findings,
deterministic differentials, triage recompute, completeness/discordance).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

from app.models.schemas import ReportRequest, StructuredFindings
from app.services import completeness, llm, templates, triage, vision_xray

SAMPLES = Path(__file__).parent.parent / "samples"
_fail = []


def check(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        _fail.append(msg)


def main():
    print("=== 1. Template report from CONFIRMED findings ===")
    req = ReportRequest(
        clinical_history="62M, smoker, chronic cough",
        structured=StructuredFindings(
            nodule_present=True, nodule_size_mm=8, nodule_location="RUL",
            pleural_effusion=True, effusion_side="right",
        ),
    )
    rep = templates.build_report(req)
    check(rep.generator == "template", "generator is template with no key")
    check("For physician review only" in rep.differentials, "differentials carry the safety line")
    check("Discuss these results with your doctor" in rep.patient, "patient summary closing line present")
    check("8 mm (clinician-measured)" in rep.clinical, "nodule size labeled clinician-measured")
    check("right-sided pleural effusion" in rep.clinical.lower(), "effusion laterality rendered")

    print("=== 2. Vision analysis on sample CXR (Grad-CAM on logits) ===")
    sample = next(SAMPLES.glob("*.png"), None) or next(SAMPLES.glob("*.jpg"), None)
    if not sample:
        print("  (no sample image; skipping vision)")
    else:
        img = np.array(Image.open(sample).convert("L"), dtype=np.uint8)
        result = vision_xray.analyze_xray(img, None, "CR", "image")
        check(0.0 <= result.findings[0].probability <= 1.0, "confidence is a raw probability in [0,1]")
        check(all(f.size_mm is None for f in result.findings), "no fabricated size_mm from the model")
        top = next((f for f in result.findings if f.flagged), None)
        if top:
            check(result.heatmap_url is not None, "heatmap produced for a flagged finding")

        print("=== 3. Discordance: AI flag not confirmed by clinician ===")
        # Force a pneumothorax flag and leave the form empty -> discordance + urgent recompute.
        vf = result.findings
        for f in vf:
            if f.label == "Pneumothorax":
                f.probability = 0.9
                f.flagged = True
        req2 = ReportRequest(structured=StructuredFindings(reviewed_no_acute=True), vision_findings=vf)
        items = completeness.check(req2)
        has_ptx_discord = any(i.category == "discordance" and "pneumothorax" in i.message.lower()
                              for i in items)
        check(has_ptx_discord, "completeness flags unconfirmed AI pneumothorax")
        m_level, _ = triage.assess(vf)
        check(m_level == "urgent", "model triage escalates on pneumothorax")

        print("=== 4. Triage recompute on human-confirmed pneumothorax ===")
        req3 = ReportRequest(structured=StructuredFindings(pneumothorax=True, pneumothorax_side="left"))
        rep3 = templates.build_report(req3)
        check(rep3.triage == "urgent", "confirmed pneumothorax forces urgent triage")

    print()
    if _fail:
        print(f"SMOKE TEST FAILED ({len(_fail)} checks): " + "; ".join(_fail))
        sys.exit(1)
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
