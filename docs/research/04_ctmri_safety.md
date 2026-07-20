# 04 — CT/MRI Research-Candidate Honesty & Safety

Team: RadAssist ACCURACY + SAFETY (read-only analysis). Scope: prove or refute that the
CT/MRI channels can never emit a diagnosis or a calibrated disease probability, that every
candidate is structurally unvalidated/research-only, that disclaimers are mandatory, and
that "no candidates" is never presented as "normal". Then define what real CT/MRI
validation would require and how the upcoming WF7 CT/MRI report must stay framed.

Method: source read of `backend/app/routers/detect.py`, `models/detect.py`,
`services/ct_cade.py`, `services/mr_cade.py`, `routers/viewer.py`, `routers/segment.py`,
`config.py`, `frontend/src/components/CandidateFindings.jsx` and `DicomViewer.jsx`; plus the
ground-truth `validation/behavior_card.json` and `docs/DESIGN_INTEGRATION_PLAN.md` §D (WF7).
MEASURED fact vs RECOMMENDATION is marked throughout. No metric is invented.

---

## 0. The single most important measured fact

**There is NO measured accuracy for CT or MRI. It does not exist.**
`validation/behavior_card.json` is 100% chest X-ray: `"model":
"torchxrayvision ensemble: densenet121-res224-all"` (line 2), every `detection[]` entry is a
CXR pathology (Atelectasis, Effusion, …). A full-text search for `ct|mr|dicom|candidate|
modality` returns only "densenet". `routers/report.py` has zero CT/MR references — the report
path is CXR-only. So any AUROC/ECE/sensitivity/specificity for CT/MRI would be fabricated. The
CT/MRI detectors are **classical, deterministic, and never characterized against ground truth.**
This is the honest baseline that every claim below must respect.

---

## 1. Verified honesty guarantees (these HOLD — MEASURED from source)

### 1a. `validated=False` is structural and triple-enforced — cannot be flipped by a detector
- Schema defaults: `CandidateFinding.validated: bool = False` (`models/detect.py:34`) and
  `CandidateResponse.validated: bool = False` (`models/detect.py:58`), with the docstring
  "classical detectors never set this True" (`models/detect.py:9,34`).
- The router **hard-codes** `validated=False` when building each finding
  (`routers/detect.py:104`, `_to_candidate`) and on the response envelope
  (`routers/detect.py:113`, `_response` base dict). Because `_to_candidate` sets
  `validated=False` literally — it never reads a `validated` key off the detector dict — even a
  hypothetical detector returning `validated=True` would be overridden. Belt-and-suspenders.
- `ct_cade.py` / `mr_cade.py` never emit a `validated` key at all (confirmed by read); the only
  `True` in either file is unrelated (`is_ct`). No code path anywhere sets `validated=True`.

### 1b. `research_only=True` is hard-coded, `DETECT_RESEARCH_ONLY = True` (config, not env)
- `CandidateResponse.research_only: bool = True` (`models/detect.py:59`, "hard True — never a
  device claim") and injected `research_only=True` on every response (`routers/detect.py:113`).
- `config.py:595 DETECT_RESEARCH_ONLY = True` is a constant with **no env override** — unlike
  the ENABLE flags, research framing cannot be turned off by configuration.

### 1c. The disclaimer is a REQUIRED field — a response cannot exist without it
- `CandidateResponse.disclaimer: str` has **no default** (`models/detect.py:70`), so Pydantic
  rejects construction of any response lacking it. The router always injects the modality string
  (`routers/detect.py:110-112`: `CT_DETECT_DISCLAIMER` / `MR_DETECT_DISCLAIMER`). This is a
  structural guarantee, not a convention.
- Disclaimer text (`config.py:658-674`) is unambiguous: "RESEARCH USE ONLY — UNVALIDATED …
  CANDIDATE regions, NOT a diagnosis … NOT FDA-cleared or CE-marked … NOT a medical device …
  may miss real disease and flag normal anatomy … Scores are detector confidence, NOT a
  probability of disease." The MR variant additionally forbids absolute/tissue-specific claims.

### 1d. No calibrated probability — and none can be produced on this path
- `score` is `Field(ge=0, le=1)` documented "DETECTOR score … NOT a validated probability of
  disease" (`models/detect.py:32-33`). Scores come from geometric heuristics
  (`ct_cade.py:116-117` extent×elongation; `mr_cade.py:63` z-score mapping) — never through
  `services/calibration.py`. There is no `calibrated_probability` field on the CT/MR schema.
- The frontend feedback POST tags these `calibration_state: 'uncalibrated'`
  (`CandidateFindings.jsx:79`), so CT/MR candidates cannot pollute the CXR calibration map.

### 1e. MR never emits an HU / absolute claim
- `mr_cade.py:71` sets `"mean_hu": None` with comment "MR is a.u. — never an HU claim";
  candidates are relative outliers (z ≥ 2.5σ vs the tissue's own mean, `mr_cade.py:16,40,62`).

### 1f. The viewer channel is model-free by construction
- `VIEWER_DISCLAIMER` (`routers/viewer.py:26-33`): "This image view is model-free — no AI is
  applied to the pixels shown … Any AI on this modality … is opt-in, off by default, shown
  separately, and never a diagnosis." Attached to every viewer/ROI response
  (`viewer.py:102,153,183,228`). A head CT can never be scored by the CXR model — modality
  routing in `routers/analyze.py` rejects non-CXR DICOM (per inv_backend §3.1).

### 1g. Both AI paths default OFF and fail closed
- `CT_DETECT_ENABLED` / `MR_DETECT_ENABLED` default `"0"` (`config.py:592-593`); a disabled
  deployment returns 503 with an audit event **before** any work (`routers/detect.py:138-140`).
- Modality is enforced twice: consensus at the API boundary (`detect.py:144-146`, 422 on
  mismatch) and again inside the job (`detect.py:71-74`, raises on CT/MR volume mismatch).
- Every detector name is re-checked against a fail-closed whitelist at run time
  (`ct_cade.py:302`, `mr_cade.py:91` → `config.assert_detector_allowed`), and the shared job
  store refuses to render a segment/anatomy job through the CADe builder (`detect.py:168`).

### 1h. "No candidates" is explicitly NOT "normal" — REFUTES the omission risk on this path
- The backend emits `candidate_count=0` with **no** "normal"/"clear" field of any kind.
- The frontend renders, for the zero-candidate `done` state: *"No candidate regions above
  threshold. This is NOT a 'normal' result — the detector is unvalidated and may miss disease."*
  (`CandidateFindings.jsx:126`). The abstain state additionally prints "Detector ABSTAINED on
  this volume" (`CandidateFindings.jsx:114-118`). So both empty paths (abstain and
  genuinely-none) surface a non-normal message; neither can read as a clean result in the UI.

**Verdict on the core claim:** On the CT/MRI channels, the guarantee *"even when the model
cannot identify disease it never emits an incorrect diagnosis"* is **structurally upheld** —
there is no diagnosis, no calibrated probability, no validated flag, no "normal" assertion,
and a mandatory disclaimer on every response. The candidate detectors are honest heuristics
wrapped in enforced framing.

---

## 2. Residual risks & leaks (RECOMMENDATION — ranked)

None of these is a diagnosis leak today, but each could let a CT/MR output be *misread* as one.

1. **The "not normal" guarantee lives only in the frontend string, not the API contract.**
   `CandidateFindings.jsx:126` is the sole place the non-normal message exists. The backend
   zero-candidate response (`candidate_count=0`, `status="done"`) carries no machine-readable
   "this is not a negative read" flag. A second UI, a WF7 report generator, or any API consumer
   polling `GET /api/ct-detect/{id}` could programmatically treat `candidate_count==0` as
   "clear". RECOMMEND: add an explicit backend field (e.g. `negative_read_supported: false` /
   `absence_of_candidates_is_not_normal: true`) so the non-claim travels with the data.

2. **Score is rendered as a percentage next to a disease-shaped label.** `CandidateFindings.jsx:141`
   shows "score 87%" beside "Candidate pulmonary nodule". Even with the "(detector, not disease
   P)" qualifier and the disclaimer, a percentage adjacent to a named disease is visually
   identical to the CXR calibrated-probability chip and is the most likely thing a hurried reader
   over-trusts. RECOMMEND: render detector score as a non-probabilistic band (e.g.
   "salience: low/med/high") or a bare unitless number, never `%`, to break the visual equivalence
   with calibrated CXR probabilities.

3. **MR has NO competence/abstain gate.** `routers/detect.py:75` hard-codes `("read", [])` for any
   non-CT volume — `_competence` runs on CT only. `mr_cade.detect` will therefore run on literally
   any MR volume (any sequence, any body part) and can emit "Candidate focal signal abnormality"
   with no input-appropriateness check. RECOMMEND: an MR competence gate (foreground fraction,
   sequence sanity, SNR) mirroring the CT one, or at minimum a down-weight default for MR.

4. **The CT abstain gate is a hand-set, unmeasured threshold.** `_competence` uses HU range < 200 →
   abstain, min-HU > -300 → down-weight (`detect.py:40-43`). No measured false-abstain or missed-
   degenerate rate exists. This is the same "unvalidated gate constant" gap flagged for the CXR
   OOD gate in inv_safety §2.5, and it applies here too.

5. **CT detectors are not anatomically scoped to their target region.** The hyperdensity detector
   (`ct_cade.py:155-173`) has no chest constraint; on a head CT (where `_lung_mask` finds no lungs
   and the nodule/effusion/pneumothorax detectors correctly no-op) it will still fire on falx/
   choroid/vascular calcium and label them "Candidate hyperdensity (e.g. haemorrhage/
   calcification)". Contained by framing (still `validated=False` + disclaimer), but it is a
   false-positive generator whose behaviour is uncharacterized. RECOMMEND: document per-detector
   intended body region, and gate hyperdensity to a body/thorax mask unless a validated
   head/cerebral detector is explicitly enabled.

6. **WF7 (CT/MRI report) does not exist yet — but is the highest future leak surface.** There is
   currently no `/api/ct-report` and no CT/MR path through `report.py`, so no report-based leak
   exists today. §3 below defines the mandatory guardrails before it is built.

---

## 3. What real CT/MRI validation would require BEFORE any diagnostic claim

CT/MR detection is a *localization* task, not per-image classification, so the CXR
AUROC/ECE apparatus does not transfer. To make ANY diagnostic (non-research) claim:

- **Independent, lesion-annotated, multi-site data per detector kind** — e.g. LIDC-IDRI / LUNA16
  (lung nodules), RSNA Intracranial Haemorrhage & CQ500 (bleed), a labelled pleural-effusion /
  pneumothorax CT set, and for MR a lesion-annotated set (e.g. BraTS-style) with expert masks.
  None of these has been run; today's detectors have zero measured operating points.
- **FROC / CPM analysis** (free-response ROC): per-lesion **sensitivity at fixed false-positives-
  per-scan** (e.g. sens @ 1, 2, 4 FP/scan) with 95% bootstrap CIs — the correct metric for a
  "candidate box" detector, replacing image-level AUROC.
- **Per-lesion localization accuracy**: hit criterion (centroid-in-mask or IoU ≥ τ) and detection
  IoU distribution vs expert masks; report miss rate by lesion size (the 3–30 mm nodule band in
  `ct_cade.py:26-27` will have a size-dependent miss profile).
- **The abstain/competence gate measured as a first-class classifier** (per inv_safety §3d):
  catch-rate on inappropriate volumes vs over-abstain on valid ones, ROC, chosen operating point —
  and an MR gate must first exist to be measured.
- **A published NPV of the zero-candidate state at realistic prevalence** — the formal statement
  of "absence of candidates is not a negative read." Until this number exists, the UI must keep
  asserting non-normality (§1h) and never imply clearance.
- **Reader study (MRMC)** for any clinical claim; subgroup/scanner/site stratification;
  test-retest robustness; ISO 14971 risk file mapping each §2 risk to a mitigation.
- **Determinism note (a genuine strength):** the classical detectors are byte-identical across
  runs (`ct_cade.py:14-15`), so they are trivially reproducible for a validation harness — a real
  advantage over a stochastic model when building the evidence file.

Only after FROC operating points + calibrated per-lesion confidence + a measured abstain gate +
a published zero-candidate NPV exist could `validated=False` responsibly become anything else —
and even then only within a locked intended-use statement.

---

## 4. WF7 CT/MRI report — mandatory framing (RECOMMENDATION, aligned to DESIGN_INTEGRATION_PLAN §D)

When the CT/MRI report (`/api/ct-report`, `models/ct_report.py`, `CtReportPanel`) is built, it
must be *feature*-parity with CXR but *honestly sub-parity in claims* (plan §D lines 277-279):

1. **Compose only from clinician-CONFIRMED candidates + anatomy measurements + ROI stats —
   never from a raw score or any probability.** The report is a "summary of unvalidated research
   candidates and anatomy measurements — NOT a diagnosis, NOT triage" (plan §D:305-306).
2. **Hard-inject `CT_DETECT_DISCLAIMER` / `CT_OVERLAY_DISCLAIMER` into every draft and every
   tab** (clinical/patient/differentials), and forbid probability/diagnosis phrasing in the
   template layer — run an `assertNoDiagnosisFields`-style guard **server-side**, not only in
   the client (plan §D:288-290).
3. **Carry the zero-candidate non-claim into the report** verbatim: an empty report must state
   "This is NOT a 'normal' result — the detector is unvalidated and may miss disease"
   (plan §D:307-308). Wire it to the machine-readable flag recommended in §2.1.
4. **A CT/MRI "what was NOT assessed" completeness list** (no validated disease coverage), so the
   completeness gate stays honest (plan §D:291-292).
5. **No AUROC/ECE/accuracy tile anywhere for CT/MRI** — none exist (plan §D:308); mixing a CXR
   accuracy number into a CT/MR surface would be the worst possible leak.
6. **Sign-off gate + AI-vs-edited provenance mandatory**; no AI candidate auto-populates a signed
   report (mirrors CXR; IMPROVEMENT_ROADMAP line 14). The confirm action
   (`CandidateFindings.jsx:155`) must write a candidate as an *unconfirmed* structured finding the
   clinician then signs.

---

## 5. Bottom line

The CT/MRI channels are, today, an honest research demo: no diagnosis, no calibrated
probability, `validated=False` triple-enforced, a required disclaimer, model-free viewer,
default-OFF fail-closed AI, and an explicit "not normal" on empty results. The core safety
claim holds on this path. The residual work is (a) move the "not normal" guarantee out of a
single frontend string into the API contract, (b) stop rendering detector score as a percentage,
(c) add an MR competence gate, and (d) keep WF7 strictly framed as a summary of unvalidated
candidates + measurements. No diagnostic claim is defensible until FROC operating points, a
measured abstain gate, and a published zero-candidate NPV exist — and none exist yet.
