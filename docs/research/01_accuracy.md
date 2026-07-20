# 01 — Detection Accuracy Audit (Chest X-ray)

**Team:** RadAssist Accuracy + Safety Research
**Scope:** Is the disease-detection accuracy *actually accurate and reliable*? Per-pathology
verdict, the false-positive burden at the flag threshold, and the top accuracy risks.
**Ground truth:** `backend/behavior_card.json` (== `validation/behavior_card.json`, byte-identical,
42 378 B), produced by `validation/run_validation.py` scoring `vision_xray.predict_probs` on a
**300-image NIH ChestX-ray14 sample**. Served at `GET /api/behavior-card`.
**Method note:** every number below tagged **MEASURED** is read from the card or arithmetically
derived from its fields (PPV, flag rate, aggregate precision). Items tagged **RECOMMENDATION** are
mine. Nothing is fabricated. Reliability language follows the harness's own rule
(`run_validation.py:118-119`): a metric is `reliable` only when **positives ≥ 20**.

---

## 0. Headline verdict

**The accuracy is NOT uniformly accurate, and for most pathologies it is not even reliably
*measured*.** Of 14 pathologies, only **4** clear the harness's own reliability bar (≥20 positives):
Atelectasis, Effusion, Infiltration, Consolidation. The other 10 are single points on 0–18
positives — indicative at best, statistical noise at worst (Pneumonia = **2** positives, sens
**0.0**). Discrimination (AUROC) is moderate-to-good on the reliable four (0.73–0.84), but the
**operating point at raw score 0.5 is placed in the worst-calibrated, highest-density band**, so
the *flag stream itself* is ~90% false positives on in-distribution data. Accuracy of *ranking* ≠
accuracy of the *flags the clinician actually sees*.

---

## 1. Per-pathology verdict: reliable / weak / unmeasured

Sorted by evidence strength. `pos` = positive cases in the 300-image sample. PPV@0.5 is the
precision of the flag at the shipped raw threshold, computed at **test-set prevalence**
(TP=sens·P, FP=(1−spec)·N); real-clinic PPV is lower still.

| Pathology | pos | AUROC | Sens@0.5 | Spec@0.5 | PPV@0.5 | Verdict |
|---|---|---|---|---|---|---|
| **Infiltration** | 44 | 0.732 | 0.909 | 0.355 | **0.195** | RELIABLE (n) — weak discrimination, near-useless specificity |
| **Effusion** | 31 | 0.839 | 0.774 | 0.799 | **0.307** | RELIABLE — best overall; still ~2 in 3 flags false |
| **Atelectasis** | 22 | 0.783 | 0.864 | 0.637 | **0.159** | RELIABLE — moderate AUROC, poor precision |
| **Consolidation** | 20 | 0.767 | 0.750 | 0.657 | **0.135** | RELIABLE (just barely) — moderate |
| Mass | 18 | 0.799 | 0.944 | 0.422 | 0.094 | WEAK (n<20) — good AUROC point est., 1-in-11 flag precision |
| Cardiomegaly | 16 | 0.906 | 0.625 | 0.880 | 0.227 | WEAK (n<20) — highest AUROC but on 16 pos; misses 3/8 |
| Pleural_Thickening | 12 | 0.688 | 0.750 | 0.590 | 0.071 | WEAK — AUROC below the 0.70 "floor", but kept (unreliable) |
| Emphysema | 11 | 0.755 | 0.818 | 0.471 | 0.056 | WEAK |
| Fibrosis | 10 | 0.734 | 0.900 | 0.221 | 0.038 | WEAK — spec 0.22 ⇒ flags almost everything |
| **Pneumothorax** | 9 | 0.828 | 0.778 | 0.619 | 0.059 | NOISE (n=9) — critical label, only 9 positives |
| Nodule | 7 | 0.626 | 0.714 | 0.382 | 0.027 | NOISE — near-chance AUROC, 1-in-37 flag precision |
| Edema | 5 | 0.766 | 0.200 | 0.919 | 0.040 | NOISE — sens 0.2 (misses 4/5) |
| **Pneumonia** | 2 | 0.458 | **0.000** | 0.862 | **0.000** | NOISE — below chance, catches 0/2; a 2-point "metric" |
| Hernia | 0 | null | — | — | — | UNMEASURED — 0 positives, correctly null |

**Reliable four, with uncertainty:** even these have wide confidence intervals. A Hanley-McNeil SE
for Effusion (best sampled, 31 pos / 269 neg) is ≈0.045 → **95% CI ≈ [0.75, 0.93]** on the 0.839
AUROC. For the 9–18-positive "weak" group the 95% CI half-width is ≈0.10–0.16, i.e. the point
estimates (e.g. Cardiomegaly 0.906, Mass 0.799) are **not distinguishable from ~0.75**. The
card exposes none of these CIs. **MEASURED discrimination is genuine but coarse; treat only the
four ≥20-pos labels as load-bearing, and even those as ±0.09.**

**Localization is separately weak and separately under-powered** (`behavior_card.json`
`localization`, 51 boxes total, 3–11 per class): hit-rate **0.0 / IoU 0.0 for Atelectasis and
Pneumonia**, Pneumothorax 0.167 / IoU 0.008, best is Cardiomegaly 0.6 / IoU 0.129 on 10 boxes.
Grad-CAM here is a region-of-attention sanity check, not evidence the flag is spatially correct.

---

## 2. The false-positive burden at the flag threshold (the core finding)

The flag decision is **`p_raw >= 0.5`** (`vision_xray.py:667`, threshold from `config.py:46`;
per-label overrides exist only for Effusion 0.5342 and Infiltration 0.5252, `calibration.json`).
Calibration is **display-only and never gates the flag** (`vision_xray.py:662-667` — `cp` is
computed but the `flagged=` decision uses raw `p`).

**MEASURED, derived from the card's own fields (two independent routes agree):**

- **Route A (per-label PPV, §1 table):** aggregate over the 13 measured labels at t=0.5 →
  **~165 true-positive flags vs ~1 467 false-positive flags** across 300 images ×13 labels.
- **Route B (calibration reliability table, `behavior_card.json` `calibration.overall`):**
  label-instances scoring ≥0.5 = 1480+111+33+11+2 = **1 637 of 4 200 (39.0%)**; true positives
  among them = Σ(obs·count) ≈ **165**.

Both routes give **aggregate flag precision ≈ 165 / 1 637 ≈ 10%**. i.e.:

> **At the shipped 0.5 threshold, ~39% of all label-instances are flagged, and ~9 out of every 10
> flags are false positives — on the model's own in-distribution test data.** That is roughly
> **~4.9 false flags per image** before any clinical-prevalence penalty.

Why: the single band **[0.5, 0.6)** holds **1 480 instances (35% of everything) at mean confidence
0.523 but only 8.2% observed-positive** (`calibration.overall.reliability`). The operating point
sits exactly inside the largest, worst-calibrated pile of scores. This band alone dominates the
**overall ECE = 0.2437**.

**The threshold is also knife-edged.** In the per-label `curve` arrays, sensitivity collapses
between t=0.50 and t=0.55 for many labels: Pneumothorax **0.778 → 0.0**, Emphysema **0.818 → 0.0**,
Nodule 0.714 → 0.143, Infiltration 0.909 → 0.386, Consolidation 0.75 → 0.35, Fibrosis 0.9 → 0.2.
This is the op_norm banding (§3) piling scores into 0.50–0.55, so a 0.05 threshold move swings
sensitivity from "catches most" to "catches none." The 0.5 operating point is on the steepest part
of the score distribution — the least stable place to put it.

**Verdict on precision:** even the best pathology (Effusion, PPV 0.31) means **2 of 3 effusion
flags are false**; the median measured label is <0.10. The flag list is a **high-sensitivity,
very-low-precision review prompt**, not an accurate detector. This is defensible *only* as
"signal for review," which the product framing claims — but it is the dominant accuracy limitation.

---

## 3. Op-norm banded scoring — why calibration and precision are both poor

Displayed `probability` = per-label **op_norm** output averaged across the ensemble
(`vision_xray.py:264-302`), where 0.5 is defined as each model's operating point. Consequences,
all **MEASURED** in the reliability table:

- op_norm maps a large fraction of raw sigmoid outputs into a narrow band just above 0.5, so
  **35% of all label-instances land in [0.5,0.6)** — a spike, not a spread.
- Because that spike is only 8.2% positive, the displayed number is **systematically
  over-confident by ~0.44 in the exact band where flagging happens** (conf 0.523 vs obs 0.082).
- Per-class ECE ranges from Hernia 0.044 / Edema 0.079 (rarely fires) to **Fibrosis 0.429 /
  Nodule 0.411 / Mass 0.379** (worst). The over-confidence is concentrated in the labels with the
  worst precision — a compounding failure.

The isotonic map (`calibration_map.json`, `CALIBRATION_MODE=isotonic`) correctly remaps the
*displayed* 0.52 down to ~0.08 and feeds triage (which fires only on calibrated P>0.30, per
inv_safety), so an over-confident raw score **cannot** manufacture a red banner. **But the flag
itself is unchanged**, so calibration fixes the *number shown* and the *triage banner*, not the
*composition of the review list*.

### 3a. Calibration-map provenance defect (NEW — accuracy governance)

`calibration_map.json` ships an isotonic map for **12 labels including Nodule (7 pos), Edema (5),
Pneumothorax (9), Emphysema (11), Fibrosis (10), Pleural_Thickening (12)** — all **below the
harness's own guard** in `run_validation.py:223` (`if t.size < 40 or pos < 12 ... excluded`), and
its `excluded` block is empty / `meta` lacks the `min_positives` field the current code writes
(`run_validation.py:234`). **The shipped map was produced by an older, looser generator than the
current harness and is inconsistent with the current 300-image card.** Effect: authoritative-looking
`calibrated_probability` values are shown for labels whose isotonic step is fit on **5–11 positive
events** — precisely the "small-sample isotonic step can invent a misleading calibrated
probability" failure the code comment (`run_validation.py:219-222`) says it is guarding against.
**RECOMMENDATION:** regenerate `calibration_map.json` from the current harness so exclusions match,
or set those labels to `insufficient_data`.

---

## 4. AUROC auto-denial — what it actually suppresses (answer: nothing, today)

Logic in `vision_xray._denial` (`vision_xray.py:336-357`) + `config.py:246-259`:

- **Static denylist** (`LABEL_DENYLIST={"Fracture"}`) — always hidden. Fracture is not a NIH-14
  label and not in the card; this is a scope statement, not a data-driven denial.
- **AUROC denial** fires only when `auroc < 0.70` **AND** the measurement is `reliable` (≥20 pos),
  because `LABEL_MIN_AUROC_REQUIRE_RELIABLE=1` (`config.py:258`).

Cross-referencing the card: the only sub-0.70 labels are **Pleural_Thickening 0.688 (12 pos,
reliable=false)**, **Nodule 0.626 (7, false)**, **Pneumonia 0.458 (2, false)** — **none are
`reliable`.** Therefore **the AUROC auto-denial currently hides zero labels.** Every weak label,
including the **below-chance Pneumonia detector (AUROC 0.458, sens 0.0)** and Nodule (0.626), is
**surfaced to the user** with only a caution chip.

**Assessment:** the design rationale is honest — hiding a label on a 2-positive AUROC would assert a
measurement that doesn't exist, and the reliability guard is the right instinct. **But the net
effect is that a detector empirically worse than a coin flip on the only 2 positives it saw is
shown as a finding.** The guard protects against *false denial* at the cost of *no protection
against surfacing a known-bad label*. For a critical, high-consequence label this is the wrong
default. **RECOMMENDATION:** for a small, curated critical set (Pneumonia, Pneumothorax), when
positives are too few to measure, treat "unmeasurable" as **abstain/insufficient-evidence on that
label** rather than "surface with caution" — an explicit non-claim, not a low-value flag. Separately,
gate flags on **calibrated P at a chosen operating point** rather than raw 0.5 (§2).

---

## 5. Reliability of the numbers themselves (sample-size audit)

- **300 images, 4 200 label-instances, ~207 total label-positives (4.9% per-label prevalence).**
- Only **4/14 labels** have ≥20 positives. **6/14 have <12** (Pneumothorax 9, Nodule 7, Edema 5,
  Pneumonia 2, plus Fibrosis 10, Emphysema 11). **1/14 (Hernia) has 0.**
- The two **most safety-critical** labels are the **worst-sampled**: Pneumothorax (9 pos) and
  Pneumonia (2 pos). No usable sensitivity estimate exists for either. Pneumonia sens 0.0 is "0 of
  2" — it carries essentially no information, yet reads as a damning number.
- Subgroup (`subgroup.groups`): **PA micro-AUROC 0.807 (185 img) vs AP 0.784 (115 img)** —
  a real, expected acquisition-shift gap; both are micro-averages that hide per-label collapse.
- Localization boxes: 51 total, 3–11 per class — **under-powered to conclude anything** beyond
  "attention is not reliably on the lesion for Atelectasis/Pneumonia/Pneumothorax."

**Verdict:** the card is an honest **engineering sanity check** (as its own caveat states), not an
accuracy measurement. The reliable-four AUROCs are trustworthy to ±~0.09; **everything else is
directional and must not be quoted as performance.**

---

## 6. Top accuracy risks (ranked)

1. **Flag precision ≈10% at t=0.5 (MEASURED).** ~9/10 surfaced flags are false positives in-dist;
   worse at clinical prevalence. Dominant accuracy limitation. → gate on calibrated P at a chosen
   operating point; report alert-burden per normal film.
2. **Miss risk on critical labels (MEASURED where sampled).** Pneumonia sens 0.0 (0/2), Edema 0.2
   (misses 4/5), Cardiomegaly 0.625 (misses 3/8); Pneumothorax "0.778" rests on 9 cases. Combined
   with no explicit "not a normal read" on a zero-flag CXR (inv_safety gap #1), this is
   incorrect-diagnosis-by-omission risk. → sensitivity-first operating points on critical labels +
   published NPV.
3. **Op_norm over-confidence in the flag band (MEASURED: ECE 0.244, conf 0.523 vs obs 0.082).**
   Calibration fixes display + triage but not the flag list. → make calibrated P gate the flag.
4. **Threshold instability (MEASURED: sens cliffs 0.50→0.55).** Operating point sits on the
   steepest part of the score distribution. → select threshold from the ROC curve per label with CIs.
5. **10/14 labels statistically unreliable, incl. the 2 most critical (MEASURED).** → enrich the
   validation set (RSNA Pneumonia, SIIM-ACR Pneumothorax for pixel truth) before any accuracy claim.
6. **AUROC auto-denial suppresses nothing today; below-chance Pneumonia is surfaced (MEASURED).**
   → abstain-per-label for unmeasurable critical labels (§4).
7. **Calibration-map provenance defect (MEASURED inconsistency, §3a).** Calibrated probabilities
   shown for labels the current harness would exclude (5–11 positives). → regenerate the map.
8. **Weak/near-zero localization (MEASURED: 0.0 hit-rate Atelectasis/Pneumonia).** Attention is not
   evidence of a correct flag; keep it labelled as attention-only (already done in captions).
9. **In-distribution, single-source optimism (MEASURED: PA/AP gap; card caveat).** All numbers on
   NIH relatives of the training set. → external multi-site validation (PadChest, VinDr-CXR).

---

## 7. Bottom line

- **Is the accuracy accurate?** *Discrimination:* moderately, and only for the 4 labels with ≥20
  positives (AUROC 0.73–0.84, ±~0.09). *Flags:* no — the review list is ~90% false positives at the
  shipped threshold. *The other 10 labels:* not reliably measured; 2 critical ones (Pneumonia,
  Pneumothorax) are essentially unmeasured.
- **Is it reliable?** Only as a high-sensitivity, low-precision **review prompt**, which matches the
  product's "signal for review, not a diagnosis" framing — and that framing is doing all the
  safety work, not the numbers.
- The card is honestly captioned and the safety scaffolding (calibration→triage separation, raw-vs-
  calibrated split, reliability-guarded denial) is sound in intent; the gap is that **accuracy of
  the flag stream and of the critical labels is neither high nor measured.**

*All MEASURED values trace to `backend/behavior_card.json` and `run_validation.py`; PPV, flag-rate,
and aggregate-precision figures are arithmetic on those fields and reproducible from §2.*
