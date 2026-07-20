# RadAssist — Accuracy & Safety: The Honest Bottom Line

**Prepared by the RadAssist ACCURACY + SAFETY research team.** Read-only synthesis of the five
research reports under `docs/research/` (01_accuracy, 02_calibration, 03_abstain_safety,
04_ctmri_safety, 05_fda_readiness), the two inventories (`inv_backend.md`, `inv_safety.md`), and the
ground-truth measured behavior card `backend/validation/behavior_card.json`
(== `backend/behavior_card.json`, byte-identical), served at `GET /api/behavior-card` and produced by
`backend/validation/run_validation.py` on a **300-image NIH ChestX-ray14 sample**.

> **Status: research/portfolio prototype. NOT an FDA-cleared or FDA-registered medical device.**
> Every finding is a "signal for review, not a diagnosis." Numbers tagged **[MEASURED]** are read from
> the behavior card or derived arithmetically from its fields; items tagged **[RECOMMENDATION]** are
> ours. No metric is invented. Where the data to answer a question does not exist, we say so.

This document answers the two questions the user actually asked:

- **(A) Is the disease-detection accuracy accurate?** — per-modality, per-pathology verdict.
- **(B) Even when it cannot identify disease, does it avoid giving an incorrect diagnosis?** — the
  current guarantees, the ranked concrete gaps, and the prioritized fixes (with the #1 fix that WF5
  must implement).

---

## PART A — Is the disease-detection accuracy accurate?

### A.0 One-paragraph verdict

**Partially, and honestly labeled as such — but NOT uniformly, and for most pathologies the accuracy
is not even reliably *measured*.** On chest X-ray (the only modality with any measured accuracy),
*discrimination* (AUROC) is moderate-to-good but trustworthy for only **4 of 14** pathologies — the
ones with ≥ 20 positive cases in the sample. The *flag stream the clinician actually sees* is a
different and worse story: at the shipped raw-0.5 threshold roughly **9 of every 10 flags are false
positives** on the model's own in-distribution test data. And there is **no measured accuracy for CT
or MRI at all** — those numbers do not exist and would be fabricated if quoted. Accuracy of *ranking*
is not the same as accuracy of the *flags*, and neither has been tested outside the training
distribution.

### A.1 Chest X-ray — per-pathology verdict (reliable / weak / unmeasured)

Ground truth: `behavior_card.json` `detection[]`. Reliability rule is the harness's own
(`run_validation.py:118-119`): a metric is `reliable` only when **positives ≥ 20**. `PPV@0.5` is
derived at test-set prevalence (TP = sens·P, FP = (1−spec)·N); real-clinic PPV is lower still.

| Pathology | pos | AUROC | Sens@0.5 | Spec@0.5 | PPV@0.5 | **Verdict** |
|---|---|---|---|---|---|---|
| **Effusion** | 31 | 0.839 | 0.774 | 0.799 | 0.307 | **RELIABLE** — best overall; even so ~2 of 3 effusion flags are false |
| **Atelectasis** | 22 | 0.783 | 0.864 | 0.637 | 0.159 | **RELIABLE** — moderate AUROC, poor precision |
| **Consolidation** | 20 | 0.767 | 0.750 | 0.657 | 0.135 | **RELIABLE** (just barely) — moderate |
| **Infiltration** | 44 | 0.732 | 0.909 | 0.355 | 0.195 | **RELIABLE (n)** — weak discrimination, near-useless specificity (flags almost everything) |
| Mass | 18 | 0.799 | 0.944 | 0.422 | 0.094 | WEAK (n<20) — good AUROC point est., 1-in-11 flag precision |
| Cardiomegaly | 16 | 0.906 | 0.625 | 0.880 | 0.227 | WEAK (n<20) — highest AUROC but on 16 pos; misses 3/8 |
| Pleural_Thickening | 12 | 0.688 | 0.750 | 0.590 | 0.071 | WEAK — AUROC below the 0.70 floor, kept because unreliable |
| Emphysema | 11 | 0.755 | 0.818 | 0.471 | 0.056 | WEAK |
| Fibrosis | 10 | 0.734 | 0.900 | 0.221 | 0.038 | WEAK — spec 0.22 ⇒ flags nearly everything |
| **Pneumothorax** | 9 | 0.828 | 0.778 | 0.619 | 0.059 | **NOISE (n=9)** — a true emergency label, only 9 positives; no usable sensitivity estimate |
| Nodule | 7 | 0.626 | 0.714 | 0.382 | 0.027 | **NOISE** — near-chance AUROC, 1-in-37 flag precision |
| Edema | 5 | 0.766 | 0.200 | 0.919 | 0.040 | **NOISE** — sens 0.2 (misses 4 of 5) |
| **Pneumonia** | 2 | **0.458** | **0.000** | 0.862 | **0.000** | **NOISE / below chance** — catches 0 of 2; a 2-point "metric" |
| Hernia | 0 | null | — | — | — | **UNMEASURED** — 0 positives, correctly null |

**Reading of the table:**

- **Reliable four (Effusion, Atelectasis, Consolidation, Infiltration).** Genuine but coarse.
  Even the best-sampled label (Effusion, 31 pos) has a Hanley-McNeil 95% CI of roughly **[0.75, 0.93]**
  on its 0.839 AUROC. Treat these four as load-bearing at **±~0.09**; the card exposes no CIs. **[MEASURED / derived]**
- **Weak / noise (10 labels).** Single points on 0–18 positives. For the 9–18-positive group the 95%
  CI half-width is ≈0.10–0.16, so point estimates like Cardiomegaly 0.906 and Mass 0.799 are **not
  statistically distinguishable from ~0.75.** Directional at best. **[MEASURED / derived]**
- **The two most safety-critical labels are the worst-sampled.** Pneumothorax (9 pos) and Pneumonia
  (2 pos). No usable sensitivity estimate exists for either. Pneumonia "sens 0.0" is 0 of 2 — it
  carries almost no information yet reads as a damning number. **[MEASURED]**
- **Subgroup shift is real.** PA micro-AUROC **0.807** (185 img) vs AP **0.784** (115 img) — an
  expected PA-upright vs AP/portable-supine acquisition gap. Both are micro-averages that hide
  per-label collapse. No site/scanner/sex/age strata exist. **[MEASURED]**

### A.2 The core accuracy finding: the flag stream is ~90% false positives

The flag decision is **`p_raw >= 0.5`** (`vision_xray.py:667`, `config.py:46`), with per-label
overrides only for Effusion (0.5342) and Infiltration (0.5252). **Calibration is display-only and
never gates the flag** (`vision_xray.py:662-667`).

Two independent routes through the card agree **[MEASURED / derived]**:

- **Route A (per-label PPV):** aggregate over the 13 measured labels at t=0.5 → ~165 true-positive
  flags vs ~1,467 false-positive flags across 300 images × 13 labels.
- **Route B (calibration reliability table):** label-instances scoring ≥ 0.5 = 1480+111+33+11+2 =
  **1,637 of 4,200 (39.0%)**; true positives among them ≈ Σ(obs·count) ≈ **165**.

> **At the shipped 0.5 threshold, ~39% of all label-instances are flagged and ~9 of every 10 flags
> are false positives — on the model's own in-distribution test data** (≈165 / 1,637 ≈ 10% flag
> precision, ~4.9 false flags per image before any clinical-prevalence penalty).

**Why:** the single band **[0.5, 0.6)** holds **1,480 instances (35% of everything) at mean
confidence 0.523 but only 8.2% observed positive**. The operating point sits inside the largest,
worst-calibrated pile of scores, and this one band is **64% of the overall ECE 0.2437**. The score
distribution is bimodal (68% of all mass in just the 0.0–0.1 and 0.5–0.6 bins) — an artifact of
`op_norm` banding, which piles scores onto the operating point. **[MEASURED]**

**Threshold instability.** Sensitivity collapses between t=0.50 and t=0.55 for most labels
(Pneumothorax 0.778→0.0, Emphysema 0.818→0.0, Infiltration 0.909→0.386, Fibrosis 0.9→0.2). The 0.5
operating point sits on the steepest part of the distribution — the least stable place to put it. A
0.05 threshold move swings sensitivity from "catches most" to "catches none." **[MEASURED]**

### A.3 Calibration — honest architecture, poor numbers

- **Overall ECE = 0.2437** over 4,200 label-instances; **every bin is over-confident** (obs < conf in
  all 10 bins). **[MEASURED]**
- The code separation is genuinely good: flag uses raw score; `calibrated_probability` and the triage
  banner (fires only on calibrated P ≥ 0.30, `triage.py:39`) use the isotonic map, so an over-confident
  raw 0.54 (calibrated ~0.08) **cannot** manufacture a red banner. **[MEASURED]**
- **But two defects remain:**
  1. **Low per-class ECE is a trap.** Hernia (0.044) and Pneumonia (0.122) look "well-calibrated"
     only because they almost never fire — Pneumonia has sens 0.0. **Never show a per-class ECE
     without its positives count.** **[MEASURED]**
  2. **Isotonic tails pinned to 1.0 on 1–3 samples.** For **Pneumothorax**, `calibrate()` returns
     **exactly 1.0** for any raw score ≥ 0.55 (`calibration.py:82-83`), fitted on bins with count 0.
     A single high-scoring **negative** is remapped to P = 100% and can **manufacture a false urgent
     pneumothorax banner** through triage. The raw-score flag is unaffected (good), but the number
     driving triage is not defensible. **[MEASURED]**
  3. **Calibration-map provenance defect.** `calibration_map.json` ships isotonic maps for labels with
     5–11 positives (Nodule 7, Edema 5, Pneumothorax 9, …) that the *current* harness guard
     (`run_validation.py:223`, `size < 40 or pos < 12`) would exclude — the shipped map was produced by
     an older, looser generator and is inconsistent with the current card. **[MEASURED]** →
     regenerate it or mark those labels `insufficient_data`.

### A.4 Localization (Grad-CAM) — separately weak, separately under-powered

`behavior_card.json` `localization`, 51 boxes total, 3–11 per class: hit-rate **0.0 / IoU 0.0 for
Atelectasis and Pneumonia**, Pneumothorax 0.167 / IoU 0.008, best Cardiomegaly 0.6 / IoU 0.129 on 10
boxes. **[MEASURED]** Grad-CAM here is a region-of-attention sanity check, not evidence the flag is
spatially correct, and it is honestly captioned as such.

### A.5 CT / MRI — no measured accuracy exists

**There is NO measured accuracy for CT or MRI. It does not exist.** The behavior card is 100% chest
X-ray. The CT/MRI research CADe detectors (`ct_cade.py`, `mr_cade.py`) are **classical, deterministic
(numpy/scipy), and never characterized against ground truth.** Any AUROC/ECE/sensitivity for CT/MRI
would be fabricated. Every candidate is structurally `validated=False` / `research_only=True` with a
mandatory disclaimer, default OFF. **[MEASURED]** This is honest by construction, but it means the CT/MRI
accuracy verdict is simply **UNMEASURED — no diagnostic claim is possible.**

### A.6 Part A bottom line

- **Is the accuracy accurate?** *Discrimination:* moderately, and only for the 4 CXR labels with ≥ 20
  positives (AUROC 0.73–0.84, ±~0.09). *Flags:* no — the review list is ~90% false positives at the
  shipped threshold. *The other 10 CXR labels:* not reliably measured; the 2 critical ones (Pneumonia,
  Pneumothorax) are essentially unmeasured. *CT/MRI:* no measured accuracy exists at all.
- **Is it reliable?** Only as a high-sensitivity, low-precision **review prompt** — which matches the
  product's "signal for review, not a diagnosis" framing. **That framing is doing the safety work, not
  the numbers.**
- All numbers are in-distribution (NIH relatives of the training data) and optimistic. The card is an
  honest engineering sanity check, correctly captioned; it is not a clinical accuracy measurement.

---

## PART B — Even when it cannot identify disease, does it avoid an incorrect diagnosis?

### B.0 Verdict on the negative claim

The claim *"even when the model cannot identify disease, it never emits an incorrect diagnosis"* is:

- **On the CT/MRI channels: STRUCTURALLY UPHELD.** No diagnosis, no calibrated probability,
  `validated=False` triple-enforced (`models/detect.py:34,58` + `routers/detect.py:104,113`),
  `research_only=True` with no env override (`config.py:595`), a **required** disclaimer field with no
  default (`models/detect.py:70`), a model-free viewer, default-OFF fail-closed AI, and — critically —
  an explicit *"No candidate regions above threshold. This is NOT a 'normal' result…"* on empty results
  (`CandidateFindings.jsx:126`). On this path the guarantee holds. **[MEASURED]**

- **On the chest X-ray channel: REFUTED as an absolute, UNPROVEN as a bounded claim.** The system
  presents an **implied-normal** (green "Routine / No findings flagged") on films with *measured* missed
  disease, and can score non-chest grayscale radiographs as chest films. The abstain gate has **zero
  measured operating characteristics** — the behavior card has no abstain/OOD section, so its two-sided
  specificity is asserted, not measured. **[MEASURED]**

The defensible, provable version of the claim is narrower: *"the tool makes no explicit normal
assertion, abstains on inputs it can detect as OOD at a measured operating point, and publishes the NPV
of its no-flag state."* None of the four supporting pieces (measured abstain ROC, published no-flag NPV,
explicit result-time non-normal banner, closed OT/PNG/grayscale routing holes) exists on the CXR path
today.

### B.1 What currently protects against a confident wrong answer (the guarantees that hold)

These are real and defense-in-depth **[MEASURED from source]**:

1. **Score/flag/calibration separation.** Flag uses raw score only; calibration can never silently move
   a flag; triage fires only on calibrated P ≥ 0.30 — an over-confident raw score cannot raise a red
   banner (`vision_xray.py:667`, `triage.py:39`).
2. **Modality routing (hard 422).** Non-CXR DICOM is rejected before the model runs (`analyze.py:38`).
3. **Self-audit OOD/abstain gate.** Color, synthetic/flat-structure, and AE-reconstruction signals force
   ABSTAIN on color photos, screenshots, and synthetic/test patterns (`self_audit.py`), returning zero
   findings and no heatmaps.
4. **Per-finding suppression.** Background gate and anatomy-plausibility gate remove flags whose
   attention lands on non-anatomy or implausible structures; marker inpainting defends against
   shortcut-learning (Zech/DeGrave).
5. **Honest UI copy where it exists,** and the AUROC-reliability-guarded denial that avoids hiding a
   label on a 2-positive fluke.
6. **CT/MRI walls** (B.0) — the strongest part of the whole system.

### B.2 The ranked concrete gaps where an incorrect / over-confident read can still occur

Ranked by risk. All grounded in MEASURED card numbers or cited code.

1. **[#1 — HIGHEST] "No flag" is silently read as "normal" (incorrect-diagnosis-by-omission).**
   A zero-flag CXR renders **no** competence banner (`CompetenceBanner.jsx:3` returns null on `read`),
   **no** triage banner (`TriageBanner.jsx:7` returns null on `routine`), a collapsed `<details>`
   "what was not checked" (`WhatNotChecked.jsx:15`), and a **green "Routine / No findings flagged"**
   worklist row (`Dashboard.jsx:31-51`). Yet the card proves the no-flag bucket carries real missed
   disease at t=0.5: **Pneumonia 2/2 missed (sens 0.0), Edema 4/5 missed (sens 0.2), Cardiomegaly 6/16
   missed (sens 0.625), 2 of 9 pneumothoraces missed.** The identical *"This is NOT a normal result"*
   warning already exists on the CT CADe panel but **not** on the CXR path. This is the single largest
   way an incorrect clinical impression reaches the user. **[MEASURED]**

2. **Grayscale non-chest radiograph (knee/hand/abdomen/spine) scored as a chest film.** For a smooth
   grayscale bone film the color signal is 0, structure signal is low, and the AE — by its own author's
   comment (`config.py:386-389`) — cannot reach the 0.9 reliable-abstain bar. **No reliable signal fires;
   the gate cannot abstain it.** If uploaded as PNG/JPG it also bypasses modality routing (no tag).
   Yields confident chest-pathology flags on a non-chest bone. **[MEASURED code behavior]**

3. **`OT`/secondary-capture and PNG/JPG routing bypass.** `CXR_MODALITIES` includes `"OT"`
   (`config.py:371`), so a DICOM tagged Other is accepted and scored; PNG/JPG carry no modality tag and
   fall straight through the hard-422. **[MEASURED]**

4. **Over-confident false-positive flags near the raw-0.5 threshold.** The 0.5–0.6 band is 8.2%
   positive → most borderline flags are false positives surfaced as "Flagged for review"; the
   "borderline" disposition softens but still presents a positive. **[MEASURED]** (This is the Part-A
   ~90%-false-positive finding, viewed as a safety risk.)

5. **Isotonic tail can manufacture a false *urgent* pneumothorax banner.** Pneumothorax calibrated P
   snaps to exactly 1.0 for raw ≥ 0.55 on zero-support bins, and triage escalates at P ≥ 0.30
   (`calibration.py:82-83`, `triage.py:42-45`). A high-scoring negative → red urgent banner. **[MEASURED]**

6. **Weak-but-shown labels over-trusted.** Below-chance Pneumonia (AUROC 0.458, sens 0.0) and Nodule
   (0.626) are kept-with-caution, not hidden — the AUROC auto-denial suppresses **nothing today** because
   no sub-0.70 label is `reliable` (`vision_xray.py:336-357`). A hurried reader may act on a near-chance
   flag. **[MEASURED]**

7. **Anatomy `suppress` gate can delete a true finding.** A model gating a model, defaulting to delete;
   PSPNet mis-segmentation removes a true flag (a safety-layer-induced false negative). Its FN/FP cost is
   **not in the behavior card** — unmeasured. It also only runs on findings that get localized (capped,
   priority-first), so a flagged-but-not-localized finding surfaces with no plausibility check.

8. **Calibration is in-distribution; triage trusts calibrated P.** The AP/PA AUROC gap (0.784 vs 0.807)
   is already visible; off-site/scanner/supine shift miscalibrates P and the triage banner inherits the
   error. No subgroup calibration data exists. **[MEASURED gap]**

9. **Lateral / rotated / inverted / pediatric PNG scored as frontal.** Lateral down-weight needs a DICOM
   `ViewPosition` tag (`analyze.py:60-65`); a lateral PNG is scored as frontal. No rotation/inversion/
   pediatric detector exists.

10. **Silent AE degradation.** If the autoencoder fails to load (likely on the CPU/HF-Space host), the
    gate silently drops to color+structure only, widening gap #2, with no user-visible notice.

11. **CT/MRI residual (framing, not diagnosis leaks):** the "not normal" guarantee lives only in a
    frontend string, not the API contract; detector score is rendered as a `%` next to a disease-shaped
    label; MR has **no** competence/abstain gate (`detect.py:75` hard-codes `("read", [])` for non-CT);
    the CT abstain gate is a hand-set unmeasured threshold. None emit a diagnosis today, but each could
    let a CT/MR output be misread — and WF7 (CT/MRI report) is the highest future leak surface.

12. **LLM report template defaults to per-region normal prose** even when nothing was confirmed
    (`templates.py:110-126`) — clinician-gated, so lowest rank, but it launders template defaults into
    normal-sounding text.

### B.3 The prioritized fix list (feed these into the implementation phases)

Ordered by safety impact. **Fix #1 is the north-star product change WF5 must implement.**

1. **[#1 — WF5 MUST IMPLEMENT] Explicit "NOT a normal read" disposition + NPV of the no-flag state.**
   Add a first-class, result-time banner on **every zero-flag CXR**, mirroring the CADe panel:
   *"This is NOT a normal read — the tool checks a fixed set of findings and can miss real disease;
   absence of a flag is not a normal result."* Promote `WhatNotChecked` out of the collapsed `<details>`.
   Recolor the Dashboard "No findings flagged" row away from green/`--success-tint` to a neutral
   "Not a normal read" state. **Publish the measured NPV of the no-flag state** at realistic clinical
   prevalence (per-label and study-level) into the behavior card and surface it beside the banner —
   computed on a held-out enriched set, **never invented.** This converts a silent implied-normal into
   an explicit non-claim; the safety guarantee becomes "the device does not *assert* normal," backed by
   the NPV number and the absence of any normal assertion.

2. **Set the flag threshold from calibrated P at a chosen per-label operating point, not raw 0.5.**
   Because `calibrate` is monotone, a P-threshold ≡ a score-threshold. Select each label's threshold
   from its ROC curve: sensitivity-first on critical labels (Pneumothorax → 0.35: sens 1.00, spec 0.557,
   unifying with `PNEUMOTHORAX_ALERT_THRESHOLD`), Youden-J on well-separated ones (Cardiomegaly ≈ 0.10–0.20),
   and **demote poorly-separated labels (Infiltration, Fibrosis, Nodule, Mass) to advisory** rather than
   raising the bar into the 0.55 cliff. Publish per-label (threshold, sens, spec, PPV@prevalence) and
   report alert-burden (flags per normal film). This directly attacks the ~90%-false-positive stream.

3. **Abstain-per-label for unmeasurable critical labels.** For Pneumonia and Pneumothorax, when
   positives are too few to measure, treat "unmeasurable" as **abstain / insufficient-evidence on that
   label** (an explicit non-claim), not "surface with caution." A detector below a coin flip on the only
   2 positives it saw should not be shown as a finding.

4. **Fix the isotonic tails feeding triage.** Require minimum bin support (e.g. ≥ 10 instances) before a
   knot may reach an extreme; **clamp the calibrated P used by triage to ≤ 0.90**; prefer Platt/beta on
   sparse labels. No 0.05 raw step should swing calibrated P from 0.03 to 1.00. Closes gap B.2#5.

5. **Close the routing / OOD holes.** Drop `"OT"` from `CXR_MODALITIES` (or route it to a confirm step);
   add a grayscale-non-chest / anatomy-presence check so PNG bone films abstain; detect and warn on
   inversion/rotation/lateral for tag-less PNGs; surface AE-unavailable degradation to the user. Closes
   gaps B.2#2, #3, #9, #10.

6. **Measure the abstain gate as a first-class selective classifier.** Build a negative-control OOD set
   (non-chest radiographs incl. smooth grayscale bone films, CT/MR-as-PNG, photos, screenshots,
   synthetic patterns, inverted/rotated/lateral/pediatric — both DICOM and PNG-stripped). Report
   missed-OOD and over-abstain rates with CIs; add an `abstain` section to `behavior_card.json`; choose
   `OOD_ABSTAIN_THRESHOLD` from the measured risk–coverage curve (e.g. ≥ 0.99 catch on hard-OOD at ≤ 1%
   over-abstain), replacing every hand-set constant. Scaffold exists (`validation/risk_coverage.py`).

7. **Regenerate `calibration_map.json` from the current harness** so exclusions match; emit an
   `"excluded"` block so the UI can show `insufficient_data` vs `uncalibrated` honestly; lead the UI with
   calibrated P (or a verbal band) and de-emphasize the misleading raw score; show per-class ECE only
   with its positives count.

8. **Measure the anatomy/background suppression gates** (suppress-TP vs remove-FP tradeoff) and add their
   FN/FP to the behavior card before trusting `suppress` mode; consider `warn_only` as default until
   measured. Closes gap B.2#7.

9. **CT/MRI hardening:** move the "not normal" guarantee into the API contract (a machine-readable
   `absence_of_candidates_is_not_normal: true`); stop rendering detector score as a `%`; add an MR
   competence/abstain gate; and keep any future WF7 CT/MRI report strictly a summary of unvalidated
   candidates + measurements with server-side no-diagnosis guards.

### B.4 Part B bottom line

The system is genuinely strong where it has been engineered to be: the CT/MRI channels uphold the
negative claim structurally, and the CXR pipeline cleanly separates raw score from calibrated P and from
triage. The claim fails on the CXR path for two reasons that are both fixable: **(1) a silent
implied-normal on a zero-flag film with measured missed disease** — the #1 WF5 fix — and **(2) hand-set,
unmeasured gate thresholds** with no abstain ROC. Reaching even the defensible narrow version of the
claim requires the explicit non-normal banner + published NPV (fix #1), a measured abstain gate (fix #6),
and closing the OT/PNG/grayscale holes (fix #5). Until then, the honest statement is: *RadAssist reliably
withholds on the OOD inputs it can detect and never asserts a CT/MRI diagnosis, but it can still present a
missed in-distribution chest finding as an implied-normal, and its abstain guarantee is asserted, not
measured.*

---

*Synthesis by the RadAssist ACCURACY + SAFETY research team. Every MEASURED value traces to
`backend/validation/behavior_card.json` (== `backend/behavior_card.json`) and `run_validation.py`, or to
the cited source file/line. PPV, flag-rate, and aggregate-precision figures are arithmetic on card
fields and reproducible. This is not clinical validation and not regulatory advice.*
