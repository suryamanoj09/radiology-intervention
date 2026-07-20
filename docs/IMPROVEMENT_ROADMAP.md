# RadAssist — Improvement Roadmap & High-Level Design

*A prioritized design for taking RadAssist from a strong prototype toward a "real
software device" feel — while staying honest about what is validated vs research.*

---

## 0. Guiding principles (these govern every item below)

1. **The display never asserts more than the model does.** Every number is either
   *measured* (from our validation harness) or clearly marked *unvalidated / research*.
   We never invent accuracy figures.
2. **Human-in-the-loop, always.** AI drafts and flags; a licensed clinician confirms,
   corrects, signs. No AI output auto-populates a signed report.
3. **Two clearly-separated AI channels on CT/MRI:**
   - **Anatomy overlay** — labels/measures anatomy, *never* disease (taboo-free schema).
   - **Research CADe** — *candidate* disease regions, hard "RESEARCH, unvalidated, not a
     diagnosis, confirm with a radiologist" framing.
3. **Abstain over guess.** If the input isn't the right kind of image, refuse (the
   self-audit gate) rather than emit confident nonsense.

---

## 1. Where we are today (baseline)

| Area | State |
|---|---|
| Chest X-ray AI | Ensemble classifier + calibrated P + per-finding Grad-CAM, abstain gate, anatomy gate, marker-masking, triage, structured report. |
| CT/MRI anatomy overlay | Opt-in, default-off segmentation (organs/tissues + volumes), taboo-free, license-clean, classical + pluggable heavy seam. |
| CT research CADe | **New** — opt-in candidate detection (lung nodule, hyperdensity), abstain + RESEARCH disclaimer + confirm/dismiss feedback. |
| Self-audit gate | Refuses color / synthetic / non-CXR input before scoring. **Just hardened** against synthetic/flat images. |
| Feedback | Recorded to `feedback.jsonl` (PHI-free, TTL-exempt). **New**: `refit_from_feedback.py` turns dismisses into threshold updates. |
| Accuracy | Measured per-label AUROC/sens/spec in the behavior card (shown in the X-ray UI). |
| Safety | De-ID (PS3.15 subset), quarantine, audit log, rate limits, auth, idle logoff. |

---

## 2. Roadmap (prioritized)

### Phase A — Trust & honesty plumbing (highest leverage, low risk)
- **A1. Close the feedback loop (done — wire into ops).** `refit_from_feedback.py` proposes
  per-label threshold changes from confirm/dismiss. Next: a small admin view to review &
  apply proposals; extend the same idea to the CADe detectors' `DETECT_MIN_SCORE`.
- **A2. Measured accuracy everywhere.** Surface per-finding AUROC/sens/spec + n + "measured
  on N held-out images" on **every** finding (X-ray already does; add to CT CADe candidates
  once a labelled CT set exists — until then show "unvalidated, no measured accuracy").
- **A3. A per-study "AI provenance" panel.** Model names, versions, licenses, calibration
  map version, abstain outcome — one place, so the reviewer always knows what ran.

### Phase B — CT/MRI parity with X-ray (the user's core ask)
- **B1. More CT candidate detectors (classical, CPU-now):** pleural effusion (dependent
  fluid density), pneumothorax (large non-anatomical air), aortic calcification, gross
  mediastinal mass — each a transparent heuristic, research-framed.
- **B2. MRI candidate detection.** Intensity is arbitrary, so candidates are *relative*
  (e.g. focal FLAIR-bright regions vs the brain's own signal) — never absolute claims.
  Pair with the DWI/ADC rail for a restricted-diffusion *candidate* (not a stroke call).
- **B3. Overlay + candidate UX unification.** One "AI" rail on the viewer with the two
  channels as tabs (Anatomy / Candidates), shared legend, opacity, per-slice review.
- **B4. Heavy-model seam activation (optional GPU deploy).** Swap the classical detectors
  for TotalSegmentator lung-nodule/liver-lesion/cerebral-bleed weights behind the same
  flags; then A2 accuracy becomes meaningful.

### Phase C — "Real device" clinical tools
- **C1. Measurement suite:** persistent calipers, angle/Cobb, HU-ROI (mean/SD/area on the
  16-bit volume), all with unit + calibration provenance chips.
- **C2. Prior-study comparison** for CT/MRI (the X-ray compare pattern), with a real
  change-vs-noise floor.
- **C3. Structured reporting** per region (chest/abdomen/neuro/spine templates), reader
  authors the impression; measurements pre-fill; export CSV / DICOM-SR (highdicom).
- **C4. MPR / thick-slab** (the volume-pivot Phase-3) once the int16 volume is persisted.
- **C5. Worklist / study list, roles (radiologist vs referrer), sign-off audit trail.**

### Phase D — Scale & ops (only if this becomes more than a demo)
- Shared rate-limit/session store (multi-worker), background job queue, per-weight license
  re-audit on version bump, a real de-identification certification path, model monitoring
  (drift, abstain-rate, feedback dashboards).

---

## 3. UI / UX suggestions (concrete)

1. **Unify the disclaimer language & placement.** One persistent safety strip; per-feature
   banners only when that feature is ON. (Anatomy = amber "not disease"; CADe = red
   "research, unvalidated".) Color-code the *risk*, not the finding.
2. **Stage-centric viewer.** Big viewport, collapsible rails, keyboard-first navigation,
   hanging protocols per body part (already specced in the CT/MRI design docs).
3. **Review ergonomics.** A "candidate gallery" (done for CADe) + one-key confirm/dismiss;
   a running "N confirmed / N dismissed" tally that feeds the feedback loop visibly.
4. **Honest confidence UI.** Never a bare "%": always score **+** calibrated P **+** measured
   accuracy chip, or an explicit "not calibrated / unvalidated" state (X-ray already does).
5. **Accessibility & theming.** System/light/dark is in; add reduced-motion, focus rings,
   ARIA on the viewer controls, and colour-blind-safe overlay palettes.

---

## 4. On "accuracy" — the honest answer

Real devices publish **validated** accuracy from a clinical study. We can and do show
**measured** accuracy from our own validation harness (AUROC/sens/spec per label on
held-out images), always labelled with the sample size and "in-distribution / optimistic."
We will **not** display an accuracy number for the CT research detectors until they are
measured against a labelled CT set — until then the UI says "unvalidated, no measured
accuracy," which is the truthful state. Inventing a number would be the real flaw.

---

## 5. Suggested next step

Pick a lane and I'll build it:
- **Feedback-loop admin view** (A1) — see & apply threshold proposals from real dismisses.
- **More CT candidate detectors** (B1) — effusion / pneumothorax / calcification.
- **MRI candidate detection** (B2) — relative-signal candidates + DWI/ADC pairing.
- **Clinical measurement suite** (C1) — HU-ROI + calipers on the 16-bit volume.
- **UI overhaul** (Phase 3 UI) — stage-centric viewer + unified AI rail.
