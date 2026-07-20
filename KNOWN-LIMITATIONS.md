# Known limitations

Read this before demoing or evaluating RadAssist. These are design-time decisions and
honest boundaries, not bugs.

## Vision model

- **Research-grade, not FDA-cleared.** The chest X-ray model (TorchXRayVision DenseNet-121)
  was trained on public research datasets. Its probabilities are *signals for review*, not
  diagnoses, and real-world performance is lower than any benchmark number.
- **The heatmap is model attention, not a lesion boundary.** Grad-CAM shows where the model
  looked when scoring the top finding. It can be diffuse, off-target, or highlight anatomy
  (e.g., the heart for cardiomegaly) rather than a discrete lesion.
- **Size estimates are rough.** The "≈ mm" value is the longest side of a box drawn around
  the attention region — usable as a starting point only, and only when DICOM pixel spacing
  is present. PNG/JPG uploads have no physical scale; the caliper then reports pixels.
- **Probabilities cluster near the threshold.** The model is calibrated so 0.5 is its
  operating point; several findings hovering at 50–55% on a normal film is expected noise,
  which is why a human confirms every flag.
- **Chest X-ray only.** CT and MRI analysis are roadmap items. The CT-brain path (if enabled
  in your build) is a windowed viewer plus an experimental screening model — even less
  validated than the X-ray path.

## Report generation

- **The LLM formats; it does not diagnose.** All clinical content comes from the clinician's
  form entries and the vision model's flags. If the input is wrong, the report is wrong.
- **Template fallback is deliberately plain.** Without an API key the reports are
  deterministic and correct but less fluent than LLM-formatted ones.
- **Differentials are static associations** (finding → common causes), not patient-specific
  reasoning. They are labeled "for physician review only".

## Comparison & triage

- **Prior-study comparison compares model confidences,** not measured anatomy. "Worsened"
  means the model is more confident, which can be caused by positioning, exposure, or
  image quality — not necessarily disease progression.
- **Triage is a rule on model confidence** for a small set of critical labels. It orders a
  review queue; it is not an alerting or notification system and must not be relied on to
  catch emergencies.

## Data & privacy

- **No PHI handling.** There is no authentication, encryption at rest, audit logging, or
  DICOM de-identification. Use public or fully de-identified images only.
- Uploaded images and analysis JSON are stored unencrypted in `backend/storage/`.

## Engineering

- Voice dictation uses the browser's speech engine (Chrome/Edge); accuracy varies and
  medical vocabulary is frequently mis-transcribed — always proofread.
- Single-process server; no queue. Heavy concurrent use will serialize on the CPU model.
- Analyses persist as JSON on disk; there is no database or user management.
