# RadAssist — Design Integration Plan (authoritative)

Owner: lead engineer / architect. Goal: implement the polished RadAssist design in the
EXISTING React 18 + Vite 6 frontend and FastAPI backend, **keep every real working
feature**, **add every design feature (with honesty tweaks)**, bring **CT/MRI to AI +
report parity** (honestly framed), **harden login/auth**, and stand up an
**accuracy-verification research program**.

Sources: `inv_frontend.md`, `inv_backend.md`, `inv_safety.md`, plus on-repo design docs
`CT_UI_DESIGN.md`, `MRI_UI_DESIGN.md`, and the shipped honesty docs
(`KNOWN-LIMITATIONS.md`, `INTENDED-USE.md`, `validation/behavior_card.{json,md}`).

> **Note on inputs.** `inv_design.md` and the source `RadAssist.dc.html` mock were not
> present on disk at plan time (only the three code inventories exist). The "design"
> surface below is reconstructed from the design specification enumerated in the task
> brief (marketing site, Dashboard w/ KPIs+charts+worklist, Login w/ SSO+2FA, accent/
> depth/backdrop theming, Help, Upload, Settings toggles, workspace, findings accept/
> reject, clinical/patient/differential report, sign+export, testimonials, compliance
> badges, evidence/metrics page). When the real `.dc.html` is supplied, reconcile any
> screen not listed here against Section A before building it — the buckets and honesty
> rules still govern.

**Governing rule (non-negotiable):** *the display layer must never assert more than the
model does.* Every metric shown must trace to `validation/behavior_card.json`; every
CT/MRI AI surface stays "research candidate / unvalidated / not a diagnosis"; no
certification is claimed that we do not hold.

---

## A. Reconciliation (three buckets)

### A.1 DESIGN-ONLY — in the design, not in our app → **ADD**

| # | Design feature | What it is | Add as | Honesty gate |
|---|---|---|---|---|
| D1 | Marketing landing hero + sections | Product hero, "how it works", feature grid, evidence, footer | Rebuild `HomePage.jsx` to the design's marketing layout (we already have a landing — this is a visual upgrade, see OVERLAP O1) | Metrics must be real (B) |
| D2 | Testimonials / social proof | Quote cards from named clinicians | New `Testimonials.jsx` (marketing) | **Illustrative only** or drop (B1) |
| D3 | Compliance badge row | HIPAA / ISO 13485 / SOC 2 badges | New `ComplianceStrip.jsx` | **Reframe as "architecture-ready / roadmap", never "certified"** (B2) |
| D4 | Evidence / "the numbers" page | Marketing metrics + charts (AUROC/ECE) | New `EvidencePage.jsx`, page key `evidence` | Numbers from `/api/behavior-card` only (B4) |
| D5 | Console **Dashboard** | KPI tiles, charts, worklist/queue of studies | New `Dashboard.jsx` (page `dashboard`) + `KpiTile.jsx`, `Worklist.jsx`, `MiniChart.jsx` | KPIs are **session/demo metrics + real behaviour-card model stats**, labelled "demo data" where synthetic (B5) |
| D6 | Dedicated **Upload screen** | Full-page upload/intake with study metadata | New `UploadScreen.jsx` (page `upload`), reuses existing `UploadPanel` + `PatientIntake` | patient ids stay client-only |
| D7 | **Login** with SSO + 2FA | Polished auth screen, "Sign in with SSO", 2FA field | Rebuild `Login.jsx` to design; SSO/SAML = roadmap button (disabled + "coming"), 2FA = real TOTP-optional (E) | SSO **not** presented as live unless wired (B6, E) |
| D8 | **Help** page | Searchable help/docs center | New `HelpPage.jsx` (page `help`); folds in existing `InfoPage`, `KnownLimitations`, `FailureGallery` content | keep FailureGallery honesty content |
| D9 | **Settings toggles** panel | Feature toggles (AI channels, theme, density, notifications) | Extend `SettingsPage.jsx` with toggle groups | CT/MRI AI toggles remain **default OFF** and gated by server flags |
| D10 | Accent / depth / backdrop theming | Accent-color picker, elevation/shadow depth, backdrop blur/gradient | New tokens in `styles.css` (`--accent-user`, `--elev-1..3`, `--backdrop-*`); accent picker in Settings | theme still flash-free, system/light/dark preserved |
| D11 | App **shell / console chrome** | Sidebar nav, top bar, breadcrumb, user menu | New `AppShell.jsx` + `Sidebar.jsx` + `TopBar.jsx` wrapping the console pages | — |
| D12 | Global search / command palette (if in design) | Study/patient quick-find | New `CommandPalette.jsx` (optional, Phase 4) | searches local session only, no PHI to server |
| D13 | Notifications / toast center | Transient status + a bell menu | New `Toast.jsx` + `useToast` | status only, no diagnosis text |

### A.2 OURS-ONLY — in our app, not in the design → **KEEP & fold into new UI**

Every one of these is a real, working, safety-load-bearing feature. **None may be dropped.**
They must be re-homed into the new shell/screens, not deleted.

| # | Feature (files) | New home |
|---|---|---|
| K1 | **Chest X-ray AI analyzer** — Grad-CAM heatmap+contour, calibrated-P vs raw chips, per-label AUROC/ECE/disposition chips, threshold slider w/ live sens/spec (`Viewer.jsx`, `analyze.py`) | Workspace (O2) |
| K2 | **Self-audit competence/abstain banner** (`CompetenceBanner.jsx`, `self_audit.py`) | Workspace top |
| K3 | **Two-tier triage banner** (calibrated-P-gated) (`TriageBanner.jsx`, `triage.py`) | Workspace top |
| K4 | **Measurement suite** — length / angle / HU-ROI rect+ellipse on true 16-bit intensity, undo/redo, jump-to-slice (`MeasureLayer.jsx`, `RawWindowCanvas.jsx`, `measureUtils.js`, `measurementGuard.js`, `dicom-roi`) | Workspace + CT/MRI viewer |
| K5 | **CT/MRI model-free viewer** — series rail, window presets, cine, 2-up, raw WW/WL, burned-in warning, de-id strip (`DicomViewer.jsx`, `viewer.py`) | Workspace (CT/MRI tab) |
| K6 | **CT/MRI opt-in Anatomy overlay** (default OFF) (`AnatomyOverlayPanel.jsx`, `OverlayLayer.jsx`, `StructureLegend.jsx`, `segment.py`) | Workspace AI rail |
| K7 | **CT/MRI opt-in research Candidate CADe** (default OFF, RED framing) (`CandidateFindings.jsx`, `detect.py`, `ct_cade.py`, `mr_cade.py`) | Workspace AI rail |
| K8 | **Prior-study comparison** + change table (`compare.py`, ReportPanel `cmp-*`) | Workspace / report |
| K9 | **Report generation** clinical / patient / differentials + sign-off gate + AI-vs-edited provenance + completeness check + measurement/laterality guard + glossary (`ReportPanel.jsx`, `report.py`, `completeness.py`, `templates.py`, `llm.py`) | Workspace report rail (O3) |
| K10 | **Local jsPDF export** w/ embedded region images + client-only patient header (`ReportPanel.jsx`) | Report rail |
| K11 | **Reviewer feedback loop** — Confirm/Dismiss + 👍/👎, `FeedbackAdmin` summary, threshold-refit (`FeedbackThumbs.jsx`, `FeedbackAdmin.jsx`, `feedback.py`, `feedback_stats.py`) | Report + Dashboard ("model tuning") |
| K12 | **Frontend logging + LogViewer** (bounded ring buffer, every fetch) (`logger.js`, `LogViewer.jsx`) | Settings → Diagnostics |
| K13 | **Privacy policy** (7-section honest) (`PrivacyPolicy.jsx`) | Footer + Help |
| K14 | **Honesty/education surfaces** — InfoPage, KnownLimitations, **FailureGallery (7 measured failure modes)**, WhatNotChecked, behavior-card landing metrics | Help (D8) + Evidence (D4) |
| K15 | **Voice dictation** in findings free-text (`FindingsForm.jsx`) | Workspace findings |
| K16 | **Findings form + disagreement prompts** (AI suggestions unchecked by default, "record it/dismiss") (`FindingsForm.jsx`, `DisagreementPrompts.jsx`) | Workspace |
| K17 | **Patient intake** client-only, sessionStorage, PDF-only (`PatientIntake.jsx`) | Upload (D6) + workspace |
| K18 | **Security hardening** — stateless HMAC cookie, scrypt, idle auto-logoff, login throttle, rate-limit, seg-launch limit, access-code, CSP/HSTS, de-id + SC quarantine + decode limit + /static PHI gating (`auth.py`, `security.py`, `dicom_utils.py`, `decode_limit.py`, `audit.py`, `upload_guard.py`) | Preserved + extended (E) |
| K19 | **Draft autosave/restore** (no patient ids) + **ErrorBoundary** + theme sync | Shell |
| K20 | **Behaviour card** measured-metrics endpoint (`/api/behavior-card`) | Powers Dashboard + Evidence |

### A.3 OVERLAP — in both → **REDESIGN so our real backend drives the design's polished UI**

| # | Overlap surface | Our reality (keep the engine) | Redesign action |
|---|---|---|---|
| O1 | Landing / marketing | `HomePage.jsx`, `AboutPage.jsx`, behavior-card metrics | Re-skin to design's hero/sections; **swap any placeholder metric for `/api/behavior-card`**; keep "what it is / is not" honesty block |
| O2 | **Workspace viewer** | `Viewer.jsx` (X-ray) + `DicomViewer.jsx` (CT/MRI) driving `/api/analyze`, `/api/localize-hires`, `/api/dicom-*` | Rebuild layout as design's 3-pane workspace (viewer center, AI rail right, tools left); **keep every Viewer control, overlay mode, threshold slider, measurement, chip** |
| O3 | Findings accept/reject + report | `FindingsForm` + `DisagreementPrompts` + `ReportPanel` driving `/api/generate-report`, `/api/completeness-check` | Re-skin to design's findings list w/ accept/reject affordance; **AI chips stay unchecked-by-default**, sign-off gate stays mandatory |
| O4 | Clinical / patient / differential report | `ReportPanel` 3-tab generator | Re-skin tabs; keep AI-vs-edited provenance + glossary + guards |
| O5 | Sign + export | Reviewer-name + attest gate, jsPDF export | Re-skin to design's "Sign & export" action; keep the hard gate + provenance |
| O6 | Theming | `ThemeToggle.jsx`, CSS custom-prop tokens, flash-free stamp | Extend token set with design's accent/depth/backdrop (D10); keep system/light/dark + cross-instance sync + no-flash inline stamp |
| O7 | Settings / profile | `SettingsPage.jsx`, `ProfilePage.jsx` (`me`/`logout`) | Re-skin into console; add toggles (D9) + accent picker (D10) |
| O8 | Auth probe | `me()`/`login()`/`logout()`, `Login.jsx` (present, unmounted) | Mount `Login` as a real optional gate; rebuild to design + harden (E) |

---

## B. Honesty tweaks to the design (CRITICAL)

Rule: **the display layer must never assert more than the model does.** Every item below
is an overclaim in the design that must be corrected before it ships.

| ID | Design overclaim | Fix |
|---|---|---|
| B1 | **Fabricated testimonials** (named clinicians endorsing) | Either **remove**, or render with a visible "Illustrative — not real endorsements" label and generic personas. Never attribute quotes to real, non-consenting people. |
| B2 | **Compliance badges HIPAA / ISO 13485 / SOC 2** presented as earned | Reframe to **"Architecture-ready / roadmap"**: e.g. "Built toward HIPAA §164.312 technical safeguards" (we do implement audit log, idle auto-logoff, transport controls), "ISO 13485 / IEC 62304 lifecycle: roadmap", "SOC 2: not audited". No certification seal, no "certified/compliant" verb. Link to `INTENDED-USE.md`. |
| B3 | **"Analysed on-device"** claim | We run inference **server-side** (FastAPI). Fix to **"Processed on our server; images de-identified; not sent to third parties"** — which matches `PrivacyPolicy.jsx`. Do not claim on-device/edge inference. |
| B4 | **"Calibrated confidence"** wording implying trustworthy probabilities | Our measured **ECE = 0.2437** (systematic mid-band over-confidence). Reword to **"raw ranking score + a calibration estimate (ECE ≈ 0.24 — imperfect)"**. Keep the existing raw-vs-calibrated chip distinction; never present the number as a reliable probability without the ECE caveat. |
| B5 | **Dashboard KPI tiles** (studies today, accuracy %, turnaround) as if production telemetry | Label demo/synthetic tiles **"Demo data"**. The only *model-accuracy* numbers allowed are from `/api/behavior-card`. Volume/turnaround tiles = local session counts, marked demo. |
| B6 | **"Sign in with SSO / SAML"** presented as live | Render as **disabled "Roadmap"** unless actually wired to an IdP. 2FA can be **real** (optional TOTP, E) — only claim what's wired. |
| B7 | **Marketing accuracy claims** ("99%…", "clinical-grade", "FDA-cleared", "diagnoses") | Ban all of these words. Replace with the real per-label table and the shipped caveat: "engineering sanity check on a research-grade pretrained model … NOT clinical validation." |
| B8 | Any **CT/MRI "diagnosis"/"detection"** framing on marketing or workspace | Keep the hard "research candidate / unvalidated / not a diagnosis" framing everywhere (D-parity in Section D). CT/MRI has **no measured accuracy** — never show an accuracy number for CT/MRI. |
| B9 | **Implied "normal / all-clear"** on a zero-flag read | Add the explicit **"This is NOT a normal read"** non-claim message to the X-ray zero-flag state (mirrors CADe panel), per `inv_safety.md` gap #1. |

### B.4 — Confirm/adjust the design's cited numbers against reality

Verified against `validation/behavior_card.json` (source of truth) and `inv_backend.md §5`:

- **ECE = 0.2437** ✅ EXACT MATCH (4200 label-instances, 10 bins). Show **with** the
  over-confidence caveat (0.50–0.60 band held 1480 instances, mean conf 0.523, only 8.2%
  positive). Do **not** round to "0.24 ≈ well-calibrated."
- **Subgroup micro-AUROC by view: PA = 0.807 (185 img), AP = 0.784 (115 img)** ✅ EXACT.
  Present **both** (the aggregate hides PA-upright vs AP/portable-supine shift). Never show
  a single blended AUROC without the view split.
- **Pneumonia AUROC = 0.458, sensitivity 0.0, n=2 positives** ✅ EXACT — below chance on 2
  positives. Must be shown as a **known weak spot / statistical noise**, kept-with-caution,
  never buried. Companion weak spots to show honestly: **Nodule 0.626 (7 pos)**,
  localization hit-rate **0.0 for Atelectasis & Pneumonia**.
- **Best labels (show alongside worst, no cherry-picking):** Cardiomegaly 0.906, Effusion
  0.839, Pneumothorax 0.828.
- **Grad-CAM localization is weak** (best Cardiomegaly hit-rate 0.6 / IoU 0.129; 51 boxes
  total) — label it "region-of-attention check, not lesion segmentation."
- **Images scored: 300**, NIH ChestX-ray14 sample, flag threshold 0.5. Always state n and
  source next to any number.

**Net:** the design's headline numbers are genuine and match the harness exactly — keep
them, but always ship them with their caveats and the PA/AP split, and never let the UI
imply they are clinical validation.

---

## C. Phased implementation plan (concrete screen → files → endpoints → keep → honesty)

**Serialization flags (multi-phase shared files — edit via additive, well-fenced sections;
never let two phases edit the same block concurrently):**
- 🔒 `frontend/src/styles.css` — touched by Phases 2,3,4,5,6,7. Own it in Phase 2 (token
  layer + component-family fences); later phases only APPEND component sections.
- 🔒 `frontend/src/App.jsx` — touched by Phases 2,3,4,5,6,7 (routing/shell). Convert to
  shell + page-registry in Phase 2 so later phases register a page without reflowing it.
- 🔒 `frontend/src/api.js` — touched by Phases 4,6,7 (new endpoints). Append-only export
  additions; never rename existing exports (they're wired across 36 components).
- 🔒 `backend/app/main.py` — touched by Phases 6,7 (router registration / middleware).
  Append routers; do not reorder the middleware stack (CORS→SecurityHeaders→Auth→
  AccessCode→SegmentLaunch→RateLimit is load-bearing).

---

### Phase 2 — Design-system tokens + shells (foundation; do first)

- **Screens:** none user-facing; establishes the visual system + app chrome.
- **Create:** `frontend/src/components/shell/AppShell.jsx`, `Sidebar.jsx`, `TopBar.jsx`,
  `PageRegistry.js` (map page-key → component), `Toast.jsx` + `useToast.js`.
- **Modify:** 🔒`styles.css` — add token layer: `--accent-user`, `--accent-user-2`,
  `--elev-1/2/3` (depth/shadow), `--backdrop-blur`, `--backdrop-grad`, radius/spacing
  scale, plus dark-mode + `[data-theme]` overrides for each (keep existing tokens intact).
  🔒`App.jsx` — extract routing into shell + page registry (pages: home, dashboard, upload,
  app/workspace, evidence, help, privacy, settings, profile, login); keep existing
  page/tab/modal state semantics and the scroll-to-top + modal-dismiss effect.
  `ThemeToggle.jsx` — add accent-color + density read/write (extend, keep API + events).
- **Endpoints:** none new. `me()` on shell mount (existing).
- **Keep (OURS-ONLY):** ErrorBoundary wrap (K19), flash-free theme stamp in `index.html`,
  theme cross-instance sync (O6), draft autosave/restore.
- **Honesty:** none (no claims rendered yet). Ensure accent/depth tokens don't break the
  disclaimer/triage/urgent color roles.

### Phase 3 — Marketing site

- **Screens:** Landing (D1/O1), Testimonials (D2), Compliance strip (D3), Evidence (D4),
  Privacy (K13), footer.
- **Create:** `EvidencePage.jsx` (page `evidence`), `Testimonials.jsx`,
  `ComplianceStrip.jsx`, `marketing/Section.jsx`, `marketing/Hero.jsx`.
- **Modify:** `HomePage.jsx` (re-skin to design hero/sections, keep "what it is/is not"),
  `AboutPage.jsx` (fold under Help or keep), `PrivacyPolicy.jsx` (re-skin only).
  🔒`styles.css` — APPEND `.mkt-*`, `.evidence-*`, `.testimonial-*`, `.compliance-*`.
- **Endpoints:** `GET /api/behavior-card` (existing) → real metrics on landing + Evidence.
- **Keep (OURS-ONLY):** behavior-card-driven "measured, not claimed" metrics (K20), Privacy
  policy (K13), FailureGallery content can preview here (K14).
- **Honesty:** B1 testimonials illustrative/removed · B2 compliance = roadmap · B3 fix
  "on-device" → server + de-id · B4 ECE wording · B7 ban accuracy hype · B4-numbers: real
  ECE 0.2437, PA 0.807 / AP 0.784, Pneumonia 0.458, best/worst side by side.

### Phase 4 — Console: Dashboard / Upload / Profile / Settings

- **Screens:** Dashboard (D5), Upload (D6), Settings (D9/O7), Profile (O7), accent picker
  (D10), Help (D8).
- **Create:** `Dashboard.jsx` (page `dashboard`) + `KpiTile.jsx`, `Worklist.jsx`,
  `MiniChart.jsx` (inline SVG, no external chart lib — CSP forbids CDNs); `UploadScreen.jsx`
  (page `upload`); `HelpPage.jsx` (page `help`); optional `CommandPalette.jsx` (D12).
- **Modify:** `SettingsPage.jsx` (add toggle groups: theme/accent/density, AI-channel
  toggles [surfaced, but effective only when server flags on], notifications; keep clear-
  identifiers / clear-draft / reset-theme / **LogViewer**). `ProfilePage.jsx` (re-skin,
  keep `me`/`logout`). 🔒`api.js` — APPEND `dashboardStats()` → new `GET /api/stats/summary`
  (optional; else derive client-side from behavior-card + local history). 🔒`styles.css` —
  APPEND `.dash-*`, `.kpi-*`, `.worklist-*`, `.help-*`, `.toggle-*`.
- **Endpoints:** existing `GET /api/behavior-card`, `GET /api/feedback/summary` (model-tuning
  KPI, reuse `FeedbackAdmin` data); **new (optional)** `GET /api/stats/summary` in a new
  `routers/stats.py` returning **only** model behaviour + de-identified session counts
  (no PHI). Worklist = **local session studies** (from `history`/`localStorage`), not a
  server PHI queue.
- **Keep (OURS-ONLY):** LogViewer + logger (K12), FeedbackAdmin model-tuning (K11),
  patient-intake client-only on Upload (K17), draft restore (K19), Help folds InfoPage +
  KnownLimitations + FailureGallery + WhatNotChecked (K14).
- **Honesty:** B5 KPI tiles "Demo data" except behavior-card model stats · B8 no CT/MRI
  accuracy KPI · CT/MRI AI toggles default OFF and labelled research/unvalidated.

### Phase 5 — Workspace (the core clinical surface)

- **Screens:** 3-pane workspace (O2): left tools, center viewer, right AI rail + report
  rail; modality tabs `xray | ct | mri` (keep).
- **Create:** `workspace/WorkspaceLayout.jsx` (3-pane grid + collapsible rails, replaces the
  two-column `layout`/`railsCollapsed` block), `workspace/ToolRail.jsx`,
  `workspace/AiRail.jsx`.
- **Modify:** `Viewer.jsx` (re-skin controls into ToolRail/overlay; **keep every control** —
  heatmap/contour modes, region picker, opacity, zoom/pan, caliper, B/C/invert, fullscreen
  safety badge, attention-map status, confidence bars + threshold slider + live sens/spec,
  calibrated-P/uncal/ECE/AUROC/disposition chips, hi-res poll). `FindingsForm.jsx`,
  `DisagreementPrompts.jsx`, `ReportPanel.jsx`, `FindingExplanation.jsx` (re-skin, O3/O4/O5).
  `CompetenceBanner.jsx`, `TriageBanner.jsx`, `DisclaimerBanner.jsx`, `StudyMetadataStrip.jsx`
  (re-home to workspace header). 🔒`styles.css` APPEND `.ws-*` (keep `.viewer-*`, `.dv-*`,
  `.measure-*` families).
- **Endpoints (existing):** `POST /api/analyze`, `GET /api/localize-hires/{id}`,
  `GET /api/analysis/{id}`, `POST /api/analyze-study`, `POST /api/generate-report`,
  `POST /api/completeness-check`, `POST /api/compare`, `POST /api/feedback`,
  `GET /api/behavior-card`; CT/MRI `POST /api/dicom-*`.
- **Keep (OURS-ONLY):** K1–K5, K8–K11, K15, K16 all live here. Measurement suite (K4) on
  both X-ray Viewer and CT/MRI viewer. Sign-off gate stays mandatory (K9). jsPDF export (K10).
- **Honesty:** B4 raw-vs-calibrated chips + ECE caveat · B9 add explicit **"NOT a normal
  read"** banner on zero-flag X-ray (new; mirrors CADe) · B7 every finding "signal for
  review, not a diagnosis" · triage only off calibrated P (keep).

### Phase 6 — Login + auth security

- **Screens:** Login (D7/O8), optional auth gate.
- **Modify:** `Login.jsx` (rebuild to design; username/password real, SSO/SAML =
  disabled "Roadmap" button, optional 2FA field). `App.jsx`/`AppShell.jsx` — mount Login as
  optional gate driven by `me().auth_enabled` (keep default-open demo when `AUTH_ENABLED=0`).
  🔒`api.js` APPEND `verify2fa()`, `enroll2fa()` if TOTP added. 🔒`main.py` — no middleware
  reorder; register any new auth sub-routes in `auth.py`.
- **Backend:** `auth.py` extensions per Section E (2FA optional TOTP, CSRF token for
  cookie-auth POSTs, cookie flag review, lockout already present). `security.py` header
  review.
- **Endpoints (existing):** `POST /api/login`, `POST /api/logout`, `GET /api/me`;
  **new (optional):** `POST /api/2fa/enroll`, `POST /api/2fa/verify`, `GET /api/csrf`.
- **Keep (OURS-ONLY):** K18 entire security stack (scrypt, HMAC cookie, idle auto-logoff,
  login throttle, rate-limit, seg-launch limit, access-code, CSP/HSTS, audit log). Do not
  regress any of it.
- **Honesty:** B6 SSO = roadmap unless wired · no "bank-grade/military-grade" claims · 2FA
  only shown if actually enrolled.

### Phase 7 — CT/MRI AI + report parity (see Section D for the full plan)

- **Screens:** CT/MRI workspace tab gains a findings→report flow at parity with X-ray, in
  honest research framing.
- **Create:** `workspace/CtReportPanel.jsx` (or generalize `ReportPanel` with a
  `modality`/`source` prop); `models/ct_report.py` inputs.
- **Modify:** `DicomViewer.jsx` (feed confirmed candidates + anatomy measures into a report
  draft), `CandidateFindings.jsx` (Confirm → structured finding), `report.py`/`templates.py`
  (accept CT/MRI research-candidate + measurement inputs), `completeness.py`.
  🔒`api.js` APPEND `generateCtReport()`. 🔒`main.py` register any new route.
- **Endpoints:** reuse `POST /api/generate-report` with a CT/MRI `source` block, OR new
  `POST /api/ct-report`; plus existing `ct-detect`/`mr-detect`/`segment`/`mr-segment`.
- **Keep (OURS-ONLY):** K5–K7 model-free viewer + anatomy overlay + candidate CADe, all
  default OFF; measurement suite (K4); feedback loop (K11).
- **Honesty:** B8 — every CT/MRI finding + report line carries "research candidate /
  unvalidated / not a diagnosis"; **no accuracy numbers** for CT/MRI; report explicitly
  states it summarizes *unvalidated candidates + anatomy measurements*, not a diagnosis.

---

## D. CT/MRI AI + report parity plan

Target: CT/MRI reaches **feature** parity with X-ray's findings→report flow, while staying
**honestly sub-parity in claims** (no calibrated probabilities, no validated detection, no
accuracy numbers — this gap is stated, not hidden).

**Backend**
1. New input schema `backend/app/models/ct_report.py`: `{modality, series_id, candidates[]
   (from ct/mr-detect, each validated=False/research_only=True/score), anatomy_measures[]
   (from segment volumes), roi_stats[] (from dicom-roi), clinician_confirmed[], history}`.
2. Extend `routers/report.py` (or new `routers/ct_report.py`, register in `main.py`):
   `POST /api/ct-report` → `services/templates.py` + `services/llm.py` produce the same
   3-tab draft (clinical / patient / differentials) but from **confirmed candidates +
   measurements**, never from a probability. Hard-inject `CT_DETECT_DISCLAIMER` /
   `CT_OVERLAY_DISCLAIMER` into every draft; forbid probability/diagnosis phrasing in the
   template layer (reuse the client `assertNoDiagnosisFields` guard server-side too).
3. `services/completeness.py` — add CT/MRI "what was NOT assessed" list (no validated
   disease coverage) so the completeness gate stays honest.
4. No new model / no calibration for CT/MRI. Candidates stay classical, deterministic,
   `validated=False`. Anatomy overlay stays non-diagnostic.

**Frontend**
5. `CtReportPanel.jsx` (or `ReportPanel` with `modality` prop) mounted in the CT/MRI
   workspace tab: confirmed candidates + measurements → 3-tab report, sign-off gate, AI-vs-
   edited provenance, jsPDF export — **reusing K9/K10 machinery**.
6. `CandidateFindings.jsx` Confirm action writes a structured CT/MRI finding into the report
   draft (mirrors X-ray `DisagreementPrompts` accept flow).
7. `api.js` APPEND `generateCtReport()`.

**Honesty framing (mandatory on every CT/MRI surface):** RED research banner; "RESEARCH
candidate" burned onto review slices (keep); every report says "summary of unvalidated
research candidates and anatomy measurements — NOT a diagnosis, NOT triage"; zero-candidate
state keeps the existing "This is NOT a 'normal' result — the detector is unvalidated and
may miss disease." No AUROC/ECE/accuracy tile anywhere for CT/MRI (none exist).

---

## E. Login + auth security hardening plan (prototype-appropriate, high bar, no fabricated certs)

Building on the **already-present** stack (`auth.py`, `security.py`), the delta:

1. **Password hashing** — keep **salted scrypt (N=2^14)**; mark legacy unsalted SHA-256
   accept path deprecated and add a startup warning; document upgrade path. (Already done —
   preserve, don't regress.)
2. **Session/cookie flags** — confirm `HttpOnly`, `Secure` (require in prod / behind HTTPS),
   `SameSite=Lax` default (offer `Strict` via env). Keep absolute TTL (12h) + **idle
   auto-logoff (15m)** (HIPAA §164.312(a)(2)(iii)). Rotate `SESSION_SECRET` = revocation.
3. **CSRF** — add a double-submit CSRF token for cookie-authenticated state-changing POSTs:
   `GET /api/csrf` issues token; middleware checks `X-CSRF-Token` vs cookie on protected
   POSTs when `AUTH_ENABLED`. (New, additive in `security.py`.)
4. **Rate-limit / lockout on login** — keep per-IP brute-force throttle (`LOGIN_MAX_ATTEMPTS`
   10 / `LOGIN_WINDOW_SECONDS` 300 → 429); add optional per-username lockout with backoff;
   keep constant-time verify + dummy-hash timing burn for unknown users.
5. **Secure headers** — keep CSP (self + data/blob, `object-src none`, `frame-src none`),
   HSTS, nosniff, no-referrer, SAMEORIGIN, COOP same-origin, Permissions-Policy. Review CSP
   against new inline SVG charts (no CDN — all inline, compliant).
6. **2FA** — **real, optional TOTP** (`pyotp`, stdlib-friendly): `POST /api/2fa/enroll`
   (QR/secret), `POST /api/2fa/verify` at login; store per-user flag in `AUTH_USERS`. Only
   surface "2FA enabled" when actually enrolled (B6).
7. **SSO / SAML** — **roadmap only** for the prototype: Login shows a disabled "Sign in with
   SSO (roadmap)" button. Do not stub a fake IdP. Document real integration path (OIDC/SAML
   via an IdP) in `docs/SECURITY_NOTES.md`.
8. **Audit** — keep PHI-free audit events (user+method+path+ip+status, §164.312(b)); add
   login-success/failure + 2FA events.
9. **No fabricated certifications** anywhere in the UI (ties to B2): the auth screen may say
   "session controls aligned to HIPAA §164.312 technical safeguards", never "HIPAA
   certified / SOC 2 compliant."

Update `docs/SECURITY_NOTES.md` + `SECURITY_REVIEW.md` with the CSRF + 2FA additions.

---

## F. Accuracy-verification research plan (5+ agent research team)

Reproducible on the on-repo harness (`validation/run_validation.py`, `.venv` python),
extending `inv_safety.md §3`. Keep every number honest and CI-bounded.

**Agent split (5+):** (1) Detection-accuracy, (2) Abstain/selective-prediction,
(3) Calibration, (4) Subgroup/robustness, (5) CT/MRI CADe + localization,
(6) Lifecycle/FDA-readiness mapping.

**(a) Measure real detection accuracy**
- Datasets (independent, multi-site): NIH ChestX-ray14 (have), + external **PadChest**,
  **VinDr-CXR** (radiologist boxes), **RSNA Pneumonia**, **SIIM-ACR Pneumothorax** (pixel
  truth for the two critical labels). License-clean only (keep MIMIC/CheXpert exclusion
  policy explicit).
- Metrics per label with **95% bootstrap CIs**: AUROC + AUPRC; sensitivity & specificity at
  the operating point; **PPV/NPV at realistic prevalence** (not test-set prevalence). New
  harness modules under `validation/`: extend `run_validation.py`, add `ci_bootstrap.py`,
  `external_eval.py`. Publish into `behavior_card.json` (extend schema; card is already the
  source of truth for `/api/behavior-card` and `_label_auroc`).
- Localization: extend `pointing_game.py` (hit-rate) + IoU vs VinDr/RSNA/SIIM boxes.
- **Baseline to beat (real, current):** ECE 0.2437, PA-AUROC 0.807 / AP 0.784, Pneumonia
  0.458/sens 0.0 (n=2), Cardiomegaly 0.906, localization hit-rate 0.0 for Atelectasis &
  Pneumonia. Re-measure these on external data with CIs.

**(b) Prove the abstain/normal path prevents incorrect diagnosis**
- Build an explicit **OOD/negative-control set**: non-chest radiographs (knee/hand/abdomen/
  pelvis) **as PNG** (closes gap #3 — PNG has no modality tag), CT/MR-as-PNG, phone photos,
  screenshots, synthetic/test patterns, inverted/rotated/pediatric/lateral CXR (DICOM-tagged
  **and** stripped-to-PNG).
- Treat the OOD gate as a **binary classifier** and measure its ROC: **catch rate** on OOD
  vs **over-abstain rate** on real CXR. Choose `OOD_ABSTAIN_THRESHOLD` at a pre-registered
  operating point (target ≥0.99 catch on hard-OOD at ≤1% over-abstain). New:
  `validation/abstain_roc.py`.
- **Selective-prediction / risk–coverage curves** (`risk_coverage.py` exists — extend):
  selective risk on the covered set ≤ pre-registered bound = the formal "when it answers,
  error is bounded; else it abstains" statement.
- Do the same tradeoff curve for **every hand-set gate constant**: `ANATOMY_MIN_OVERLAP`,
  `ATTENTION_BG_*`, `AE_ERR_*`, `OOD_CAUTION_THRESHOLD`, `PRIORITY_MIN_CALIBRATED_P`. **Add
  the missing anatomy-gate FN/FP section to `behavior_card.json`** (gap #6, currently
  unmeasured — a safety layer that can delete true findings must publish its own FN cost).
- **NPV of the no-flag state** at realistic prevalence → publish; pair with the new UI
  "NOT a normal read" non-claim (B9). This is the core proof of "does not *assert* normal."

**(c) Map gaps → FDA-readiness**
- Per-gap risk table (ISO 14971): each `inv_safety.md §2` gap → mitigation → measured
  residual risk. Lock intended use + predicate (`INTENDED-USE.md`); version + re-audit
  models/calibration maps per bump; IEC 62304 lifecycle doc.
- Reader study (MRMC ROC/AFROC, clinician-with-AI vs alone) named as the required device-
  claim step (out of prototype scope, on the roadmap).
- Post-market monitoring: drift, abstain-rate, subgroup performance, and the confirm/dismiss
  feedback loop (`feedback_stats.py` / refit) with **human review before any threshold
  change**.
- Reproducibility: everything runs from `validation/` with pinned `requirements-dev.txt` and
  the `.venv` python; every published number carries n, dataset, date, and CI.

**Honesty invariant for the whole program:** no number reaches the UI unless it is in
`behavior_card.json`, carries its caveat, and was produced by the on-repo harness. CT/MRI
gets a *coverage/what-was-not-assessed* report, **not** an accuracy number, until a
validated detector with ground truth exists.

---

## Build order summary
Phase 2 (tokens+shell) → 3 (marketing) → 4 (console) → 5 (workspace) → 6 (auth) →
7 (CT/MRI parity), with the research program (F) running in parallel to feed real numbers
into Phases 3–5. Shared files 🔒 `styles.css` / `App.jsx` / `api.js` / `main.py` are
append-only after Phase 2 claims their structure — serialize any edits to them.
