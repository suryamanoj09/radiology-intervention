# 02 — Calibration & Operating Point (CXR)

**Team:** RadAssist Accuracy + Safety research. **Mode:** read-only analysis.
**Ground truth:** `backend/behavior_card.json` (served at `GET /api/behavior-card`), the
shipped isotonic map `backend/calibration_map.json`, the flag-threshold map
`backend/calibration.json`, and code in `backend/app/services/calibration.py`,
`vision_xray.py`, `triage.py`, `config.py`.
Every number below is **MEASURED** from those files unless prefixed **RECOMMENDATION**.
Nothing here is fabricated; where the data does not exist I say so.

---

## 0. How the pipeline handles score vs. probability (MEASURED code behavior)

- The model emits a **banded `op_norm` score** per label where `0.5 == that model's
  operating point` (`vision_xray.py:9-11`, `:649-650`).
- **Flag decision uses the RAW score only**: `flagged = p >= _threshold_for(label)`
  (`vision_xray.py:667`); `_threshold_for` = `LABEL_THRESHOLDS.get(label,
  FINDING_THRESHOLD=0.5)` (`vision_xray.py:305-307`, `config.py:46`). Calibration can
  **never move a flag** — a genuinely good property.
- **Calibrated P is display/disposition/triage only**: `cp = calibration.calibrate(label,
  p)` (`vision_xray.py:662`), shipped as `calibrated_probability` alongside raw
  `probability` and a `calibration_state` (`vision_xray.py:663-666`).
- **Triage banner fires ONLY on calibrated P** ≥ `PRIORITY_MIN_CALIBRATED_P = 0.30`
  (`triage.py:38-48`, `config.py:61`). An over-confident raw 0.54 whose calibrated P is
  ~0.08 cannot raise a red banner — the intended alert-fatigue defense.
- **Calibration map** = per-label **isotonic** piecewise-linear interpolation over a fixed
  `x = 0.00…1.00` step-0.05 grid → `y` (`calibration.py:76-88`, `calibration_map.json`).
  Fitted on the **NIH ChestX-ray14 sample**, `meta.caveat: "In-distribution isotonic
  remap; recalibrate on target data."`

This score/P separation is honest by construction. The problems below are in the
**numbers**, the **isotonic tails**, the **coverage**, and the **operating point**.

---

## 1. Overall calibration is bad and the badness is concentrated (MEASURED)

**Overall ECE = 0.2437** over **4200 label-instances**, 10 bins
(`behavior_card.json` `calibration.overall`). **Every bin is over-confident** (observed
positive rate < mean confidence in all 10 bins). Per-bin decomposition (gap = conf−obs,
contribution = gap × count/4200):

| bin | count | conf | obs | gap | ECE contribution |
|---|---|---|---|---|---|
| 0.0–0.1 | 1379 | 0.031 | 0.007 | 0.024 | 0.008 |
| 0.1–0.2 | 458 | 0.146 | 0.022 | 0.124 | 0.014 |
| 0.2–0.3 | 305 | 0.247 | 0.030 | 0.217 | 0.016 |
| 0.3–0.4 | 232 | 0.348 | 0.034 | 0.314 | 0.017 |
| 0.4–0.5 | 189 | 0.452 | 0.032 | 0.420 | 0.019 |
| **0.5–0.6** | **1480** | **0.523** | **0.082** | **0.441** | **0.155** |
| 0.6–0.7 | 111 | 0.640 | 0.225 | 0.415 | 0.011 |
| 0.7–0.8 | 33 | 0.733 | 0.485 | 0.248 | 0.002 |
| 0.8–0.9 | 11 | 0.856 | 0.182 | 0.674 | 0.002 |
| 0.9–1.0 | 2 | 0.924 | 0.500 | 0.424 | 0.000 |

**Two findings dominate:**

1. **The 0.5–0.6 band alone is 64% of the total ECE** (0.155 of 0.2437). It holds **1480
   of 4200 instances (35%)** at mean confidence 0.523 but only **8.2% observed positive**.
   This is a direct artifact of `op_norm` banding: the model piles scores onto its
   operating point (~0.5). 68% of ALL mass sits in just two bins — **0.0–0.1 (1379) and
   0.5–0.6 (1480)** — the score distribution is **bimodal**, not spread. There is almost no
   usable resolution between 0.1 and 0.5 or above 0.6.
2. **Reliability shape:** obs rises roughly monotonically with conf (so *ranking* is
   partially preserved — consistent with micro-AUROC ~0.80), but every point sits **far
   below the diagonal**. A reliability diagram would show all 10 points hugging the x-axis
   until conf≈0.7, a giant mass marker at (0.52, 0.08), and 2–3 noisy sparse points above
   0.7 (the 0.8–0.9 point actually *drops* to obs 0.182 on 11 counts — noise). **Net: the
   model is systematically, severely over-confident across the entire displayed range.**

---

## 2. Per-class ECE — and why low ECE here is a TRAP (MEASURED)

Per-class ECE (`calibration.per_class`), best→worst:

| label | ECE | positives | note |
|---|---|---|---|
| Hernia | 0.0441 | **0** | not evaluable — all scores ~0, trivially "calibrated" |
| Edema | 0.0790 | 5 | scores stay low; only 5 positives |
| Cardiomegaly | 0.0976 | 16 | genuinely the best-behaved real label |
| Pneumonia | 0.1216 | **2** | **misleading** — every bin obs≈0, sens 0.0, AUROC 0.458 |
| Effusion | 0.1467 | 31 | best *reliable* label |
| Consolidation | 0.2264 | 20 | |
| Atelectasis | 0.2425 | 22 | |
| Pneumothorax | 0.2763 | 9 | critical label, poorly calibrated |
| Pleural_Thickening | 0.3028 | 12 | |
| Infiltration | 0.3228 | 44 | worst *reliable* label |
| Emphysema | 0.3381 | 11 | |
| Mass | 0.3789 | 18 | |
| Nodule | 0.4114 | 7 | |
| Fibrosis | 0.4294 | 10 | worst overall |

**TRAP (RECOMMENDATION to flag in the UI):** low per-class ECE does **not** mean
trustworthy. **Hernia (0.044) and Pneumonia (0.122)** score "well-calibrated" only because
their scores stay near 0 and they almost never fire — Pneumonia has **sensitivity 0.0**
(`detection`), so its low ECE reflects *never predicting the positive*, not accuracy. Any
calibration dashboard must show ECE **next to** positives-count, sensitivity, and AUROC, or
it will mislead. **Do not surface a per-class ECE number without its sample size.**

---

## 3. The isotonic map fixes the mid-band but INTRODUCES a new failure at the top (MEASURED)

The map correctly **deflates** the over-confident 0.5–0.6 band. Example: Infiltration raw
0.523 → `y`≈0.11–0.20; Consolidation raw 0.53 → ~0.069→0.229; these match the observed
~8–15% positive rate. In-distribution, the remapped reliability diagram would sit close to
the diagonal **by construction** (isotonic is fit to this exact data → in-sample ECE is
near-zero but **optimistically biased**; there is no held-out ECE reported).

**But the isotonic tails are pinned to 1.0 on 1–3 instances** (`calibration_map.json`):

| label | knee → tail | tail value | data supporting the tail |
|---|---|---|---|
| **Pneumothorax** | y jumps **0.0337 (x=0.50) → 1.0 (x≥0.55)** | 1.0 | 0.6–1.0 bins **count 0** in card |
| Cardiomegaly | 0.1143 (0.55) → 0.3636 (0.60) → 1.0 (x≥0.65) | 1.0 | 0.7–0.8 bin count 3 |
| Pleural_Thickening | 0.391 (0.65) → 1.0 (x≥0.70) | 1.0 | 0.7+ bins count 0 |
| Effusion | 0.7151 (0.90) → 1.0 (x≥0.95) | 1.0 | 0.9–1.0 bin count 1 |

**Consequence — a real, if low-frequency, defect:** triage fires on calibrated P ≥ 0.30
(`triage.py:39`) and **Pneumothorax at cp ≥ 0.30 escalates to a RED "urgent" banner**
(`triage.py:42-45`). Because `calibrate()` returns **exactly 1.0** for any Pneumothorax raw
score ≥ 0.55 (`calibration.py:82-83`, `x >= xs[-1]` / grid hit), a single high-scoring
**negative** (the card shows sens 0 above 0.55 — i.e. no *positives* live up there, so the
occupants are noise/negatives) is remapped to **P = 100%** and can manufacture a **false
urgent pneumothorax banner**. The raw-score flag is unaffected (good), but the calibrated
number driving triage is not defensible. **This is calibration over-correcting into false
certainty on thin data.**

> **RECOMMENDATION (code, out of scope to change here):** require a minimum bin support
> (e.g. ≥10 instances) before an isotonic knot may reach an extreme; **clamp the calibrated
> P used by `triage.assess` to a ceiling (e.g. 0.90)**; and/or fit **Platt/beta** on sparse
> labels where isotonic's step tails are unstable. At minimum, do not let a 0.05 raw-score
> step (0.50→0.55) swing calibrated P from 0.03 to 1.00.

---

## 4. Coverage gaps in the shipped map (MEASURED)

- `calibration_map.json.per_label` covers **13 labels**. **Pneumonia and Hernia are
  absent.** For those, `calibrate()` returns `None` → UI shows **"not calibrated"**
  (`FindingExplanation.jsx:46,66`).
- **Dead code path:** `calibration.state()` (`calibration.py:47-57`) can return
  `insufficient_data` only if the map has an `"excluded"` key — **the shipped map has no
  such key**. So `insufficient_data` is **never returned in production**; every label is
  either `calibrated` (13) or `uncalibrated` (Pneumonia, Hernia). The UI therefore cannot
  distinguish "deliberately excluded for too few positives (Pneumonia, 2 pos)" from "no map
  at all." **RECOMMENDATION:** emit `"excluded": {"Pneumonia": "2 positives", "Hernia": "0
  positives"}` so the honest reason is shown.
- **Coherence gap:** an *uncalibrated* label can still be **flagged** on raw score ≥ 0.5
  and surfaced with a bare `score X%` and no P. For **Pneumonia (AUROC 0.458, sens 0.0)** a
  flagged finding is essentially meaningless yet still shows a "52%"-style number. The
  AUROC-denial (`_denial`, `vision_xray.py:336-357`) keeps it visible with a caution chip
  because 2 positives is "unreliable" — but a bare score on a sub-chance label invites
  over-trust.

---

## 5. Calibration is IN-DISTRIBUTION ONLY; the PA↔AP shift is unmeasured for calibration (MEASURED gap)

- The card reports **subgroup AUROC only**: PA **0.807** (185 img, 2590 instances) vs AP
  **0.784** (115 img, 1610 instances) (`subgroup.groups`). Discrimination gap is modest
  (0.023).
- **There is NO per-view, per-site, per-scanner, sex, or age ECE / reliability curve in the
  behavior card.** The isotonic map is a **single global-per-label** fit on NIH. AP images
  are portable/supine (sicker patients → higher true prevalence, different gray-level
  statistics); the fitted `score→P` mapping is very likely **mis-scaled on AP**, and the
  triage banner (which trusts calibrated P) inherits that error.
- **We cannot claim the calibration holds out-of-distribution** — the data to prove or
  refute it does not exist. This is asserted risk, not measured. The map's own
  `meta.caveat` concedes it.

---

## 6. Operating point: the uniform raw-0.5 flag is suboptimal AND sits on a cliff (MEASURED)

The `detection[].curve` sens/spec-vs-threshold tables expose two problems.

**(a) Every label has a sensitivity CLIFF at 0.50→0.55** — a direct `op_norm` banding
artifact (scores cluster at the operating point). At t=0.55 sensitivity collapses:
Atelectasis 0.864→**0.273**, Pneumothorax 0.778→**0.0**, Emphysema 0.818→**0.0**,
Consolidation 0.75→**0.35**, Infiltration 0.909→**0.386**, Fibrosis 0.9→**0.2**, Nodule
0.714→**0.143**. **The chosen threshold (0.5) sits on a knife-edge**: a 0.05 move
annihilates recall. This is fragile and is the same banding that wrecks calibration (§1).

**(b) 0.5 is far from the Youden-optimal point for several labels.** Optimal thresholds
computed from the card curves (max sens+spec−1), vs the shipped flag threshold:

| label | shipped thr | Youden-opt thr | sens/spec @ opt | sens/spec @ 0.5 |
|---|---|---|---|---|
| Cardiomegaly | 0.50 | **~0.10** | 1.00 / 0.673 | 0.625 / 0.880 |
| Pneumothorax (critical) | 0.50 | **~0.35** | 1.00 / 0.557 | 0.778 / 0.619 |
| Effusion | **0.5342** (override) | ~0.50–0.55 | 0.774/0.799 – 0.71/0.877 | 0.774 / 0.799 |
| Atelectasis | 0.50 | ~0.50 | 0.864 / 0.637 | 0.864 / 0.637 |
| Infiltration | **0.5252** (override) | ~0.45–0.50 | 0.955/0.309 – 0.909/0.355 | 0.909 / 0.355 |
| Mass | 0.50 | ~0.55 | 0.667 / 0.770 | 0.944 / 0.422 |

**Note the two shipped overrides go the WRONG way for recall.** `calibration.json` raises
Effusion→0.5342 and Infiltration→0.5252 (Youden-J tuning, in-distribution). For a
recall-oriented review aid these *reduce* sensitivity, and because of the cliff at 0.55
they sit right at the edge where Infiltration sensitivity is about to fall off. Meanwhile
Cardiomegaly (opt ~0.10) and Pneumothorax (opt ~0.35) — where a **lower** threshold buys
large sensitivity at acceptable specificity — are left at 0.5.

**(c) Some labels have no good operating point at any threshold** (poor separability):
Infiltration (AUROC 0.732, spec 0.355 at sens 0.909), Fibrosis (0.734, spec 0.221),
Nodule (0.626), Mass (0.799 but spec 0.422 at 0.5). At usable sensitivity their specificity
is low → **high false-positive/alert burden**. These should be **advisory-only**, not
flagged with the same weight as Cardiomegaly/Effusion.

---

## 7. RECOMMENDATIONS

**R1 — Set per-label flag thresholds from the curve, favoring sensitivity with explicit FP
control (not a uniform raw 0.5).**
- Policy: for **critical** labels (Pneumothorax) pick the highest-sensitivity point whose
  specificity is still usable → **Pneumothorax 0.35** (sens 1.00, spec 0.557; already the
  value of `PNEUMOTHORAX_ALERT_THRESHOLD`, so unify the flag with it).
- For **well-separated** labels pick Youden-J → **Cardiomegaly ≈0.10–0.20** (sens
  1.0/0.875, spec 0.67/0.79), **Effusion ≈0.50** (revert the 0.5342 override).
- For **poorly-separated** labels (Infiltration, Fibrosis, Nodule, Mass) do **not** raise
  the bar into the cliff; instead **demote them to advisory** and publish their low
  specificity next to the flag.
- Publish, per label, the chosen (threshold, sensitivity, specificity, PPV@prevalence) as
  the operating-point contract — the card already has the curve to do this.

**R2 — Express the flag threshold as a calibrated-P operating point.** Because `calibrate`
is monotone, a P-threshold ≡ a score-threshold. Choose each label's flag at the score whose
**calibrated P** meets a target (e.g. "flag when P(disease) ≥ P\*_label"), so a surfaced
finding always corresponds to a defensible probability, and the same number drives flag,
disposition, and banner. This removes today's split where the flag is a raw 0.5 but the
shown P is 8–15%.

**R3 — Fix the isotonic tails feeding triage (§3).** Minimum-support per knot; clamp
triage's calibrated P to ≤0.90; prefer Platt/beta on sparse labels. Re-verify that no
0.05 raw step can swing calibrated P by >0.5.

**R4 — Report held-out and subgroup calibration.** Add to the behavior card: (a)
**held-out** ECE (the current isotonic in-sample ECE is optimistic); (b) **per-view ECE**
(PA vs AP) and reliability curves; (c) MCE alongside ECE. Target a stated ceiling
(e.g. ECE ≤ 0.05) and prove it out-of-sample before any clinical claim.

**R5 — Honest UI for score-vs-P.**
- **Lead with calibrated P (or a verbal band: "very unlikely / possible / likely"), and
  de-emphasize the raw score** — a hurried reader reads "score 52%" as ~50/50 when true P
  is 8%. Current `score X% · P≈Y%` (`FindingExplanation.jsx:36-41`) is honest but puts the
  misleading number first.
- Show **per-class ECE only with its positives-count** (§2) so Pneumonia/Hernia's low ECE
  cannot masquerade as reliability.
- Distinguish **`uncalibrated` vs `insufficient_data`** (fix §4) and suppress the bare
  score on sub-chance labels (Pneumonia sens 0.0) or replace it with "not assessable."

**R6 — Retire the operating-point banding fragility.** The single deepest issue is that
`op_norm` piles 68% of scores into two bins and creates a 0.50→0.55 cliff (§1, §6a). No
threshold choice is robust on top of it. Longer-term: calibrate/threshold on the **raw
sigmoid logits** (pre-`op_norm`) so the score is smooth, then fit isotonic/Platt on that
smoother distribution — this both flattens the cliff and gives calibration real resolution.

---

## 8. Bottom line

Calibration is **honestly separated** from flagging in code (flag = raw score, P/triage =
calibrated), which is the right architecture. But the **measured** state is poor: ECE
**0.2437**, systematic over-confidence in every bin, **64% of the miscalibration from one
`op_norm` pile-up band (0.5–0.6, 8.2% positive)**, sensitivity cliffs at 0.55 on nearly
every label, a uniform 0.5 flag that is Youden-suboptimal (esp. Cardiomegaly, Pneumothorax),
two labels uncalibrated, a dead `insufficient_data` path, isotonic tails pinned to 1.0 on
1–3 samples that can **manufacture a false urgent pneumothorax banner**, and **zero
out-of-distribution / subgroup calibration evidence**. The calibrated `P` is trustworthy
**only in-distribution and only in the mid-band**; at the tails and on AP it is not, and the
UI currently leads with the more misleading of the two numbers.
