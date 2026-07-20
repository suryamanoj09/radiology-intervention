# 05 — FDA / Regulatory Readiness Gap Analysis

**RadAssist ACCURACY + SAFETY research team**
Status of the document: research analysis, READ-ONLY. Nothing here changes production code.
Scope: map the RadAssist chest-X-ray (CXR) path and the CT/MRI channels to US FDA
Software-as-a-Medical-Device (SaMD) expectations, IEC 62304, ISO 14971, and clinical-validation
norms; state what exists on-repo today versus what a submission would require.

> **Headline regulatory fact (not opinion).** RadAssist is a **research/portfolio prototype and is
> NOT an FDA-cleared or FDA-registered medical device.** Its own governance doc says so explicitly:
> `INTENDED-USE.md:24-25` — "RadAssist is **not a regulated medical device today**. That safe harbor
> rests entirely on the intended use above" (non-clinical, public/de-identified, no-real-patient).
> `KNOWN-LIMITATIONS.md:9` — "Research-grade, not FDA-cleared." This document analyzes the distance
> between that prototype and a clearable device; it does **not** assert the device is close to clearance.

Throughout, findings are tagged **[MEASURED]** (a fact read from the repo / behavior card),
**[ABSENT]** (a required artifact that does not exist on-repo), or **[RECOMMENDATION]** (what a
submission would need). No metric is invented.

---

## 1. Where the ground truth stands today (the substrate a submission would build on)

**[MEASURED]** The only quantitative performance evidence on-repo is
`validation/behavior_card.json` (served at `GET /api/behavior-card`), produced by the real harness
`validation/run_validation.py`:

- Model: `torchxrayvision densenet121-res224-all`, flag threshold 0.5, **300 images**, calibration
  over **4200 label-instances**, 10 bins (`behavior_card.json:1-5,1438-1439`).
- Data provenance: NIH ChestX-ray14 sample + BBox_List_2017 (per `inv_backend.md:90-92`). This is
  **a single public dataset, single institution (NIH Clinical Center), retrospective**.
- The card's own caveat (`behavior_card.json:5`): *"Engineering sanity check … NOT clinical
  validation, NOT a performance guarantee … in-distribution and optimistic."*
- Overall **ECE = 0.2437** (`behavior_card.json:1439`) — severe miscalibration; the 0.5–0.6
  confidence band holds 1480 instances at mean confidence 0.523 but only 8.2% observed positive
  (`behavior_card.json:1491-1495`).
- Subgroup analysis present is **view only**: PA micro-AUROC 0.807 (185 img), AP 0.784 (115 img)
  (`behavior_card.json:2895-2908`). **No site, scanner, sex, age, ethnicity, or pediatric strata.**
- Per-pathology AUROC ranges 0.906 (Cardiomegaly) down to **0.458 Pneumonia (sensitivity 0.0, only
  2 positives)** (`behavior_card.json:644-650`); 9 of 14 evaluable labels carry `"reliable": false`
  (too few positives). Hernia has 0 positives → not evaluable (`behavior_card.json:1385-1392`).
- Localization vs NIH boxes: **51 boxes total**, hit-rate 0.0 for Atelectasis and Pneumonia, best
  0.6 / IoU 0.129 Cardiomegaly (`behavior_card.json:1394-1433`).
- **No confidence intervals anywhere in the card.** The JSON contains point estimates only; there is
  no CI field, no bootstrap, no p-value. **[ABSENT]**

**Regulatory read of that substrate:** this is a legitimate *engineering* verification artifact and
is honestly labeled as such, but it satisfies **none** of the pillars of a clinical-performance
submission: it is single-site, single-dataset, has no CIs, no prespecified acceptance criteria, no
demographic subgroups, and n is far too small (single-digit positives for the safety-critical
labels). A device claim cannot be built on it; it can only seed the test *design*.

---

## 2. Device classification — what RadAssist would be if the intended use were clinical

`INTENDED-USE.md:27-35` already names the classifications correctly. Restated and completed:

| RadAssist function | US FDA device type | Reg. / product code | Class | Typical pathway |
|---|---|---|---|---|
| CXR finding probabilities + heatmap | Radiological **CADe** (computer-assisted **detection**) | 21 CFR 892.2090 | II | 510(k), needs a predicate |
| Per-finding probability framed as disease likelihood | Radiological **CADx** (**diagnosis/characterization**) | 21 CFR 892.2060/2070 | II–III | 510(k) or De Novo |
| Priority-review triage banner (`services/triage.py`) | Radiological **CADt** (computer-assisted **triage**) | 21 CFR 892.2080 (product code QFM/QAS) | II | De Novo established the type; now 510(k) |
| CT/MRI research CADe (`detect.py`) | CADe (CT) | 21 CFR 892.2090 | II | 510(k) / De Novo |
| CT/MRI anatomy overlay (non-diagnostic labeling/measurement) | Image-processing / quantitative imaging | 21 CFR 892.2050 | II | 510(k) |

- **CADx is the highest-risk lane.** RadAssist deliberately avoids it: the differential list is a
  fixed human-curated textbook set, *not* patient-specific reasoning (`INTENDED-USE.md:30-32`), and
  the displayed number is framed "signal for review, not a diagnosis." **[RECOMMENDATION]** Keep this
  wall; a per-patient diagnostic claim would push the CXR path from CADe (II) toward CADx (II/III) and
  materially raise the evidence bar.
- **IMDRF SaMD risk category:** intended use "drives clinical management" of a **serious** condition
  (e.g., pneumothorax, effusion) → **IMDRF Category III–IV** — one of the higher SaMD risk tiers,
  which sets the expectation for independent multi-site clinical validation.
- **EU parallel:** MDR 2017/745 Rule 11 → **Class IIa or higher** (`INTENDED-USE.md:29`). Notified-body
  review, not self-certification.
- **CADt special controls** (the triage banner) additionally require: a defined time-to-notification
  claim, a measured **AFROC/localization** endpoint, and explicit labeling that it does **not** remove
  images from the queue or replace the standard-of-care read.

---

## 3. Intended Use / Indications for Use framing a submission would need

The current `INTENDED-USE.md` is a *non-clinical demonstration* statement — correct for the prototype
and it should stay for the demo. A cleared device needs a **new, clinical** Indications for Use (IFU)
that is deliberately narrow. Illustrative target IFU **[RECOMMENDATION]**:

> "RadAssist-CXR is a computer-assisted **detection** software device intended to assist appropriately
> trained radiologists in the identification of {defined finding set, e.g., pleural effusion,
> pneumothorax} on **frontal (PA/AP) chest radiographs of adults ≥ {age}** acquired on {stated
> detector types}. It is an **adjunct/concurrent-read** aid; it does not replace the radiologist's
> review of the full image, provides no output on lateral/pediatric/portable-outside-spec images, and
> is not intended as a stand-alone diagnostic, screening, or triage-notification device."

IFU discipline that the data forces:
- **Views:** claim **PA/AP frontal only.** Lateral is force-down-weighted and never validated
  (`inv_safety.md:48-49`); it must be an explicit **contraindication/exclusion**, not a silent degrade.
- **Finding set:** claim only labels with a defensible, adequately-powered operating point. On current
  data that is a *short* list (Effusion, Atelectasis, Consolidation are `reliable:true`; Cardiomegaly
  AUROC is high but `reliable:false` at 16 positives). **Pneumonia and Nodule cannot be claimed**
  (Pneumonia AUROC 0.458/sens 0.0; Nodule 0.626) and should be **excluded from the IFU or removed from
  the device**, not merely "shown with a caution chip" (`inv_safety.md:164-166`).
- **Population:** adults; **pediatric is out of scope** until separately validated (no pediatric data
  on-repo).
- **Adjunct vs autonomous:** claim **concurrent/second-reader adjunct**; the human-in-the-loop review
  gate (`INTENDED-USE.md:16-19`) is the core risk control and must be a labeled condition of use.
- **"No-flag ≠ normal":** the device must **not** state or imply a normal read. This is the single most
  important labeling control given the omission risk in §5 and `inv_safety.md:117-124`.

---

## 4. External, multi-site validation datasets required — and why

**[MEASURED]** on-repo: only NIH ChestX-ray14 (the training-adjacent dataset). MIMIC/CheXpert/Open-i
were *deliberately excluded* for license reasons (`inv_backend.md:92`), which is fine for a public demo
but means **the model has never been tested on data independent of its training distribution.** FDA
clinical-validation norms and GMLP Principle 6 ("independent test sets") require test data that is
(a) **independent of training**, (b) **multi-site/multi-scanner**, and (c) **representative of the
intended-use population**. Required set **[RECOMMENDATION]**:

| Dataset | Role in the submission | Why it is needed |
|---|---|---|
| **MIMIC-CXR** (Beth Israel, US) | Primary external standalone test | Large, different institution/scanner mix than NIH; pairs with reports for label QA. |
| **CheXpert** (Stanford, US) | Second external site | Different labeler + uncertainty labels; tests cross-institution generalization. |
| **PadChest** (Spain) | Geographic/scanner shift | Non-US population and equipment → probes the AP/PA acquisition-shift already visible (0.807 vs 0.784). |
| **VinDr-CXR** (Vietnam) | Geographic shift **+ radiologist bounding boxes** | Independent expert boxes → the *localization / pointing-game / AFROC* endpoint the CADt/CADe claim needs. |
| **RSNA Pneumonia** | Pixel-level truth, critical label | Pneumonia is below-chance on-repo; a real claim needs an adequately-powered, box-annotated set. |
| **SIIM-ACR Pneumothorax** | Pixel-level truth, critical label | Pneumothorax is safety-critical (tension PTX); needs enriched positives + segmentation truth. |
| **Curated OOD / negative-control set** | Abstain-gate validation (§7) | Non-chest radiographs (knee/hand/abdomen), CT/MR-as-PNG, photos, screenshots, inverted/rotated/lateral/pediatric CXR — to measure the abstain classifier as a first-class detector. |
| **Prospective enriched-normal set** | NPV of the no-flag state at real prevalence | The omission-safety claim (§5) cannot be made on test-set prevalence. |

Rationale in one line: **you cannot generalize a claim beyond the distribution you tested, and today
that distribution is one dataset from one hospital.** Each external site also lets you measure — and
then *recalibrate* — the ECE that is currently 0.2437.

---

## 5. Standalone performance metrics, CIs, and subgroup analyses required

**[ABSENT]** today: confidence intervals, prespecified acceptance criteria, clinical-prevalence
PPV/NPV, and every demographic subgroup. Required standalone analysis **[RECOMMENDATION]**:

**5a. Per-label operating characteristics, each with a 95% CI, on each external site:**
- AUROC + AUPRC (bootstrap CI, e.g. 2000 resamples).
- **Sensitivity & specificity at a *prespecified* operating point** (chosen *before* the test unlocks),
  with CIs.
- **PPV/NPV at realistic clinical prevalence** — *not* test-set prevalence. This is decisive: at ~1–3%
  pneumothorax prevalence, even 0.62 specificity produces a false-positive stream that dominates the
  flags.
- Illustrative power reality (NOT a measured CI): Effusion on-repo is 31 pos / 269 neg; a Hanley-McNeil
  ballpark on AUROC 0.839 at that n is roughly ±0.05–0.07 — **wide**, and this is the *best*-powered
  label. Pneumothorax (9 pos) and Pneumonia (2 pos) yield CIs so wide the point estimate is
  uninformative. This is why external, enriched, adequately-powered sets are mandatory, and why a
  **prospective sample-size / power calculation per label** must precede data collection.

**5b. Prespecified acceptance criteria (the thing that makes it a *study*, not a measurement):**
- e.g., "per-label AUROC lower 95% CI bound ≥ 0.80 on each external site," "sensitivity ≥ X at the
  locked operating point," "ECE ≤ 0.05 per site after recalibration." None exist on-repo. **[ABSENT]**

**5c. Subgroup / fairness analysis (GMLP Principle 3; FDA subgroup expectation):**
- Stratify **every** metric by: view (PA/AP/lateral), **site, scanner/detector make, sex, age band,
  body habitus, pediatric-vs-adult**, and disease severity. On-repo, only **view** exists
  (`behavior_card.json:2895-2908`); the aggregate already hides a PA/AP gap. Require a **prespecified
  minimum per-subgroup performance** (no subgroup collapse) as a release gate.

**5d. Localization endpoint:**
- Pointing-game hit-rate + IoU / **AFROC** vs expert boxes (VinDr/RSNA/SIIM). On-repo it is 51 boxes
  with 0.0 hit-rate on two labels (`behavior_card.json:1394-1433`) — far below any device claim; the
  heatmap must stay labeled "region of model attention, not a lesion boundary"
  (`KNOWN-LIMITATIONS.md:11-13`) unless separately validated as localization.

---

## 6. MRMC reader study design (the pivotal clinical study)

Standalone numbers are necessary but **not sufficient** for a CADe/CADt claim; FDA expects a
**Multi-Reader Multi-Case (MRMC)** study proving *clinician-with-AI beats clinician-alone*.
**[ABSENT]** on-repo; **[RECOMMENDATION]** design:

- **Design:** fully-crossed MRMC, **ROC (or AFROC for localized findings)**, **sequential or
  independent** reader paradigm; RadAssist positioned as **concurrent/second-reader adjunct**.
- **Readers:** ≥ 10–15 board-certified radiologists spanning experience levels; each reads every case
  both **unaided** and **aided** (crossover, with washout to prevent memory bias).
- **Cases:** independent multi-site enriched set (§4), stratified across the claimed finding set,
  severities, and the demographic subgroups; sample size from an **MRMC power analysis**
  (e.g., OR-DBM / Hillis) sized to detect the target ΔAUC with the observed reader+case variance.
- **Primary endpoint:** difference in **reader-averaged AUC (or AFROC FOM)**, aided − unaided; success
  = lower 95% CI bound > 0 (superiority) or within a prespecified non-inferiority margin on the
  co-primary the claim targets.
- **Secondary:** sensitivity/specificity change per finding, **reading time** (for a triage/efficiency
  claim), localization accuracy, inter-reader variability, and **automation-bias / over-reliance**
  probes (does the AI cause readers to *miss* findings it didn't flag — directly ties to the omission
  risk in §5).
- **Truthing:** independent expert panel with adjudication, blinded to the AI, ideally with a
  composite reference standard (follow-up/CT/path where available).

For the **CADt (triage) claim** specifically: add a **time-to-notification** endpoint and a
**workflow simulation** showing worklist reprioritization improves time-to-read for true positives
without harming the queue — plus labeling that the tool does not remove cases from the standard read.

---

## 7. Calibration & abstention as first-class, validated components

**7a. Calibration.** **[MEASURED]** ECE 0.2437 (`behavior_card.json:1439`); an isotonic map ships
(`validation/calibration_map.json`, `services/calibration.py`) and the device correctly separates raw
`probability` (drives flags) from `calibrated_probability` (display/triage) so calibration can never
silently move a flag (`inv_backend.md:49,53`). **[RECOMMENDATION]** Refit and **re-measure ECE/MCE per
site and per subgroup**, target a prespecified ceiling (e.g. ECE ≤ 0.05), and prove it holds
out-of-sample; version the calibration map in the provenance panel (Roadmap A3).

**7b. Abstention (the core "abstain over guess" proof).** The self-audit OOD gate exists and is
principled (AE reconstruction + synthetic detector + color + heuristics; only reliable signals hard-
abstain — `inv_safety.md:19-45`), but **its thresholds are hand-set and unvalidated**
(`inv_safety.md:141-146`): `OOD_ABSTAIN_THRESHOLD`, `AE_ERR_*`, `ANATOMY_MIN_OVERLAP`, `ATTENTION_BG_*`,
`PRIORITY_MIN_CALIBRATED_P` have **no measured ROC / operating point**. **[RECOMMENDATION]** treat the
gate as a binary classifier and measure, with CIs, on the §4 OOD set:
- **Catch rate** (true OOD correctly abstained) and **over-abstain rate** (real CXR wrongly refused) —
  choose the threshold at a prespecified operating point (e.g. ≥ 0.99 catch on hard-OOD at ≤ 1%
  over-abstain).
- **Selective-prediction / risk–coverage curves** (scaffolded on-repo: `validation/risk_coverage.py`):
  prove **selective risk on the answered set ≤ a pre-registered bound.** This is the formal statement of
  "when it answers, its error is bounded; otherwise it abstains."
- Do the same tradeoff curve for every gate constant, and **add the missing anatomy-gate FN/FP section
  to the behavior card** — the anatomy gate defaults to *deleting* findings and its false-negative cost
  is currently unmeasured (`inv_safety.md:147-156`); a safety layer that can remove a true finding must
  itself be validated.

**7c. Proving the negative claim — "even when it cannot identify disease, it never emits an incorrect
diagnosis."** Decomposes into three *measurable* guarantees (from `inv_safety.md:224-241`), and this is
the team's north-star deliverable:
1. **Two-sided specificity of the abstain path** (catch OOD; do not over-refuse real CXR) — §7b.
2. **Safety of the no-flag path.** The CXR path makes **no explicit normal call** and, unlike the CADe
   panel, shows **no "this is not a normal read" message** on zero flags (`inv_safety.md:117-124`).
   Given real low sensitivity (Pneumonia sens 0.0, Edema 0.2, Cardiomegaly 0.625), *missed disease →
   no flag → user infers normal* is the **single largest incorrect-diagnosis-by-omission risk.** The
   claim reduces to: (a) publish the **NPV of the no-flag state at realistic prevalence**; (b) select
   **high-sensitivity operating points** on critical labels; (c) surface an explicit "NOT a normal read"
   non-claim in the UI. The guarantee is provable as "the device does not *assert* normal," backed by
   the NPV number and the absence of any normal assertion.
3. **False-positive / over-confidence control.** The flag fires on the **raw score at 0.5, a band that
   is only ~8.2% true-positive** (`behavior_card.json:1491-1495`, `inv_safety.md:126-131`). A defensible
   device sets the **flag threshold from calibrated P at a chosen operating point**, with a measured
   alert-burden (findings-per-normal-film) target.

---

## 8. Quality System, software lifecycle, and risk management (the process gaps)

A submission is as much *process* as *performance*. On-repo, none of the formal lifecycle artifacts
exist; `INTENDED-USE.md:37-40` acknowledges this ("would need to be revisited under IEC 62304 … and
ISO 14971"). Required **[ABSENT / RECOMMENDATION]**:

- **QMS — 21 CFR 820 QSR → QMSR** (the FDA rule harmonizing with **ISO 13485**, effective **Feb 2026**):
  design controls, DHF, document/version control, CAPA, supplier controls (incl. the **pretrained
  TorchXRayVision weights and OSS licenses** as a supplier/SOUP-management item). **[ABSENT]**
- **IEC 62304 — software lifecycle:** software **safety classification** (this is plausibly **Class C**
  — a failure could contribute to serious injury via a missed critical finding), development plan,
  SRS/SDS, unit/integration/system verification traceability, and **SOUP management** (PyTorch,
  TorchXRayVision, scipy/numpy, FastAPI must be inventoried, version-pinned, and monitored for known
  anomalies). On-repo there is a strong **test suite (197 tests per memory index)** and multiple
  validation scripts, but **no 62304 lifecycle documentation, no safety classification, no SOUP list.**
- **ISO 14971 — risk management file:** a hazard analysis mapping each failure mode to a mitigation and
  residual-risk judgment. The two inventories (`inv_safety.md §2`, this doc §5/§7) are effectively a
  **pre-hazard-analysis** and are a good seed, but the formal RMF, risk-acceptability criteria, and
  benefit-risk determination are **[ABSENT]**. Highest-priority hazards to enter: (H1) missed critical
  finding read as normal; (H2) over-confident false-positive flood; (H3) mis-calibrated triage banner;
  (H4) OOD/wrong-modality image scored (mitigated by modality routing + abstain, but gate unvalidated);
  (H5) anatomy gate deleting a true finding; (H6) enabling CT/MRI research CADe in a clinical context.
- **Cybersecurity / privacy:** the demo explicitly has **no PHI handling by default**
  (`KNOWN-LIMITATIONS.md:44-46`), though the codebase *does* contain de-ID, quarantine, auth, idle
  logoff, audit logging, and security headers (`inv_backend.md §4`). A clinical build needs the FDA
  premarket cybersecurity documentation (SBOM, threat model, SPDF) and a HIPAA-grade deployment — the
  security primitives exist but are **default-off and uncertified.**

---

## 9. Predetermined Change Control Plan (PCCP) & post-market surveillance

An ML device that will be updated needs a **PCCP** (FDA final guidance, Dec 2024) authorized *in the
submission* so that prespecified changes don't require a new 510(k). RadAssist already has the two
mechanisms a PCCP is built around, which is a genuine strength:

- **[MEASURED]** a **feedback loop**: `POST /api/feedback` + `refit_from_feedback.py` turns reviewer
  confirm/dismiss into proposed per-label threshold changes (`inv_backend.md:26-27`, Roadmap A1).
- **[MEASURED]** a **calibration-map + behavior-card versioning** seam and a provenance panel plan
  (Roadmap A3), plus the harness that regenerates the card.

**[RECOMMENDATION]** Formalize these into a PCCP with the three FDA-required components:
1. **Description of Modifications** — e.g., periodic recalibration, per-label threshold refits from the
   feedback loop, site-specific calibration maps. **Locked model architecture** unless a new submission.
2. **Modification Protocol** — the exact data, retraining/refit procedure, the **frozen acceptance
   criteria** (§5b), and the verification each change must pass **before** deployment, with **human
   review before any threshold change** (already the stated design — `inv_safety.md:252-256`).
3. **Impact Assessment** — benefit-risk of each allowed change, and rollback.

**Post-market surveillance [RECOMMENDATION]:** continuous monitoring of **drift** (input distribution,
score distribution), **abstain-rate**, **per-subgroup performance**, alert-burden, and the
confirm/dismiss stream; complaint handling and **MDR/MDV adverse-event reporting**; a periodic
real-world-performance re-audit. The dashboards are named in Roadmap Phase D but are **[ABSENT]** today.

---

## 10. GMLP (FDA/Health Canada/MHRA 10 principles) — quick conformance read

| # | GMLP principle | RadAssist today |
|---|---|---|
| 1 | Multidisciplinary expertise across lifecycle | Partial — engineering strong; no documented clinical/regulatory sign-off. |
| 2 | Good software eng. & security practices | **Partial-strong** — tests, security middleware, de-ID exist (`inv_backend.md §4`); no 62304 QMS. |
| 3 | Clinical-study participants & data representative of intended population | **Gap** — single-site NIH only; no demographic representativeness. |
| 4 | Training data independent of test data | **Gap** — test set is training-adjacent (NIH); no independent external test. |
| 5 | Selected reference datasets are well-characterized | Partial — NIH labels are known-noisy; no expert-adjudicated truth. |
| 6 | Model design tailored to data & intended use | Partial — off-the-shelf pretrained model, not designed for a locked IFU. |
| 7 | Human-AI team performance (not model alone) | **Gap** — no MRMC reader study (§6). |
| 8 | Testing under clinically relevant conditions | **Gap** — no prospective/multi-site testing; robustness only n=8 (`validation/perturbation_stats.json`). |
| 9 | Clear, essential info to users | **Strong** — honest disclaimers, calibrated-vs-raw, "not a diagnosis", known-limitations doc. |
| 10 | Monitored deployment with retraining risk-managed | Partial — feedback loop + refit exist; no monitoring dashboards or PCCP. |

Net: RadAssist is unusually strong on **principles 2 and 9** (engineering honesty, transparent
labeling) and weak on the **clinical-evidence principles 3, 4, 7, 8** — exactly the pillars that
require money, sites, and time rather than code.

---

## 11. Prioritized, honest gap list (on-repo vs missing)

Ranked by what most blocks a submission. "Exists" = concretely on-repo; "Missing" = **[ABSENT]**.

| # | Gap | Exists on-repo | Missing (blocker) |
|---|---|---|---|
| 1 | **Independent multi-site clinical validation** | NIH-only sanity card (`behavior_card.json`) | MIMIC/CheXpert/PadChest/VinDr/RSNA/SIIM external test; **the #1 blocker.** |
| 2 | **MRMC reader study** (human-with-AI) | Nothing | Full crossed MRMC design, readers, powered case set (§6). |
| 3 | **Confidence intervals + prespecified acceptance criteria** | Point estimates only | Bootstrap CIs, power analysis, frozen pass/fail gates (§5). |
| 4 | **Demographic/site/scanner subgroups** | View-only (PA/AP) | Sex/age/site/scanner/pediatric strata + no-collapse gate (§5c). |
| 5 | **Omission-safety / no-flag NPV + "not a normal read" UI** | CADe panel already shows non-normal msg; CXR does not (`inv_safety.md:117-124`) | Measured NPV at real prevalence; UI non-claim on the CXR path. |
| 6 | **Validated abstain gate + gate constants** | Working gate; `risk_coverage.py`, `decision_curve.py`, `pointing_game.py`, `perturbation_stability.py`, `anatomy_gate_audit.py`, `cam_divergence.py` scaffolds | Measured ROC/risk-coverage with CIs; anatomy-gate FN/FP in the card (§7). |
| 7 | **Recalibration to ECE ceiling per site** | Isotonic map + ECE 0.2437 measured | Per-site/subgroup refit proving a prespecified ceiling (§7a). |
| 8 | **Drop or exclude unclaimable labels** | Kept-with-caution (Pneumonia 0.458, Nodule 0.626) | IFU that excludes them, or removal from device (§3). |
| 9 | **ISO 14971 risk management file** | Two inventories = pre-hazard analysis | Formal RMF, hazard-mitigation traceability, benefit-risk (§8). |
| 10 | **IEC 62304 lifecycle + software safety class + SOUP list** | 197-test suite, structured code | 62304 docs, Class C classification, SOUP/OSS inventory (§8). |
| 11 | **QMS (21 CFR 820 / QMSR-ISO 13485)** | Ad-hoc | Design controls, DHF, CAPA, supplier controls (§8). |
| 12 | **PCCP + post-market monitoring** | Feedback loop + refit + card versioning (`refit_from_feedback.py`) | Authorized PCCP, drift/subgroup dashboards, MDR reporting (§9). |
| 13 | **Clinical IFU + predicate/De Novo strategy** | Non-clinical demo IFU (`INTENDED-USE.md`) | Narrow clinical IFU, predicate identification, pre-submission (Q-Sub) (§3). |
| 14 | **Robustness at scale** | Perturbation stability but **n=8 images** (`perturbation_stats.json`) | Adequately-powered test-retest/perturbation across the external sets (§5/§8). |
| 15 | **Cybersecurity/privacy premarket package** | Security middleware, de-ID, audit, idle-logoff (all default-off) | SBOM, threat model, SPDF, HIPAA-grade certified deployment (§8). |
| 16 | **CT/MRI channels** | Model-free viewer + opt-in unvalidated research CADe (default OFF, hard disclaimers) | **No measured accuracy exists** for CT/MRI; entirely research — keep default-off and out of any clinical claim. |

---

## 12. Bottom line

RadAssist is a **research prototype, not an FDA-cleared device**, and it says so itself. Its
distinguishing strength for a *future* regulatory path is **process honesty**: transparent
measured-vs-unvalidated labeling, calibrated-vs-raw separation, an abstain gate, a feedback/refit loop,
a real (if small, single-site) validation harness, and several validation *scaffolds*
(`risk_coverage.py`, `decision_curve.py`, `pointing_game.py`, `anatomy_gate_audit.py`) already on-repo.
The gaps that remain are the expensive, non-code ones — **independent multi-site clinical validation
with CIs and subgroups, an MRMC reader study, a formal ISO 14971 / IEC 62304 / QMS lifecycle, and an
authorized PCCP with post-market surveillance** — plus one product-safety fix that *is* code and *is*
the team's north star: turning the silent "no-flag" CXR state into an explicit, NPV-backed
"this is NOT a normal read" non-claim, so that even when the model cannot identify disease it never
asserts an incorrect one.

---

*Prepared by the RadAssist ACCURACY + SAFETY research team — regulatory GAP analysis, read-only.
Every quantitative figure is traceable to `validation/behavior_card.json` or a cited repo file; no
metric was invented. This is not regulatory advice and not a substitute for a Q-Submission to FDA.*
