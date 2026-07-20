# AI Radiology Assistant & Report Generator — Coverage

A decision-support prototype for **chest X-ray** interpretation: the AI *drafts*
findings, regions of attention, and reports; a **licensed clinician reviews,
corrects, and signs off**. Nothing is treated as a diagnosis, and no output is
final until a human attests to it.

> **Framing (enforced everywhere):** "model confidence" and "region of model
> attention" — never "diagnosis" or "lesion boundary". Human-in-the-loop.
> No PHI / no real patient data. Not FDA-cleared; not a medical device.

- **Backend:** FastAPI · TorchXRayVision (DenseNet-121 ensemble, Apache-2.0) ·
  pytorch-grad-cam · pydicom · OpenCV · Pillow · uvicorn
- **Frontend:** React + Vite · jsPDF (client-side PDF)
- **Tests:** 96 backend tests passing · frontend builds clean
- **Deploy target:** single-origin Docker Space (CPU-only)

---

## Table of contents

1. [Chest X-ray AI pipeline](#1-chest-x-ray-ai-pipeline)
2. [Accuracy & anti-shortcut defences](#2-accuracy--anti-shortcut-defences)
3. [Heatmap / localization honesty](#3-heatmap--localization-honesty)
4. [Self-audit / out-of-distribution gate](#4-self-audit--out-of-distribution-gate)
5. [Measurement & validation tools](#5-measurement--validation-tools)
6. [CT / MRI viewers (honest, no-AI)](#6-ct--mri-viewers-honest-no-ai)
7. [Report generation](#7-report-generation)
8. [Viewer & UX features](#8-viewer--ux-features)
9. [Multi-image studies & comparison](#9-multi-image-studies--comparison)
10. [Security & privacy](#10-security--privacy)
11. [Testing & verification](#11-testing--verification)
12. [Configuration reference](#12-configuration-reference)
13. [Known limitations (honest gaps)](#13-known-limitations-honest-gaps)
14. [File map](#14-file-map)

---

## 1. Chest X-ray AI pipeline

**Model.** Pretrained **TorchXRayVision DenseNet-121** (`densenet121-res224-all`,
Apache-2.0). Optional ensemble via `ENSEMBLE_WEIGHTS` — banded outputs are
averaged **per label** so each model votes only on classes it actually has and
whose operating point is defined.

**Confidence, not probability-of-disease.** Displayed confidence is each model's
**op_norm banded output**, calibrated so **0.5 == the operating point**. Classes
with no calibrated operating point are dropped rather than shown as a misleading
0.5. `confidence ≥ threshold` is exactly "flagged".

**Grad-CAM on raw logits.** Attention maps are computed on the classifier's **raw
logits** via a `_LogitWrapper`, because op_norm + sigmoid saturate the gradients
and make the maps vanish. Per-finding localization: each flagged finding gets its
own Grad-CAM, sourced from the ensemble model that scored that label highest.

**Preprocessing.** `xrv.datasets.normalize(img, 255)` → `[-1024, 1024]`, then
**pad-to-square** (not centre-crop) so the full field of view is analyzed — a
centre crop would silently discard the apices and costophrenic angles where
pneumothorax and effusion present.

**Localization budget.** Every flagged **priority/emergency** label (Pneumothorax,
Pneumonia, Consolidation, Effusion, Edema, Mass, Lung Lesion) is always localized
and anatomy-gated — so a dangerous flag is never shown without an anatomy check —
then remaining slots (`LOCALIZE_MAX`) are filled by confidence.

---

## 2. Accuracy & anti-shortcut defences

The core failure mode of chest-X-ray AI is **shortcut learning** (Zech et al.
2018; DeGrave et al. 2021): the model keys on burned-in markers, not anatomy.
Three independent guards address it.

### 2.1 Burned-in marker masking (root-cause fix)
`_mask_burned_in_markers()` detects near-saturated, compact glyphs in the image
**margins only** (side letters, "PORTABLE", timestamps) and **inpaints** them
(Telea) **before** the model or Grad-CAM ever see the image. The clinician still
views the **original** image; only the model's input is cleaned.

- **Proven on the real film:** Effusion attention hot-centroid moved from
  **x=91%, y=13% (94% of hot mass in the marker corner)** to **off-corner (0%)**;
  the marker-driven Effusion/Edema flags are then suppressed by the anatomy gate.
- Verified never to erase a bright finding inside the lungs (centre is protected).

### 2.2 Anatomy gate
`anatomy.py` segments 14 chest structures with `xrv.baseline_models.chestx_det.PSPNet`
and computes the fraction of a finding's high-attention region that overlaps the
anatomy it could plausibly arise from (heart→cardiac, lungs→parenchymal,
bone→fracture). Below `ANATOMY_MIN_OVERLAP` the flag is **suppressed** with a
reason; below `ANATOMY_CAUTION_OVERLAP` it is **cautioned**. This is what drops
"Cardiomegaly on the arm".

### 2.3 Background gate
`_background_fraction()` suppresses/cautions a flag whose attention sits on
near-black, non-anatomical border pixels.

---

## 3. Heatmap / localization honesty

Every rendered map declares **what it is**, so a reader can never confuse
"confident nothing there" / "abstained" / "all-zero CAM" / "pipeline crashed".

**Per-finding state** (`Finding.heatmap_state` + `heatmap_caption`):

| State | Meaning | Overlay |
|---|---|---|
| `localized` | focal region of attention | soft gradient; crisp contour only if grid ≥ 16 |
| `diffuse` | attention spread > 40% of the frame | **no** overlay, no size — labelled non-localizing |
| `suppressed` | dropped by anatomy/background gate | none; reliability note shown |
| `none` | all-zero CAM | none; "attention map was empty" |
| `not_localized` | flagged by score, below localization budget | none; "map not computed" |
| `error` | Grad-CAM raised | none; fields rolled back |

**No crisp contour at 7×7.** The DenseNet CAM's native grid is 7×7; upsampling to
1000px adds no resolution. A crisp outline implies a boundary the model cannot
support, so at grid < `CONTOUR_MIN_GRID` (16) only a **soft gradient** is drawn.
`_classify_cam` + `_cam_cells_spanned` gate this.

**Rendering.** Floor-and-ceiling **percentile normalization** (not min-max, which
manufactures a hot spot on every image), **activation-proportional alpha** (cold
regions fully transparent — no whole-frame purple haze), **inferno** by default,
**cividis** for colour-vision deficiency (`HEATMAP_COLORMAP`), **never jet**.
Colour encodes **intensity only, never pathology identity**; each pathology is a
separate toggleable layer.

**No masquerade.** A `diffuse`/`none`/`suppressed`/`error` finding never ships a
`heatmap_url` or a size estimate — the state and caption carry the explanation
instead. The UI surfaces a per-finding **map-status list** (including suppressed
findings) so nothing is ever a silent blank.

> **res512 option:** a `resnet50-res512-all` localizer gives a true 16×16 grid but
> costs ~10.7 s/CAM on CPU and its logit differs from the ensemble probability, so
> it is **deferred / documented**, not shipped by default.

---

## 4. Self-audit / out-of-distribution gate

`self_audit.py` scores each input READ / DOWN-WEIGHT / ABSTAIN **before** running
the model, so a non-chest-radiograph (a knee film, a CT slice, a colour photo) is
refused rather than confidently mis-scored:

- **Colour saturation** — the strong, cheap signal (radiographs are grayscale).
- **TorchXRayVision autoencoder** reconstruction error — secondary signal.
- Heuristics; **fails safe** and is cheaper on refusal.

A lateral/AP view (out-of-distribution for a frontal-trained model) is
down-weighted with a reason.

---

## 5. Measurement & validation tools

Localization value is **measured, not claimed**.

| Tool | What it answers | Result on our data |
|---|---|---|
| `backend/tools/marker_ablation.py` | Does confidence collapse when the marker is removed? (proves shortcut vs. signal) | P(Effusion) Δ+0.003 — shortcut was in the *attention*, not the score |
| `validation/pointing_game.py` (224, 7×7) | Is the CAM peak inside the expert box, vs. an "always guess chest-centre" baseline? | 28% vs 31% baseline (n=32) — honestly **below** baseline overall |
| `validation/pointing_game.py` (res512, 16×16) | Same, with the high-res localizer enabled | **50% vs 41% baseline = +9.4% lift** — the 16×16 grid flips it **above** baseline (Effusion +25%, Infiltration +50%). Directional: `--limit` picked a slightly different 32-box subset |
| `validation/cam_divergence.py` | Are per-class CAMs class-specific or collapsing to one region? | `aa2a5daa3ca9`: **CLASS-SPECIFIC** (mean IoU 0.16) |
| `validation/run_validation.py` | Per-label AUROC / sensitivity / specificity + Youden-J threshold calibration | emitted to `behavior_card.json` / `calibration.json` |
| `validation/run_validation.py` (calibration) | **Reliability diagram + Expected Calibration Error** on the displayed confidence | **ECE ≈ 0.24** (overconfident): the 0.50–0.60 band was positive only ~8% of the time |
| `validation/run_validation.py` (subgroup) | Per-view micro-AUROC (acquisition shift) | PA 0.812 vs AP/portable 0.794 |
| `validation/perturbation_stability.py` | Flag-decision "flip rate" under hflip / ±3° rotation / crop — signal vs. noise | reports per-label std + flip rate |

The **behavior card** (measured AUROC per label, with a ⚠ on classes with too few
positives) is shown in the UI so accuracy is displayed honestly, in-distribution
and optimistic by construction.

**Key honest finding — the confidence is not a calibrated probability.** ECE ≈ 0.24
means the displayed number is a *ranking score at the operating point*, not a
probability of disease: "52% confidence" corresponded to only ~8% observed
positives. This is surfaced in the UI (a note under the confidence panel) and in the
failure gallery, and it directly explains the operating-point over-flagging. An
isotonic calibrated-probability mapping is the measured next step.

**Higher-resolution localization (`services/localizer.py`, opt-in).** A res512
ResNet localizer (16×16 grid) runs Grad-CAM for *flagged findings only* — the 224
ensemble still produces the displayed confidence; the 512 model produces a sharper
attention map where a crisp contour becomes defensible and the pointing score
crosses above baseline. Off by default (~10 s/CAM on CPU), capped at
`LOCALIZER_MAX_FINDINGS`; enable via `LOCALIZER_WEIGHTS`. Note: **no per-pathology
segmentation** exists in the license-clean stack (TorchXRayVision ships only anatomy
segmentation, used as the anatomy gate), so this localizer is the localization-
quality path, not a seg swap.

**Confidence → action.** Each flagged finding carries an explicit `disposition`
(urgent / recommend correlation / borderline-below-threshold / flagged-for-review),
shown as a chip and used in the report, so the UI is decision-support rather than a
number dump.

**Provenance invariant (`services/provenance.py`).** A generated report may not
assert a measurement with no backing clinician-entered size field; the LLM path
rejects such a draft and falls back to the deterministic template, so a fabricated
measurement is structurally unable to reach the report.

**Patient-summary readability** is a gated test (`services/readability.py`):
Flesch-Kincaid grade of the generated summary is asserted ≤ 9, and priority/urgent
findings auto-insert severity-gated "contact your care team" safety-netting.

**Security:** see [SECURITY_REVIEW.md](SECURITY_REVIEW.md) — an adversarial review
across auth/upload/DICOM/injection/SSRF/PHI; one High (PHI descriptor egress) and a
cluster of Medium DoS/robustness items were fixed.

### Calibration & decision-quality layer

The displayed number is a ranking **score**, not a probability. This layer makes
that honest and makes the downstream subsystems stop standing on the raw number:

- **Calibration map (`services/calibration.py`)** — a per-label isotonic map (fitted
  by `run_validation.py --emit-calibration-map`) ships a `calibrated_probability`
  alongside every finding. Verified live: raw 0.5 → **P≈5%** for most labels, shown
  as a `P≈` chip and a per-label `ECE` chip in the Viewer.
- **Fusion (`FUSION_MODE`)** — `max` (default, safety-favouring) / `calibrated_mean`
  / `noisy_or`; a **down-weighted view is scaled** (`DOWNWEIGHT_FUSION_FACTOR`) so a
  "less reliable" projection can't drive the study by accident.
- **Compare noise floor** — an interval delta smaller than the label's **measured
  perturbation std** (`perturbation_stats.json`, e.g. Cardiomegaly ≈0.066) is
  reported "within measurement noise", not progression.
- **Decision Curve Analysis (`validation/decision_curve.py`)** — net benefit vs
  treat-all/none on the calibrated probability: the model helps at low thresholds
  (prevalence ≈5%) and not at high ones — surfaced, not hidden.
- **Risk-coverage (`validation/risk_coverage.py`)** — abstaining on the least
  confident cases raises accuracy 64%→98%: the abstain signal is selective.
- **Anatomy-gate FN audit (`validation/anatomy_gate_audit.py`)** — the one component
  that can delete a correct finding; its false-negative rate is measured into the
  behaviour card (`ANATOMY_GATE_MODE=warn_only` keeps flags instead).
- **HIPAA-adjacent:** salted **scrypt** password hashing, a PHI-free **audit trail**
  (§164.312(b)), and **auto-logoff** idle timeout (§164.312(a)(2)(iii)).

### CT / MRI experience design

High-level, developer-ready UI designs (from a 10-agent research fan-out) live in
[CT_UI_DESIGN.md](CT_UI_DESIGN.md) and [MRI_UI_DESIGN.md](MRI_UI_DESIGN.md). They
keep the honesty guardrail central (**AI describes anatomy, never disease**),
identify the **volume-pivot** (ship the HU volume, not baked PNGs) as the unlock for
MPR/MIP/HU-ROI, and phase the buildable-now work. Phase-1 items landed now: the
`abdomen` HU preset and the **B3 fix** (effective rendered-pixel spacing, so the
caliper is correct on downscaled slices).

---

## 6. CT / MRI viewers (honest, no-AI)

`POST /api/dicom-view` is an **image viewer only** — model-free **by
construction** (it never imports the chest model) so a head CT can never be
silently scored, and the response contains **no** field named or shaped like a
diagnosis (`finding`, `probability`, `impression`, `heatmap_url`).

- **CT** — Hounsfield rescale + **window presets** (brain, stroke, subdural, bone
  [temporal], skeletal, lung, mediastinum, liver, angio) in HU; the `bone` key is
  kept stable for back-compat.
- **MR** — **percentile** windowing from the stack (arbitrary units, **never** HU,
  CT presets never applied); advisory sequence label auto-detected from
  `SeriesDescription`/`ProtocolName`/`SequenceName` ("auto — verify").
- **Series** — geometric slice ordering (`ImagePositionPatient · normal`),
  multi-frame support, slice slider + wheel/keyboard navigation.
- **Safety** — de-identification on every file, a **burned-in-annotation warning**
  (YES/UNKNOWN), a persistent "no AI on this modality — not a medical device"
  banner, MONOCHROME1 inversion, anisotropic-aware caliper.
- **DoS-bounded** — each slice is downscaled to ≤ `VIEW_MAX_EDGE` **at decode**,
  no raster is retained, accumulation stops at `VIEW_MAX_SLICES`, uploads are read
  in capped chunks, and file-count / total-byte limits apply.

Tabs are labelled **CT (viewer)** / **MRI (viewer)** to avoid implying analysis.

---

## 7. Report generation

- **Clinician-confirmed only.** `structured` findings are what the clinician
  confirmed; AI suggestions live separately and are never auto-adopted.
- **Attestation required.** No reviewer name + attestation → no final report,
  no export.
- **Three sections:** clinical report, patient-friendly summary, reference
  differentials — plus a completeness check (discordance / empty-section /
  borderline flags).
- **LLM optional.** Template generator by default; Gemini / Groq / Ollama
  pluggable via `LLM_PROVIDER` (none required).
- **Client-side PDF** (jsPDF): per-finding region thumbnails, size *estimates*
  explicitly labelled, provenance ("AI-drafted" until edited), no false "PA"
  projection, patient identifiers rendered **locally only** and never sent to the
  server.

---

## 8. Viewer & UX features

- **Overlays:** heatmap / contour / off, opacity control, per-pathology region
  picker, inferno legend, grounded hover (hovering a finding highlights its
  region), **per-finding map-status list**.
- **Window/Level:** brightness/contrast presets (Default/Lung/Bone/Soft tissue) +
  invert (display aid on the 8-bit image).
- **Caliper:** simple **mm ↔ px** toggle; anisotropic-aware (scales dx/dy by
  column/row spacing independently); mm only when DICOM pixel spacing is known.
- **Zoom/pan:** wheel-zoom about the cursor (up to 6×), drag-to-pan.
- **Confidence panel:** per-pathology bars with a confidence-threshold slider and
  measured NIH AUROC chips.
- **Trust markers:** model name/version + "markers masked / anatomy gate" footer,
  study metadata strip (modality, view, source, de-identified image id,
  identifiers-removed count), "what happens next" + glossary, known-limitations
  page, disagreement surfacing, feedback thumbs (PHI-free), info / how-to page.
- **Intake / login / info:** optional client-side patient intake (never
  transmitted), stateless login/logout, modality tabs.

---

## 9. Multi-image studies & comparison

- `POST /api/analyze-study` accepts multiple current views (PA + lateral + …),
  runs each through the full pipeline independently (per-image Grad-CAM), and
  returns per-image analyses + a **fused** block (per-label max banded confidence
  across non-abstained views, tagged with the producing view).
- **In-study md5 dedup** so a byte-identical image can't double-count in fusion.
- One bad/abstained view degrades to a single abstained slot rather than failing
  the whole study.
- **Prior-image comparison:** `POST /api/compare` produces a stable/new/worsened/
  improved/resolved delta table, framed as *change in model confidence*, not
  confirmed disease progression.

---

## 10. Security & privacy

- **No PHI by construction:** patient identifiers stay client-side; analysis JSON
  lives in a **non-served** directory; feedback sink is schema-validated and has
  no free-text identifier field.
- **DICOM de-identification** at ingest: direct identifiers removed, UIDs
  regenerated, private tags stripped, `identifiers_removed` reported;
  burned-in-annotation disclosed.
- **Auth (optional):** stateless HMAC-signed session token, HttpOnly cookie,
  middleware-gated PHI-adjacent prefixes (incl. `/api/dicom-view`), per-IP login
  throttle.
- **Hardening:** constant-time access-code compare, CSP + HSTS + COOP, `/docs`
  off in prod, Content-Length DoS guard, decompression-bomb guard, per-IP rate
  limiter (incl. the viewer path), pinned dependencies, TTL storage sweeper,
  static-privacy (only images/heatmaps are public).

---

## 11. Testing & verification

- **96 backend tests** (pytest) — including heatmap-honesty, CT/MRI viewer/DoS,
  report-safety (readability/provenance/disposition), and calibration/fusion/
  compare/scrypt tests, all torch-free (no weights needed in CI).
- **Two multi-agent review passes** — a design/research pass and an adversarial
  verification pass — whose confirmed defects were all fixed (memory-DoS in the
  viewer, diffuse-map masquerade, a Viewer runtime crash, anisotropic caliper,
  modality-consensus, error-finding field leak).
- **Live end-to-end checks** on the real problem films and synthetic CT/MR series;
  OOD abstain confirmed on a colour photo.

Run:
```bash
# backend
cd backend && python -m pytest
# frontend
cd frontend && npm run build
# measurement tools
python backend/tools/marker_ablation.py backend/storage/uploads/<img>.png
python validation/pointing_game.py --limit 120
python validation/cam_divergence.py ../backend/storage/uploads/<img>.png --top 5
```

---

## 12. Configuration reference

Selected env knobs (all have safe defaults):

| Area | Keys |
|---|---|
| Flagging | `FINDING_THRESHOLD`, `URGENT_THRESHOLD`, `PNEUMOTHORAX_ALERT_THRESHOLD`, `LABEL_THRESHOLDS` |
| Ensemble | `ENSEMBLE_WEIGHTS`, `TTA_HFLIP`, `LOCALIZE_MAX` |
| Localizer (res512) | `LOCALIZER_WEIGHTS`, `LOCALIZER_MAX_FINDINGS`, `CAM_NATIVE_GRID` |
| Calibration | `CALIBRATION_MODE` (isotonic/platt/none), `CALIBRATION_MAP_PATH` |
| Fusion / compare | `FUSION_MODE`, `DOWNWEIGHT_FUSION_FACTOR`, `COMPARE_MIN_DELTA_MODE`, `COMPARE_NOISE_K`, `PERTURBATION_STATS_PATH` |
| Marker mask | `MASK_MARKERS`, `MARKER_BRIGHT_MIN`, `MARKER_MARGIN_FRAC`, `MARKER_MAX_AREA_FRAC` |
| Anatomy gate | `ANATOMY_GATE_ENABLED`, `ANATOMY_GATE_MODE` (suppress/warn_only), `ANATOMY_MIN_OVERLAP`, `ANATOMY_CAUTION_OVERLAP` |
| Heatmap honesty | `CONTOUR_MIN_GRID`, `CAM_MIN_CELLS`, `CAM_DIFFUSE_MAX_FRAC`, `HEATMAP_COLORMAP`, `OVERLAY_*` |
| Self-audit | `SELF_AUDIT_ENABLED`, `SELF_AUDIT_AE`, `OOD_*`, `COLOR_SAT_OOD` |
| Report safety | `READABILITY_MAX_GRADE` (test), provenance invariant (server), disposition |
| Upload / DoS | `MAX_UPLOAD_MB`, `MAX_IMAGE_PIXELS`, `STUDY_MAX_IMAGES`, `TRUSTED_PROXY_HOPS`, `RATE_LIMIT_*` |
| CT/MRI viewer | `VIEW_MAX_FILES`, `VIEW_MAX_SLICES`, `VIEW_MAX_EDGE`, `VIEW_MAX_TOTAL_MB` |
| Security / HIPAA | `ACCESS_CODE`, `AUTH_ENABLED`, `SESSION_SECRET`, `SESSION_IDLE_TIMEOUT_SECONDS` (auto-logoff), `AUDIT_ENABLED`, `ENABLE_DOCS`, `DEIDENTIFY_DICOM`, `STORAGE_TTL_SECONDS` |
| LLM (optional) | `LLM_PROVIDER`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OLLAMA_HOST` |

---

## 13. Known limitations (honest gaps)

- **Localization at 7×7 (the default) does not beat a chest-centre baseline** on
  the small local NIH sample (28% vs 31%). The **opt-in res512 16×16 localizer**
  crosses above it (≈50% vs 41%, +9.4% on its subset) but costs ~10 s/CAM on CPU,
  so it is off by default — a capability, not the shipped default. Both numbers are
  reported in §5 with a Wilson CI; a full 984-box run (needs the full NIH download)
  is required before either is a headline claim.
- **The displayed confidence is a ranking SCORE, not a calibrated probability**
  (measured ECE ≈ 0.24). The isotonic calibration map (§5) ships a
  `calibrated_probability` alongside it; disposition/fusion/compare consume the
  calibrated value where available, and the raw score still drives flags.
- **Operating-point over-flagging:** on a hard portable film many labels sit near
  0.50; each now shows its calibrated P (often ~3–9%), an explicit disposition, and
  a map-state — the noise is labelled, not hidden.
- **The anatomy gate can suppress a true finding** (PSPNet mis-segmentation). Its
  false-negative rate is measured into the behaviour card (`anatomy_gate.fn_rate`),
  and `ANATOMY_GATE_MODE=warn_only` keeps a flag instead of deleting it.
- A **mixed** multi-frame + single-frame CT series can mis-order (rare edge case).
- MR `sequence_label` is unscrubbed DICOM free-text (length-capped, "auto —
  verify") — a low residual PHI surface, disclaimed.
- Research-grade pretrained models on **de-identified, non-clinical** data only;
  **not** FDA-cleared, **not** a medical device.

---

## 14. File map

```
backend/app/
  services/
    vision_xray.py     # ensemble scoring, Grad-CAM, marker mask, heatmap states, overlay
    anatomy.py         # PSPNet anatomy segmentation + attention-overlap gate
    self_audit.py      # OOD / abstention gate
    dicom_utils.py     # DICOM/PNG load, windowing, CT presets, series render_view
    triage.py, fusion.py, templates.py, llm.py, storage.py
  routers/
    analyze.py, study.py, report.py, compare.py, feedback.py, viewer.py
  models/schemas.py    # Pydantic contracts (Finding.heatmap_state, etc.)
  config.py, main.py, security.py, auth.py
  tools/marker_ablation.py
  tests/               # 81 tests incl. test_heatmap_honesty.py, test_viewer.py
frontend/src/
  App.jsx
  components/
    Viewer.jsx         # X-ray viewer + heatmap states + map-status + caliper
    DicomViewer.jsx    # CT/MRI honest viewer
    ReportPanel.jsx, FindingsForm.jsx, StudyMetadataStrip.jsx, DisagreementPrompts.jsx,
    KnownLimitations.jsx, WhatNotChecked.jsx, FeedbackThumbs.jsx, Glossary.jsx,
    FindingExplanation.jsx, PatientIntake.jsx, Login.jsx, InfoPage.jsx, StudyStrip.jsx
  api.js, labelMap.js, measurementGuard.js
validation/
  run_validation.py, pointing_game.py, cam_divergence.py, download_data.py
  behavior_card.json, calibration.json
```
