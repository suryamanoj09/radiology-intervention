# Intended use

**RadAssist is a non-clinical demonstration and portfolio prototype of an AI radiology
decision-support workflow.** It analyzes de-identified or public chest X-ray images with a
pretrained model to surface candidate findings, a region of model attention, a rule-based
priority-review flag, and a draft three-part report (clinical, plain-language patient summary,
and reference differentials) that a licensed radiologist would review, correct, and approve
before it has any meaning.

It is intended for developers and technical reviewers evaluating the prototype. It is **NOT**
intended for the diagnosis, treatment, triage, or clinical management of any patient, **NOT**
for use with real or identifiable patient data, and has **not** been evaluated or cleared by
any regulatory authority.

All model outputs are draft signals only — "model confidence" and "region of model attention",
never a diagnosis. No output is a finalized or signed medical record. The in-app review
attestation ("I have reviewed and adopt these findings") is a **workflow acknowledgement to
gate the draft**, not a legal electronic signature — the tool has no identity, audit, or
records function.

## Why this framing matters

Device classification flows from intended use. On the basis of this non-clinical,
public/de-identified, no-real-patient intended use, RadAssist is **not a regulated medical
device today**. That safe harbor rests entirely on the intended use above:

- If the stated intended use were clinical, the same functions would be regulated — in the US
  as FDA Class II radiological CADe/CADx (the vision path) and CADt (the triage flag); in the
  EU under MDR 2017/745 Rule 11 as Class IIa or higher.
- The **differential** list is a fixed, human-curated set of textbook associations, never
  patient-specific model reasoning, precisely so the tool does not perform a diagnostic
  (CADx) function.
- The sanctioned future CT-brain intracranial-hemorrhage feature falls in one of the most
  heavily regulated AI-radiology categories. Its intended-use guardrails and its "experimental
  screening flag, not detection" framing must be locked before that build.

For any move toward real clinical use, this document, the disclaimers, and the whole
development process would need to be revisited under IEC 62304 (software lifecycle) and
ISO 14971 (risk management). This prototype deliberately stays on the demonstration side of
that line.
