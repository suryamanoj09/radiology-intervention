# RadAssist — FDA / Regulatory Readiness Roadmap

**Prepared by the RadAssist ACCURACY + SAFETY research team.** Synthesis of `docs/research/05_fda_readiness.md`
and the supporting accuracy/calibration/abstain/CT-MRI analyses, grounded in the measured behavior card
`backend/validation/behavior_card.json` and the shipped governance docs (`INTENDED-USE.md`,
`KNOWN-LIMITATIONS.md`).

> ## ⚠️ Regulatory status header (not opinion — fact)
> **RadAssist is a research / portfolio prototype. It is NOT an FDA-cleared, FDA-registered, or
> CE-marked medical device, and must not be used for clinical decision-making.** Its own governance says
> so: `INTENDED-USE.md:24-25` ("not a regulated medical device today"), `KNOWN-LIMITATIONS.md:9`
> ("Research-grade, not FDA-cleared"). This roadmap measures the distance between that prototype and a
> clearable device. It does **not** claim the device is close to clearance, and it is **not a substitute
> for a Q-Submission to FDA or for regulatory counsel.**

Findings are tagged **[MEASURED]** (read from repo/card), **[ABSENT]** (a required artifact that does not
exist on-repo), or **[RECOMMENDATION]**. No metric is invented.

---

## 1. Where the ground truth stands today

**[MEASURED]** The only quantitative performance evidence on-repo is `validation/behavior_card.json`
(served at `GET /api/behavior-card`), produced by `run_validation.py`:

- Model `densenet121-res224-all`, flag threshold 0.5, **300 images**, calibration over **4,200
  label-instances**, 10 bins. Data provenance: **NIH ChestX-ray14 sample + BBox_List_2017 — a single
  public dataset, single institution (NIH Clinical Center), retrospective, training-adjacent.**
- The card's own caveat: *"Engineering sanity check … NOT clinical validation … in-distribution and
  optimistic."*
- Overall **ECE = 0.2437** (severe miscalibration; the 0.5–0.6 band holds 1,480 instances at conf 0.523
  but 8.2% observed positive).
- Subgroup analysis is **view only**: PA 0.807 (185 img), AP 0.784 (115 img). **No site, scanner, sex,
  age, ethnicity, or pediatric strata.**
- Per-label AUROC 0.906 (Cardiomegaly) down to **0.458 Pneumonia (sens 0.0, 2 positives)**; **9 of 14**
  evaluable labels are `"reliable": false`. Hernia not evaluable (0 positives).
- Localization: 51 boxes total, hit-rate 0.0 for Atelectasis and Pneumonia.
- **No confidence intervals anywhere** — point estimates only, no bootstrap, no p-values. **[ABSENT]**

**Regulatory read:** a legitimate *engineering verification* artifact, honestly labeled, but it satisfies
**none** of the pillars of a clinical-performance submission: single-site, single-dataset, no CIs, no
prespecified acceptance criteria, no demographic subgroups, and n far too small (single-digit positives
for the safety-critical labels). It can only seed the test *design*, not support a device claim. For CT/MRI
there is **no measured accuracy at all** — those numbers do not exist.

---

## 2. Device classification (if the intended use were clinical)

| RadAssist function | FDA device type | Reg. / product code | Class | Pathway |
|---|---|---|---|---|
| CXR finding probabilities + heatmap | Radiological **CADe** (detection) | 21 CFR 892.2090 | II | 510(k), needs predicate |
| Per-finding probability as disease likelihood | Radiological **CADx** (diagnosis) | 21 CFR 892.2060/2070 | II–III | 510(k) / De Novo |
| Priority triage banner (`triage.py`) | Radiological **CADt** (triage) | 21 CFR 892.2080 (QFM/QAS) | II | 510(k) (De Novo established type) |
| CT/MRI research CADe (`detect.py`) | CADe (CT) | 21 CFR 892.2090 | II | 510(k) / De Novo |
| CT/MRI anatomy overlay (measurement) | Image-processing / QIB | 21 CFR 892.2050 | II | 510(k) |

- **Keep the CADx wall.** RadAssist deliberately avoids per-patient diagnostic reasoning: the differential
  list is a fixed human-curated textbook set, not patient-specific (`INTENDED-USE.md:30-32`), and the
  number is framed "signal for review." A per-patient diagnostic claim would push CXR from CADe (II)
  toward CADx (II/III) and materially raise the evidence bar. **[RECOMMENDATION]**
- **IMDRF SaMD risk:** intended use drives clinical management of a *serious* condition (pneumothorax,
  effusion) → **Category III–IV**, one of the higher tiers → expectation of independent multi-site
  clinical validation.
- **EU parallel:** MDR 2017/745 Rule 11 → Class IIa+ (notified-body review, not self-certification).
- **CADt special controls** (triage banner) additionally require a defined time-to-notification claim, a
  measured **AFROC/localization** endpoint, and labeling that it does not remove images from the queue or
  replace the standard read.

---

## 3. Intended Use / Indications for Use a submission would need

The current `INTENDED-USE.md` is a *non-clinical demonstration* statement — correct for the prototype and
it should stay for the demo. A cleared device needs a **new, deliberately narrow clinical IFU.**
Illustrative target **[RECOMMENDATION]**:

> "RadAssist-CXR is a computer-assisted **detection** device intended to assist appropriately trained
> radiologists in the identification of {defined finding set, e.g. pleural effusion, pneumothorax} on
> **frontal (PA/AP) chest radiographs of adults ≥ {age}** acquired on {stated detector types}. It is an
> **adjunct/concurrent-read** aid; it does not replace the radiologist's review of the full image,
> provides no output on lateral/pediatric/portable-outside-spec images, and is not a stand-alone
> diagnostic, screening, or triage-notification device."

IFU discipline the data forces:

- **Views:** claim **PA/AP frontal only.** Lateral is a labeled **contraindication/exclusion**, not a
  silent degrade.
- **Finding set:** claim only adequately-powered labels. On current data that is a *short* list
  (Effusion, Atelectasis, Consolidation are `reliable:true`; Cardiomegaly AUROC is high but `reliable:false`
  at 16 positives). **Pneumonia (AUROC 0.458/sens 0.0) and Nodule (0.626) cannot be claimed** — exclude
  from the IFU or remove from the device, not "shown with a caution chip."
- **Population:** adults; **pediatric out of scope** until separately validated (no pediatric data on-repo).
- **Adjunct vs autonomous:** claim **concurrent/second-reader adjunct**; the human-in-the-loop review gate
  is the core risk control and a labeled condition of use.
- **"No-flag ≠ normal":** the device must **not** state or imply a normal read — the single most important
  labeling control (see §7c and `ACCURACY_AND_SAFETY.md` fix #1).

---

## 4. External, multi-site validation datasets required

**[MEASURED]** on-repo: only NIH ChestX-ray14 (training-adjacent). MIMIC/CheXpert/Open-i were *deliberately
excluded* for license reasons — fine for a public demo, but it means **the model has never been tested on
data independent of its training distribution.** FDA norms + GMLP Principle 6 require test data that is
independent of training, multi-site/multi-scanner, and representative of the intended-use population.

| Dataset | Role | Why needed |
|---|---|---|
| **MIMIC-CXR** (Beth Israel, US) | Primary external standalone test | Different institution/scanner mix; report-paired label QA. |
| **CheXpert** (Stanford, US) | Second external site | Different labeler + uncertainty labels; cross-institution generalization. |
| **PadChest** (Spain) | Geographic/scanner shift | Non-US population/equipment; probes the AP/PA shift (0.807 vs 0.784). |
| **VinDr-CXR** (Vietnam) | Geographic shift **+ radiologist boxes** | Independent expert boxes → the localization / AFROC endpoint. |
| **RSNA Pneumonia** | Pixel truth, critical label | Pneumonia is below-chance on-repo; needs a powered, box-annotated set. |
| **SIIM-ACR Pneumothorax** | Pixel truth, critical label | Safety-critical (tension PTX); enriched positives + segmentation truth. |
| **Curated OOD / negative-control set** | Abstain-gate validation (§7b) | Non-chest radiographs, CT/MR-as-PNG, photos, screenshots, inverted/rotated/lateral/pediatric — DICOM and PNG-stripped. |
| **Prospective enriched-normal set** | NPV of the no-flag state at real prevalence | The omission-safety claim cannot be made on test-set prevalence. |

For CT/MRI a real claim would require lesion-annotated multi-site sets per detector kind (LIDC-IDRI/LUNA16
for nodules, RSNA-ICH/CQ500 for haemorrhage, annotated effusion/pneumothorax CT, BraTS-style MR) with
**FROC/CPM** analysis — not the CXR AUROC apparatus. None has been run.

---

## 5. Standalone metrics, CIs, and subgroup analyses required

**[ABSENT]** today: confidence intervals, prespecified acceptance criteria, clinical-prevalence PPV/NPV,
and every demographic subgroup. Required **[RECOMMENDATION]**:

- **5a. Per-label operating characteristics with 95% CI on each external site:** AUROC + AUPRC (bootstrap,
  e.g. 2000 resamples); **sensitivity & specificity at a *prespecified* operating point** (locked before
  the test unlocks), with CIs; **PPV/NPV at realistic clinical prevalence**, not test-set prevalence. Power
  reality: Effusion (best-powered, 31 pos) already implies a ±0.05–0.07 AUROC CI; Pneumothorax (9) and
  Pneumonia (2) are uninformative → a **per-label power/sample-size calculation must precede collection.**
- **5b. Prespecified acceptance criteria** (what makes it a *study* not a measurement): e.g. "per-label
  AUROC lower 95% CI ≥ 0.80 on each external site," "sensitivity ≥ X at the locked operating point,"
  "ECE ≤ 0.05 per site after recalibration." **None exist on-repo. [ABSENT]**
- **5c. Subgroup / fairness (GMLP Principle 3):** stratify **every** metric by view, **site, scanner make,
  sex, age band, body habitus, pediatric-vs-adult**, severity. On-repo only **view** exists; require a
  prespecified minimum per-subgroup performance (no subgroup collapse) as a release gate.
- **5d. Localization endpoint:** pointing-game hit-rate + IoU / **AFROC** vs expert boxes. On-repo 51 boxes
  with 0.0 hit-rate on two labels — far below a device claim; the heatmap stays labeled "region of
  attention, not a lesion boundary" unless separately validated.

---

## 6. MRMC reader study (the pivotal clinical study)

Standalone numbers are necessary but **not sufficient** for a CADe/CADt claim; FDA expects a
**Multi-Reader Multi-Case** study proving *clinician-with-AI beats clinician-alone*. **[ABSENT]**;
**[RECOMMENDATION]** design:

- **Design:** fully-crossed MRMC, **ROC (or AFROC** for localized findings), RadAssist as
  **concurrent/second-reader adjunct**.
- **Readers:** ≥ 10–15 board-certified radiologists across experience levels; each reads every case both
  **unaided** and **aided** (crossover, with washout).
- **Cases:** independent multi-site enriched set (§4), stratified across the claimed findings, severities,
  and demographic subgroups; sample size from an **MRMC power analysis** (OR-DBM / Hillis) sized to the
  target ΔAUC.
- **Primary endpoint:** reader-averaged ΔAUC (or AFROC FOM), aided − unaided; success = lower 95% CI > 0
  (or within a prespecified non-inferiority margin).
- **Secondary:** per-finding sens/spec change, **reading time** (triage/efficiency claim), localization
  accuracy, inter-reader variability, and **automation-bias / over-reliance** probes — does the AI cause
  readers to miss findings it didn't flag (ties directly to the omission risk in §7c).
- **Truthing:** independent adjudicated expert panel blinded to the AI; composite reference standard
  (follow-up/CT/path) where available.
- **CADt specifically:** add a **time-to-notification** endpoint and a worklist-simulation showing
  reprioritization improves time-to-read for true positives without harming the queue.

---

## 7. Calibration & abstention as validated components

**7a. Calibration.** **[MEASURED]** ECE 0.2437; an isotonic map ships and the device correctly separates
raw `probability` (flags) from `calibrated_probability` (display/triage) so calibration can never silently
move a flag. **[RECOMMENDATION]** refit and re-measure **ECE/MCE per site and per subgroup**, target a
prespecified ceiling (e.g. ECE ≤ 0.05), prove it holds out-of-sample, and version the map in a provenance
panel. Also fix the sparse-support isotonic tails that can snap Pneumothorax calibrated P to 1.0 and
manufacture a false urgent banner (clamp triage P ≤ 0.90; minimum knot support; Platt/beta on sparse labels).

**7b. Abstention (the core "abstain over guess" proof).** The OOD gate exists and is principled but its
thresholds (`OOD_ABSTAIN_THRESHOLD`, `AE_ERR_*`, `ANATOMY_MIN_OVERLAP`, `ATTENTION_BG_*`,
`PRIORITY_MIN_CALIBRATED_P`) are **hand-set and unvalidated** — no measured ROC. **[RECOMMENDATION]** treat
the gate as a binary classifier and measure, with CIs, on the §4 OOD set: **catch rate** (true OOD
abstained) and **over-abstain rate** (real CXR wrongly refused), choosing the threshold at a prespecified
operating point (e.g. ≥ 0.99 catch on hard-OOD at ≤ 1% over-abstain). Build **selective-prediction /
risk–coverage curves** (scaffold: `validation/risk_coverage.py`) proving **selective risk on the answered
set ≤ a pre-registered bound**. Add the missing **anatomy-gate FN/FP section** to the behavior card — a
safety layer that can *delete* a true finding must itself be validated.

**7c. Proving the negative claim** — *"even when it cannot identify disease, it never emits an incorrect
diagnosis"* — decomposes into three measurable guarantees, and this is the team's north-star deliverable:
1. **Two-sided specificity of the abstain path** (catch OOD; do not over-refuse real CXR) — §7b.
2. **Safety of the no-flag path.** The CXR path makes **no explicit normal call** and shows **no "not a
   normal read" message** on zero flags, while real sensitivity is low (Pneumonia 0.0, Edema 0.2,
   Cardiomegaly 0.625) → *missed disease → no flag → user infers normal* is the **largest
   incorrect-diagnosis-by-omission risk.** The claim reduces to (a) publish the **NPV of the no-flag state
   at realistic prevalence**, (b) select **high-sensitivity operating points** on critical labels, (c)
   surface an explicit **"NOT a normal read"** non-claim in the UI. Provable as "the device does not
   *assert* normal," backed by the NPV and the absence of any normal assertion. **This is the #1 product
   fix (WF5) in `ACCURACY_AND_SAFETY.md`.**
3. **False-positive / over-confidence control.** The flag fires on the **raw score at 0.5, a band only
   ~8.2% true-positive** → set the **flag threshold from calibrated P at a chosen operating point** with a
   measured alert-burden (flags-per-normal-film) target.

---

## 8. Quality system, software lifecycle, and risk management

A submission is as much *process* as *performance*. On-repo none of the formal lifecycle artifacts exist
(`INTENDED-USE.md:37-40` acknowledges this). Required **[ABSENT / RECOMMENDATION]**:

- **QMS — 21 CFR 820 QSR → QMSR** (harmonizing with **ISO 13485**, effective **Feb 2026**): design
  controls, DHF, document/version control, CAPA, and **supplier/SOUP controls** for the pretrained
  TorchXRayVision weights and OSS licenses. **[ABSENT]**
- **IEC 62304 — software lifecycle:** software **safety classification** (plausibly **Class C** — a failure
  could contribute to serious injury via a missed critical finding), development plan, SRS/SDS,
  verification traceability, and **SOUP management** (PyTorch, TorchXRayVision, scipy/numpy, FastAPI —
  inventoried, version-pinned, monitored). On-repo there is a strong test suite but **no 62304
  documentation, safety class, or SOUP list.**
- **ISO 14971 — risk management file:** hazard analysis mapping each failure mode to a mitigation and
  residual-risk judgment. The two inventories are effectively a **pre-hazard-analysis** seed; the formal
  RMF, risk-acceptability criteria, and benefit-risk determination are **[ABSENT]**. Highest-priority
  hazards to enter: **(H1)** missed critical finding read as normal; **(H2)** over-confident
  false-positive flood; **(H3)** mis-calibrated triage banner; **(H4)** OOD/wrong-modality image scored;
  **(H5)** anatomy gate deleting a true finding; **(H6)** enabling CT/MRI research CADe in a clinical
  context.
- **Cybersecurity / privacy:** demo has no PHI by default, but the codebase contains de-ID, quarantine,
  auth, idle logoff, audit logging, and security headers — all **default-off and uncertified.** A clinical
  build needs FDA premarket cybersecurity docs (SBOM, threat model, SPDF) and a HIPAA-grade deployment.

---

## 9. Predetermined Change Control Plan (PCCP) & post-market surveillance

An ML device that will be updated needs a **PCCP** (FDA final guidance, Dec 2024) authorized *in the
submission*. RadAssist already has the two mechanisms a PCCP is built around — a genuine strength:

- **[MEASURED]** a feedback loop: `POST /api/feedback` + `refit_from_feedback.py` turns reviewer
  confirm/dismiss into proposed per-label threshold changes.
- **[MEASURED]** a calibration-map + behavior-card versioning seam and a provenance-panel plan.

**[RECOMMENDATION]** formalize into a PCCP with the three FDA-required components: **(1) Description of
Modifications** (periodic recalibration, per-label threshold refits, site-specific maps; locked model
architecture); **(2) Modification Protocol** (exact data, refit procedure, frozen acceptance criteria
§5b, verification each change must pass, **human review before any threshold change**); **(3) Impact
Assessment** (benefit-risk of each allowed change, rollback).

**Post-market surveillance [RECOMMENDATION]:** continuous monitoring of **drift** (input/score
distribution), **abstain-rate**, **per-subgroup performance**, alert-burden, and the confirm/dismiss
stream; complaint handling and **MDR adverse-event reporting**; periodic real-world-performance re-audit.
Dashboards are planned but **[ABSENT]** today.

---

## 10. GMLP conformance (quick read)

| # | GMLP principle | RadAssist today |
|---|---|---|
| 1 | Multidisciplinary expertise | Partial — engineering strong; no documented clinical/regulatory sign-off. |
| 2 | Good SW eng. & security | **Partial-strong** — tests, security middleware, de-ID; no 62304 QMS. |
| 3 | Representative clinical data | **Gap** — single-site NIH only; no demographic representativeness. |
| 4 | Train/test independence | **Gap** — test set training-adjacent (NIH); no independent external test. |
| 5 | Well-characterized reference sets | Partial — NIH labels known-noisy; no expert-adjudicated truth. |
| 6 | Design tailored to data & use | Partial — off-the-shelf pretrained model, not designed for a locked IFU. |
| 7 | Human-AI team performance | **Gap** — no MRMC reader study. |
| 8 | Testing under clinical conditions | **Gap** — no prospective/multi-site; robustness only n=8. |
| 9 | Clear info to users | **Strong** — honest disclaimers, calibrated-vs-raw, "not a diagnosis." |
| 10 | Monitored deployment | Partial — feedback loop + refit; no monitoring dashboards or PCCP. |

Net: unusually strong on **principles 2 and 9** (engineering honesty, transparent labeling), weak on the
**clinical-evidence principles 3, 4, 7, 8** — exactly the pillars that require money, sites, and time
rather than code.

---

## 11. Prioritized gap list (on-repo vs missing)

| # | Gap | Exists on-repo | Missing (blocker) |
|---|---|---|---|
| 1 | **Independent multi-site clinical validation** | NIH-only sanity card | MIMIC/CheXpert/PadChest/VinDr/RSNA/SIIM external test — **the #1 blocker.** |
| 2 | **MRMC reader study** | Nothing | Full crossed MRMC design, readers, powered case set (§6). |
| 3 | **CIs + prespecified acceptance criteria** | Point estimates only | Bootstrap CIs, power analysis, frozen pass/fail gates (§5). |
| 4 | **Demographic/site/scanner subgroups** | View-only (PA/AP) | Sex/age/site/scanner/pediatric strata + no-collapse gate. |
| 5 | **Omission-safety: no-flag NPV + "not a normal read" UI** | CADe panel shows non-normal msg; CXR does not | Measured NPV at real prevalence; UI non-claim on the CXR path — **the one code fix that is the north star (WF5).** |
| 6 | **Validated abstain gate + gate constants** | Working gate; `risk_coverage.py` etc. scaffolds | Measured ROC/risk-coverage with CIs; anatomy-gate FN/FP in the card. |
| 7 | **Recalibration to ECE ceiling per site** | Isotonic map + ECE 0.2437 | Per-site/subgroup refit proving a prespecified ceiling. |
| 8 | **Drop or exclude unclaimable labels** | Kept-with-caution (Pneumonia, Nodule) | IFU excluding them, or removal from device. |
| 9 | **ISO 14971 risk management file** | Two inventories = pre-hazard analysis | Formal RMF, hazard-mitigation traceability, benefit-risk. |
| 10 | **IEC 62304 lifecycle + safety class + SOUP** | Test suite, structured code | 62304 docs, Class C classification, SOUP inventory. |
| 11 | **QMS (21 CFR 820 / QMSR-ISO 13485)** | Ad-hoc | Design controls, DHF, CAPA, supplier controls. |
| 12 | **PCCP + post-market monitoring** | Feedback loop + refit + card versioning | Authorized PCCP, drift/subgroup dashboards, MDR reporting. |
| 13 | **Clinical IFU + predicate/De Novo strategy** | Non-clinical demo IFU | Narrow clinical IFU, predicate ID, pre-submission (Q-Sub). |
| 14 | **Robustness at scale** | Perturbation stability but **n=8** | Powered test-retest/perturbation across external sets. |
| 15 | **Cybersecurity/privacy premarket package** | Security middleware, de-ID, audit (default-off) | SBOM, threat model, SPDF, HIPAA-grade certified deployment. |
| 16 | **CT/MRI channels** | Model-free viewer + opt-in unvalidated research CADe (default OFF, disclaimers) | **No measured accuracy exists** — keep default-off and out of any clinical claim. |

---

## 12. Bottom line

RadAssist is a **research prototype, not an FDA-cleared device**, and it says so itself. Its distinguishing
strength for a *future* regulatory path is **process honesty**: transparent measured-vs-unvalidated
labeling, calibrated-vs-raw separation, an abstain gate, a feedback/refit loop, a real (if small,
single-site) validation harness, and several validation scaffolds already on-repo. The remaining gaps are
the expensive, non-code ones — **independent multi-site clinical validation with CIs and subgroups, an
MRMC reader study, a formal ISO 14971 / IEC 62304 / QMS lifecycle, and an authorized PCCP with post-market
surveillance** — plus the one product-safety fix that *is* code and *is* the north star: turning the
silent "no-flag" CXR state into an explicit, NPV-backed **"this is NOT a normal read"** non-claim, so that
even when the model cannot identify disease it never asserts an incorrect one.

---

*Prepared by the RadAssist ACCURACY + SAFETY research team — regulatory gap analysis, read-only. Every
quantitative figure traces to `backend/validation/behavior_card.json` or a cited repo file; no metric was
invented. This is not regulatory advice and not a substitute for a Q-Submission to FDA.*
