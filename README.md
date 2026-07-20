---
title: RadAssist
emoji: "\U0001FA7B"
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
---

# RadAssist — AI Radiology Assistant & Report Generator

A **non-clinical, research/decision-support prototype** for radiology: **the AI drafts and
highlights; a licensed clinician reviews, corrects, and signs.** The model suggests — the
clinician decides.

> ⚠️ **For decision support only — not a diagnosis.** Every output (findings, highlighted
> regions, differentials, CT/MRI candidates) is AI-generated and may be wrong. It must be
> reviewed, corrected, and approved by a licensed radiologist before any clinical use.
> RadAssist is **not FDA-cleared and is not a medical device.** Use public / de-identified
> images only. Read [INTENDED-USE.md](INTENDED-USE.md) and
> [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md) first.

---

## Contents

- [What it is / is not](#what-it-is--is-not)
- [Features](#features)
- [The app, screen by screen](#the-app-screen-by-screen)
- [Quick start](#quick-start)
- [How to use it](#how-to-use-it)
- [Demo login (test credentials)](#demo-login-test-credentials)
- [Checking the results (tests, build, accuracy, security)](#checking-the-results)
- [Configuration reference](#configuration-reference)
- [Optional: database persistence](#optional-database-persistence)
- [Optional: LLM report formatter](#optional-llm-report-formatter)
- [Architecture](#architecture)
- [Security](#security)
- [Project structure](#project-structure)
- [Documentation index](#documentation-index)
- [Data sources](#data-sources)
- [Accuracy & limitations (honest)](#accuracy--limitations-honest)

---

## What it is / is not

- **Is:** a research/education decision-support workspace with *measured, transparent* behaviour
  — every number is either measured on a public benchmark or clearly labelled "not calibrated /
  unvalidated". It abstains on out-of-distribution input instead of guessing.
- **Is not:** a diagnostic device. Not FDA-cleared or CE-marked. The chest X-ray model is a
  high-sensitivity/low-precision *review prompt*, reliable for only a few findings; CT/MRI AI is
  explicitly **unvalidated research**. "No flag" is **never** "normal".

---

## Features

### Chest X-ray AI
- **18-pathology screening** — a pretrained **TorchXRayVision DenseNet-121 ensemble** scores
  nodule, mass, effusion, pneumothorax, consolidation, pneumonia, cardiomegaly, atelectasis,
  edema, and more. Shown as a **ranking score** (a calibrated P≈ only where one is measured),
  never a diagnosis.
- **Grad-CAM region highlighting** — an attention heatmap/contour for the top finding, labelled
  "region of model attention — not a lesion boundary".
- **Abstain / OOD gate** — refuses non-chest, synthetic, or off-distribution images rather than
  emit a confident but meaningless flag; a **competence banner** downgrades low-quality films.
- **"NOT a normal read" safeguard** — a zero-flag film is never presented as normal; the app
  shows the measured negative-predictive-value of the no-flag state (≈0.82, in-distribution).
- **Per-label reliability gating** — findings with too few positives or at/below-chance AUROC
  (e.g. Pneumonia) are marked *"cannot exclude / not reliably measured"* and don't drive triage.
- **Two-tier triage** — high-confidence critical findings (calibrated-P gated) raise a
  "needs priority review" banner.

### CT / MRI (viewer + opt-in AI)
- **Full DICOM viewer** — windowing/presets, slice navigation + mouse-wheel, **cine**, **2-up
  compare**, MRI **series rail** (T1/T2/FLAIR/DWI/ADC auto-labelled from coded tags — *verify*),
  raw 16-bit window/level canvas, burned-in-annotation warning.
- **Measurement suite** — length, angle, and **HU / a.u. ROI** statistics computed on the true
  16-bit intensity, with undo/redo, a measurements list, and jump-to-slice.
- **Opt-in AI channels (default OFF, server-flag gated):** an **anatomy overlay** that labels
  organs/tissue (never disease) and an **unvalidated research candidate detector** (classical/
  deterministic; every candidate `validated=False`, "research use only — not a diagnosis").
- **CT/MRI research report** — a structured summary of confirmed candidates + measurements,
  server-guarded against any diagnostic/probability language, with sign-off + PDF export.

### Reporting & review
- **Findings form** — AI flags arrive **unchecked by default**; the clinician confirms, edits, or
  dismisses each. Free-text supports **voice dictation**.
- **Three-part report** — clinical report (Technique / History / Comparison / Findings /
  Impression / Recommendations), an 8th-grade **patient summary**, and reference **differentials**.
  Fully editable; AI-vs-edited provenance tracked; a completeness check runs before sign-off.
- **Mandatory sign-off** — nothing is finalized or exported until a named reviewer attests.
- **Local PDF export** — generated in-browser (jsPDF); downloads to your device (named with the
  patient), **never stored on the server**.
- **Prior-study comparison** — per-finding stable / new / worsened / improved / resolved changes.
- **Reviewer feedback loop** — confirm/dismiss feedback feeds a transparent operating-point
  refit (no black-box retraining).

### Platform
- **Full app shell** — a marketing site (Home w/ animated 3D hero, About, Help, Evidence) and a
  console (Dashboard w/ KPIs + charts + worklist, Upload, Workspace, Profile, Settings).
- **Theming** — light / dark / system, four **accent** colours, comfortable/compact density
  (flash-free, synced across the app).
- **Accounts & sessions** — optional login with **TOTP 2FA enrollment**, **active-session list +
  revoke** ("sign out of all other devices"), and a demo-login mode (below).
- **Optional database** — durable users/2FA, feedback, and audit (SQLite → Postgres); off by
  default (zero-config).
- **Client diagnostics log** — every API call/timing/error captured locally (viewable in
  Settings), never logging response bodies (no PHI).
- **Evidence page** — the model's real measured behaviour (AUROC, ECE, per-label sensitivity,
  no-flag NPV), served live from the validation harness — *measured, not claimed*.

---

## The app, screen by screen

| Area | Screens |
|---|---|
| **Marketing** | Home (hero + capabilities + modalities + evidence + FAQ), About, Help, Evidence, Privacy |
| **Console** | Dashboard (KPIs, charts, session worklist), Upload, **Workspace** (X-ray analyzer + CT/MRI viewer), Profile (security/2FA/sessions), Settings (theme/accent/prefs/diagnostics) |
| **Auth** | Login (password + optional 2FA; SSO shown as roadmap), demo-login mode |

---

## Quick start

**Prereqs:** Python 3.11+ and Node 18+.

```powershell
# 1) Backend (first run downloads pretrained weights, ~30 MB)
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# 2) Frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** — the Vite dev server proxies `/api` and `/static` to the backend
on `:8000`. Drop a chest X-ray (e.g. from `samples/`) onto the upload panel.

Helper scripts from the repo root: `.\start-backend.ps1` and `.\start-frontend.ps1`.
Production build of the UI: `cd frontend && npm run build` (a `Dockerfile` builds the SPA and
serves it from FastAPI on port 7860 for the Hugging Face Space deploy).

---

## How to use it

**Chest X-ray:**
1. **Upload** a chest radiograph (DICOM `.dcm`, PNG, or JPG) on the Upload screen or the Workspace.
2. The model **analyses** it (or **abstains** with a reason if it isn't a readable chest film).
3. **Review** the AI findings in the right rail — each is a suggestion with a score, a Grad-CAM
   region, and a plain-language explanation. **Confirm / edit / dismiss** each; nothing is a
   finding until you say so. Watch for the **"not a normal read"** and reliability chips.
4. Optionally add **history**, take **caliper** measurements, and **compare a prior** study.
5. Switch to the **Report** tab, generate the clinical / patient / differential text, **enter your
   name + attest**, then **Sign & export PDF**.

**CT / MRI:** open the **CT** or **MRI** tab in the Workspace → drop a DICOM series → window /
scroll / cine / compare / measure. To use AI, enable the (off-by-default) **anatomy overlay** or
**research candidate detector**, confirm any candidates, then generate the **research summary**
(clearly framed as *not a diagnosis*).

**Signing in:** by default the app is an **open demo** (no login). To try the real auth flow, see
the demo login below.

---

## Demo login (test credentials)

RadAssist runs open by default. To experience the real sign-in flow (login → optional 2FA →
console), enable **demo mode**:

```powershell
copy backend\.env.demo backend\.env     # sets AUTH_DEMO_MODE=1, SESSION_COOKIE_SECURE=0
# restart the backend
```

Then **Sign in** with (the login page also shows these + a "Fill demo credentials" button):

| Field | Value |
|---|---|
| Username | `radiologist` |
| Password | `RadAssist-Demo-2026` |

Insecure by design — evaluation only. Full details + production hardening in
[docs/DEMO_LOGIN.md](docs/DEMO_LOGIN.md).

---

## Checking the results

**Backend test suite (294 tests):**
```powershell
# from the repo root — with and without the optional database
.\backend\.venv\Scripts\python -m pytest backend/tests -q
$env:DATABASE_URL="sqlite:///./_t.db"; .\backend\.venv\Scripts\python -m pytest backend/tests -q; del _t.db
```

**Frontend build:**
```powershell
cd frontend; npm run build      # must be green; 0 npm-audit vulnerabilities
```

**Measured model accuracy (the honest numbers):**
- Live in the app on the **Evidence** page and at `GET /api/behavior-card`.
- Regenerate from the validation harness: `python validation/run_validation.py` (see
  [validation/README.md](validation/README.md)); companion analyses include `compute_npv.py`,
  `risk_coverage.py`, `decision_curve.py`, `pointing_game.py`, `perturbation_stability.py`.
- Read the plain-English verdict in [docs/ACCURACY_AND_SAFETY.md](docs/ACCURACY_AND_SAFETY.md).

**Security / dependency scanning:**
```powershell
cd frontend; npm audit --omit=dev             # currently 0 vulnerabilities
.\backend\.venv\Scripts\pip-audit -r backend\requirements.txt
```
See [docs/SECURITY_SCANNING.md](docs/SECURITY_SCANNING.md) and the CI workflow in
`.github/workflows/ci.yml` (runs both test modes + build + audits).

---

## Configuration reference

All configuration is via environment variables (the backend auto-loads `backend/.env`).

| Variable | Default | Purpose |
|---|---|---|
| `AUTH_ENABLED` | `0` | Turn the login gate on (protects PHI-adjacent endpoints). |
| `AUTH_DEMO_MODE` | `0` | Demo login: enables the gate + seeds `radiologist` / `RadAssist-Demo-2026`. |
| `AUTH_USERS` | — | Real users, `name:sha256hex,...` (or `AUTH_USERNAME` + `AUTH_PASSWORD_SHA256`). |
| `AUTH_ADMINS` | — | Comma-separated usernames granted the admin (session-management) role. |
| `SESSION_SECRET` | ephemeral | HMAC signing key. **Required** (min 32 chars) once `AUTH_ENABLED=1`; fail-closed on a weak value in a production posture. |
| `SESSION_COOKIE_SECURE` | `1` | Set `0` for plain-http local dev (else the browser drops the cookie). |
| `ENCRYPTION_KEY` | derived | Fernet key for encrypting 2FA secrets at rest (falls back to a key derived from `SESSION_SECRET`). |
| `DATABASE_URL` | — (off) | Enable persistence, e.g. `sqlite:///./radassist.db` or a Postgres URL. |
| `LLM_PROVIDER` | `none` | `gemini` / `groq` / `ollama` / `none` (template fallback). |
| `CT_DETECT_ENABLED`, `MR_DETECT_ENABLED` | `0` | Server flags for the opt-in CT/MRI candidate detector. |
| `REQUIRE_STRONG_SECRETS`, `PROD` | `0` | Force the production posture (fail-closed secrets) without enabling auth. |

---

## Optional: database persistence

Off by default — the app runs zero-config (env/file/in-memory) with the browser holding drafts +
identifiers. Set `DATABASE_URL` to persist **users + durable 2FA, feedback events, and the audit
log** (PHI-free by construction — no pixels or patient names in the DB).

```powershell
$env:DATABASE_URL="sqlite:///./radassist.db"
# Postgres: swap the URL and add a driver (e.g. psycopg[binary]); versioned via Alembic:
#   cd backend; .\.venv\Scripts\alembic upgrade head
```

See [docs/FULLSTACK_IMPLEMENTATION_PLAN.md](docs/FULLSTACK_IMPLEMENTATION_PLAN.md) §3.

---

## Optional: LLM report formatter

The app works fully without an LLM (a deterministic template produces the report). To use one,
set `LLM_PROVIDER` + a key in `backend/.env`. The LLM **only formats/translates** findings the
clinician and vision model supplied — it never invents findings.

| Provider | Free tier | Setup |
|---|---|---|
| `gemini` | Yes | Key from https://aistudio.google.com/apikey |
| `groq` | Yes | Key from https://console.groq.com/keys |
| `ollama` | Local/offline | `ollama pull qwen2.5:3b` |
| `none` | — | Built-in template engine (always the fallback) |

---

## Architecture

```
React 18 + Vite SPA            FastAPI backend                    Model / data
─────────────────────         ──────────────────                 ───────────────────
marketing + console      ┌─▶  /api/analyze          ──▶  TorchXRayVision DenseNet-121
workspace (X-ray + CT/MRI)│    → OOD/abstain gate → marker-mask → Grad-CAM → calibration → triage
findings · report · PDF   │   /api/dicom-* (view/roi/raw)   ──▶  CT/MRI viewer (model-free)
theming · logging         ├─▶  /api/segment · /api/*-detect ──▶  opt-in anatomy / research CADe
                          │   /api/ct-report · /api/generate-report ─▶ template / LLM (formats only)
auth · 2FA · sessions ◀───┼─▶  /api/login · /api/2fa/* · /api/sessions* · /api/me
                          └─▶  /api/behavior-card ──▶  validation harness (measured metrics)

Persistence (opt-in via DATABASE_URL): SQLModel → SQLite/Postgres  ·  users/2FA · feedback · audit
Security middleware: CORS → SecurityHeaders(CSP/HSTS) → Auth(HMAC cookie) → AccessCode → RateLimit
```

Patient identifiers stay **client-side only** (browser session storage → the exported PDF), never
sent to or stored by the server.

---

## Security

Strong for a prototype (not certified clinical infrastructure): scrypt password hashing, stateless
**HMAC signed-cookie** sessions (HttpOnly/Secure/SameSite) with **DB-backed revocation**, **TOTP
2FA** (secrets **encrypted at rest**), **double-submit CSRF**, per-account lockout + per-IP
throttle, enumeration-uniform login, session rotation, fail-closed on a weak `SESSION_SECRET`,
CSP/HSTS headers, in-memory **DICOM de-identification**, secondary-capture quarantine, decode
bounds, and PHI-gated static serving. See [docs/SECURITY_NOTES.md](docs/SECURITY_NOTES.md),
[docs/SECURITY_SCANNING.md](docs/SECURITY_SCANNING.md), and
[docs/PRE_DEPLOYMENT_CHECKLIST.md](docs/PRE_DEPLOYMENT_CHECKLIST.md).

---

## Project structure

```
backend/            FastAPI app
  app/
    main.py         app + middleware stack
    auth.py         login / 2FA / sessions / secrets
    db.py           opt-in SQLModel engine (DATABASE_URL)
    routers/        analyze, compare, report, ct_report, detect, feedback, viewer, …
    services/       vision_xray, self_audit (abstain), calibration, triage, store (DB adapter), …
    models/         pydantic schemas + db_models
  tests/            294 tests
  alembic/          DB migrations
frontend/           React + Vite SPA
  src/
    App.jsx         routing + shell
    components/     workspace/, shell/, dashboard/, account/, Viewer, DicomViewer, ReportPanel, …
    styles.css      design tokens + component styles
validation/         accuracy harness → behavior_card.json (served at /api/behavior-card)
docs/               plans, accuracy/safety, FDA readiness, security, demo login, UI audit
```

---

## Documentation index

- [INTENDED-USE.md](INTENDED-USE.md) · [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md) — read first
- [docs/ACCURACY_AND_SAFETY.md](docs/ACCURACY_AND_SAFETY.md) — is the accuracy accurate? does it ever give a wrong diagnosis? (honest verdict) + [docs/research/](docs/research)
- [docs/FDA_READINESS.md](docs/FDA_READINESS.md) — regulatory gap analysis & roadmap
- [docs/DEMO_LOGIN.md](docs/DEMO_LOGIN.md) — demo credentials & how to run
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — **hosting** (Hugging Face Spaces / any Docker host) + production config
- [docs/FULLSTACK_IMPLEMENTATION_PLAN.md](docs/FULLSTACK_IMPLEMENTATION_PLAN.md) — frontend/backend/DB/security/infra plan
- [docs/SECURITY_NOTES.md](docs/SECURITY_NOTES.md) · [docs/SECURITY_SCANNING.md](docs/SECURITY_SCANNING.md) · [docs/PRE_DEPLOYMENT_CHECKLIST.md](docs/PRE_DEPLOYMENT_CHECKLIST.md)
- [docs/UI_AUDIT.md](docs/UI_AUDIT.md) — every control, audited · [docs/IMPROVEMENT_ROADMAP.md](docs/IMPROVEMENT_ROADMAP.md)

---

## Data sources

Use only **public / de-identified** images. Good sources: Open-i / IU-Xray
(Kaggle `raddar/chest-xrays-indiana-university`), the NIH ChestX-ray14 sample
(Kaggle `nih-chest-xrays/sample`), and Radiopaedia teaching cases. **Never upload real patient
data with PHI.**

---

## Accuracy & limitations (honest)

The chest X-ray metrics are **measured on a public in-distribution benchmark and are optimistic**;
real-world performance is lower. The model is reliable only as a **high-sensitivity, low-precision
review prompt** for a few findings (e.g. Effusion, Atelectasis, Consolidation); some critical
labels (e.g. Pneumonia) are at/below chance and are surfaced as "cannot exclude", not diagnoses.
**CT/MRI AI has no measured accuracy at all** — it is unvalidated research. FDA-grade external
validation (multi-site datasets, a reader study, subgroup analysis) is documented as the roadmap
in [docs/FDA_READINESS.md](docs/FDA_READINESS.md) and has **not** been done. Nothing here is a
substitute for a radiologist. See [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md).

— *RadAssist is a research/education prototype. Not FDA-cleared. Not a medical device.*
