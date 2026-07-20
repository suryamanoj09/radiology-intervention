# 03 — Abstain / OOD Safety Audit: "Does RadAssist ever emit an incorrect diagnosis?"

Research team: ACCURACY + SAFETY. Scope: the abstain / out-of-distribution (OOD) /
"knows when to shut up" machinery, and the central negative claim —
**"even when the model cannot identify disease, it never emits an incorrect diagnosis."**

Method: read-only audit of `backend/app/services/self_audit.py`, `routers/analyze.py`,
`services/vision_xray.py` (`abstain_response`, `analyze_xray`), `services/triage.py`,
`services/templates.py`, `services/llm.py`, `config.py`, the React result surface
(`App.jsx`, `CompetenceBanner.jsx`, `TriageBanner.jsx`, `WhatNotChecked.jsx`,
`dashboard/Dashboard.jsx`), and the ground-truth `validation/behavior_card.json`.
Every metric below is quoted from that card (MEASURED) or labelled RECOMMENDATION.

**Bottom line up front.** The verdict on the negative claim is **REFUTED as an absolute
and UNPROVEN as a bounded claim.** RadAssist reliably *withholds* on color / synthetic /
non-CXR-DICOM inputs, and cleanly separates raw score from calibrated P. But (a) the
abstain gate has **zero measured operating characteristics** — the behavior card has a
`detection`, `localization`, `calibration`, and `subgroup` section but **no abstain / OOD
section at all**, so its two-sided specificity is asserted, not measured; and (b) the
dominant, un-mitigated failure is **incorrect-diagnosis-by-omission**: a zero-flag chest
X-ray is presented as a clean study with no prominent non-normal disposition, while the
card proves the model misses real disease at the ship threshold (Pneumonia sensitivity
**0.0**, Edema **0.2**, Cardiomegaly **0.625**). A silent "no flag → normal" on an
in-distribution film with missed disease is the single largest way an incorrect clinical
impression reaches the user today.

---

## 1. What the abstain gate actually is (MEASURED code behavior)

`self_audit.assess(img8, color_saturation)` (`self_audit.py:181`) produces a composite
`ood_score` and one of three competences: **read / down-weight / abstain**. Only *reliable*
signals may force ABSTAIN (`self_audit.py:198-207`):

```
reliable_ood = max(color_ood, struct_ood, ae_norm if ae_norm >= 0.9 else 0.0)
ood          = max(color_ood, struct_ood, ae_norm, 0.6 * h_score)
abstain  iff reliable_ood >= OOD_ABSTAIN_THRESHOLD (0.75)
down-weight iff ood       >= OOD_CAUTION_THRESHOLD (0.50)
```

The four signals and their real reach:

| Signal | Source | Can force ABSTAIN? | Real reach |
|---|---|---|---|
| Color saturation | `_color_component`, thr `COLOR_SAT_OOD=0.12` | Yes (reliable) | Strong for color photos/screenshots/selfies. **Zero for any grayscale radiograph.** |
| Synthetic/flat structure | `_structure_component` (local var + histogram entropy) | Yes (reliable) | Catches test patterns/UI screenshots/flat fills. **Low on organic anatomy** (a real knee/hand film has sensor texture, so it is NOT flagged synthetic). |
| AE reconstruction error | TorchXRayVision `ResNetAE 101-elastic`, `AE_ERR_LOW=0.015 / HIGH=0.15` | Only if `ae_norm >= 0.9` (err ≳ **0.136**) | The config comment itself (`config.py:386-389`) states real CXRs measure ~0.001–0.012 and the AE "**can't catch smooth non-CXR images** and never hard-ABSTAINs alone." |
| Quality heuristics (aspect/dynrange/blur) | `_heuristics` | **No** — down-weight only (`0.6*h_score`) | By design never refuses a plausibly-real film. |

**Consequence (structural, not hypothetical):** for a **smooth grayscale non-chest
radiograph** (knee, hand, abdomen, pelvis, spine) the color signal is 0, the structure
signal is low, and the AE — by its author's own comment — does not reach the 0.9 reliable
bar. **No reliable signal fires, so the gate cannot ABSTAIN it.** It is scored by the
DenseNet as if it were a chest film. This is the OOD gate's blind spot and it is the
class of input most likely to be confused for a CXR.

Degradation path: `SELF_AUDIT_AE` can fail to load (`self_audit.py:46-48`, `_ae_failed`);
on a CPU host (the HF Space target) the gate then runs on **color + synthetic only**, and
the AE column above disappears entirely — silently.

---

## 2. The abstain path as a selective-prediction classifier (and why it is unproven)

Frame the gate as a binary selective predictor `g(x) ∈ {answer, abstain}` sitting in front
of the DenseNet `f(x)`. Two error directions matter and **neither is measured anywhere in
the repo**:

- **Missed-OOD rate (false-answer):** P(read | x is truly OOD). Every missed OOD is a
  potential confident-nonsense diagnosis. Target for a device: near-zero on hard OOD.
- **Over-abstain rate (false-refuse):** P(abstain | x is a real readable CXR). Every
  over-abstain is a denial-of-service on a legitimate film. Target: ≤ ~1%.

The correct measurement is a **risk–coverage curve**: sweep `OOD_ABSTAIN_THRESHOLD`, plot
selective risk (classifier error on the answered set) vs coverage (fraction answered), and
choose the operating point so that selective risk on the covered set ≤ a pre-registered
bound. **This curve does not exist.** `behavior_card.json` scores 300 in-distribution NIH
films and reports detection/calibration/localization/subgroup — there is **no negative-
control / OOD set** and therefore no ROC for `g`. Every abstain constant
(`OOD_ABSTAIN_THRESHOLD=0.75`, `OOD_CAUTION_THRESHOLD=0.5`, `AE_ERR_LOW/HIGH`,
`COLOR_SAT_OOD=0.12`, the `ae_norm>=0.9` reliable bar) is **hand-set with no measured
operating point.** The "abstain over guess" property is thus an architectural intention,
not a validated characteristic — it cannot support an FDA claim as-is.

**Two-sided specificity is exactly what must be measured** and is the core proof obligation:
catch true OOD (high sensitivity of `g`) *without* over-refusing real films (high
specificity of `g`). See §6 for the concrete measurement program.

---

## 3. The "zero-flag reads as normal" gap (the most dangerous path)

### 3a. What the UI does on a clean read (MEASURED)
A `read` result with zero flagged findings produces, in `App.jsx`:
- `CompetenceBanner` → **renders nothing** (returns `null` for `competence==='read'`,
  `CompetenceBanner.jsx:3`).
- `TriageBanner` → **renders nothing** (returns `null` for `triage==='routine'`,
  `TriageBanner.jsx:7`).
- `WhatNotChecked` → present but is a **collapsed `<details>`** (`WhatNotChecked.jsx:15`),
  hidden behind a "What this tool did not check" summary the user must click.
- `Dashboard` worklist row → `'No findings flagged'` on a **green `--success-tint`
  background with priority `Routine`** and a green status dot (`Dashboard.jsx:31-51`).

So the strongest signal the user receives on a missed-disease film is an actively
reassuring green "Routine / No findings flagged." There is **no prominent "this is NOT a
normal read / absence of a flag is not a normal result" disposition** on the CXR path,
even though the identical warning already exists and is prominently shown on the CT CADe
panel ("This is NOT a 'normal' result…", per `inv_safety.md`). The honesty copy that does
exist (`InfoPage.jsx:69`, `WhatNotChecked.jsx`, the `llm.py:58-60` prompt line, the
`templates.py:74` patient-summary line) is real but is either on a separate page or behind
a click — it is not on the result surface at read time.

### 3b. Why "no flag" is demonstrably not "normal" (MEASURED from the card, t=0.5 ship threshold)
Missed positives that fall into the no-flag bucket at the shipped flag threshold 0.5,
computed as `positives × (1 − sensitivity)` from `behavior_card.json`:

| Pathology | Positives | Sensitivity @0.5 | Missed → "no flag" |
|---|---|---|---|
| **Pneumonia** | 2 | **0.0** | **2 (all)** |
| **Edema** | 5 | **0.2** | **4** |
| **Cardiomegaly** | 16 | 0.625 | 6 |
| Effusion | 31 | 0.774 | 7 |
| Consolidation | 20 | 0.75 | 5 |
| **Pneumothorax** (the one true emergency) | 9 | 0.778 | 2 |
| Infiltration | 44 | 0.909 | 4 |
| Atelectasis | 22 | 0.864 | 3 |
| Pleural_Thickening | 12 | 0.75 | 3 |
| Nodule | 7 | 0.714 | 2 |

These are MEASURED per-label misses on the NIH sample. The **study-level NPV of the
no-flag state is NOT computed by the harness and must not be invented** — but the table
proves the no-flag state carries real, non-trivial missed disease, including 2 of 9
pneumothoraces and every pneumonia. Publishing a measured NPV at realistic prevalence, and
turning the silent green "Routine" into an explicit non-claim, are the two required fixes.

### 3c. Nuance — the generated *report* is clinician-gated (mitigation, not gap)
The template/LLM report normal language ("No acute cardiopulmonary abnormality identified.",
`templates.py:179`; per-region negatives at `templates.py:111,121,124,126`) is driven by
the **clinician's structured form** `s`, and the outright all-clear impression fires only
when `s.reviewed_no_acute` is set (`templates.py:177-181`); the LLM prompt explicitly warns
"no findings … does not mean the study is completely normal" (`llm.py:58-60`). So the
report attributes a normal read to the human, which is defensible. **Residual risk:** the
FINDINGS section still emits per-region normal sentences for every unchecked region by
default, so a hastily generated report reads as regionally normal even when the clinician
confirmed nothing (`templates.py:110-126`). Lower rank than 3a because it requires clinician
action, but it launders template defaults into normal-sounding prose.

---

## 4. The other gates, audited

- **Non-chest hard-reject (`analyze.py:38`):** fires **only** when `source_format=="dicom"`
  AND `modality ∉ CXR_MODALITIES`. Two holes: (i) a **PNG/JPG has no modality tag**, so a
  non-chest radiograph as PNG bypasses routing entirely and falls through to the OOD gate
  blind spot of §1; (ii) `CXR_MODALITIES` includes **`"OT"` (Other/secondary-capture)**
  (`config.py:371`) — a DICOM tagged `OT` is *accepted and scored*, so any non-chest image
  wrapped as an OT secondary capture is routed into the chest model rather than refused.
- **Anatomy-plausibility gate (`ANATOMY_GATE_MODE="suppress"`, `ANATOMY_MIN_OVERLAP=0.20`):**
  a model gating a model, defaulting to **delete**. A PSPNet mis-segmentation can remove a
  *true* finding (a safety-layer-induced false negative). Its FN/FP cost is **not in the
  behavior card** — unmeasured. It also only runs on findings that get **localized**;
  localization is capped/priority-first (`analyze.py:85`, `vision_xray.py:820-826`), so a
  flagged-but-not-localized finding surfaces with **no anatomy/background plausibility
  check** and a `not_localized` caption.
- **Background gate (`ATTENTION_BG_SUPPRESS=0.55`):** removes flags whose attention lands on
  the black border — reasonable, but same "only runs when localized" caveat.
- **Marker inpainting (`_mask_burned_in_markers`):** a genuine shortcut-learning defense
  (Zech/DeGrave); inpaints the *model's* copy only, clinician sees the original. No safety
  objection; it does not affect the abstain decision.
- **Triage banner:** correctly fires only on **calibrated** P ≥ 0.30 (`triage.py:39`), so an
  over-confident raw score can't manufacture an emergency — good. The flip side is §3a: a
  routine result renders no banner.
- **Flag threshold = raw 0.5:** calibration is display-only and never moves a flag
  (`vision_xray.py`, disposition in `triage.py:94-97`). The card's 0.50–0.60 bin holds 1480
  instances at mean conf 0.523 but only **8.2% observed positive** — most near-threshold
  flags are false positives dressed as "Flagged for review" (over-confidence path, §5).

---

## 5. EVERY concrete path by which an incorrect / over-confident diagnosis can still reach the user, RANKED

1. **Missed in-distribution disease read as normal (omission).** Zero-flag CXR → no
   prominent non-normal disposition; Dashboard shows green "Routine / No findings flagged".
   Card proves misses: Pneumonia sens 0.0, Edema 0.2, Cardiomegaly 0.625, 2/9 pneumothorax.
   *Highest risk; no measured NPV; no result-time banner.* (§3)
2. **Grayscale non-chest radiograph (knee/hand/abdomen/spine) scored as a chest film.** OOD
   gate has no reliable signal for it (color 0, structure low, AE can't reach 0.9 on smooth
   images per `config.py:388`); if uploaded as PNG it also bypasses modality routing. Yields
   confident chest-pathology flags on a non-chest bone. (§1, §4)
3. **`OT`/secondary-capture and PNG/JPG routing bypass.** `CXR_MODALITIES` includes `"OT"`
   and PNG/JPG carry no modality tag → non-chest content reaches the chest model without the
   hard 422. (§4)
4. **Over-confident false-positive flags near the 0.5 raw threshold.** 0.50–0.60 band is
   8.2% positive → most borderline flags are false positives surfaced as findings; the
   "borderline" disposition softens but still presents a positive. (§4)
5. **Weak-but-shown labels over-trusted.** Nodule (AUROC 0.626) and Pneumonia (0.458, sens
   0.0) are kept-with-caution, not hidden — a hurried reader may act on a near-chance flag.
6. **Anatomy `suppress` gate deletes a true finding.** Safety-layer-induced false negative
   from PSPNet mis-segmentation; FN cost unmeasured; only runs on localized findings. (§4)
7. **Calibration is in-distribution; triage trusts calibrated P.** AP vs PA AUROC gap
   already 0.784 vs 0.807; off-site/scanner/supine shift miscalibrates P, and the triage
   banner (and any P-gated disposition) inherits that error.
8. **Lateral / rotated / inverted / pediatric PNG scored as frontal.** Lateral down-weight
   needs a DICOM `ViewPosition` tag (`analyze.py:60-65`); a lateral PNG is scored as frontal;
   no rotation/inversion/pediatric detector exists.
9. **Silent AE degradation.** If the AE fails to load (likely on CPU host), the gate drops to
   color+structure only with no user-visible notice, widening gap #2.
10. **Report FINDINGS template defaults to per-region normal prose** even when nothing was
    confirmed (`templates.py:110-126`) — clinician-gated, so lowest rank.

---

## 6. Recommended safeguards (RECOMMENDATION — not implemented)

- **Explicit non-normal disposition on every zero-flag CXR.** Add a first-class result-time
  banner mirroring the CADe panel: *"This is NOT a normal read — the tool checks a fixed set
  of findings and can miss real disease; absence of a flag is not a normal result."* Promote
  `WhatNotChecked` out of the collapsed `<details>`. Recolor the Dashboard "No findings
  flagged" row away from green/`--success-tint` to a neutral "Not a normal read" state.
- **Publish the NPV of the no-flag state** at realistic clinical prevalence (not test-set
  prevalence), per label and study-level, into the behavior card; surface it beside the
  zero-flag banner. Do not ship a fabricated number — compute it on a held-out enriched set.
- **Measure the abstain gate as a first-class selective classifier.** Build a negative-
  control OOD set (non-chest radiographs incl. **smooth grayscale bone films**, CT/MR-as-PNG,
  photos, screenshots, synthetic patterns, inverted/rotated/lateral/pediatric, both DICOM and
  PNG-stripped). Report missed-OOD and over-abstain rates with CIs; add an `abstain` section
  to `behavior_card.json`. Choose `OOD_ABSTAIN_THRESHOLD` from the **measured ROC / risk–
  coverage curve** at a pre-registered operating point (e.g. ≥0.99 catch on hard-OOD at ≤1%
  over-abstain), replacing every hand-set constant in §1.
- **Close the routing/OOD holes:** drop `"OT"` from `CXR_MODALITIES` (or route OT to a
  confirm step); add a grayscale-non-chest / anatomy-presence check so PNG bone films abstain;
  detect and warn on inversion/rotation/lateral for tag-less PNGs; surface AE-unavailable
  degradation to the user.
- **Set the flag threshold from calibrated P at a chosen operating point**, not a fixed raw
  0.5, so a surfaced finding corresponds to a defensible probability; report alert-burden
  (flags per normal film).
- **Measure the anatomy/background suppression gates** (suppress-TP vs remove-FP tradeoff)
  and add their FN/FP to the behavior card before trusting `suppress` mode; consider
  `warn_only` as the default until measured.

---

## 7. Verdict on the negative claim

"Even when it cannot identify disease it never emits an incorrect diagnosis" is **REFUTED as
stated**: the system emits an implied-normal (green Routine, no flags) on films with measured
missed disease, and can score non-chest grayscale radiographs as chest films. The **defensible,
provable** version of the claim is narrower and requires work: *"the tool makes no explicit
normal assertion, abstains on inputs it can detect as OOD at a measured operating point, and
publishes the NPV of its no-flag state."* Reaching even that requires (1) a measured abstain
ROC / risk–coverage curve, (2) a published no-flag NPV, (3) an explicit result-time non-normal
banner, and (4) closing the OT/PNG/grayscale routing-and-OOD holes. None of the four exist today.
