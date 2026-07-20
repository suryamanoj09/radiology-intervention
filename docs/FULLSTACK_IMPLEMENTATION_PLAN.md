# RadAssist — Full-Stack Implementation Plan

Maps the "full-stack" layers (Frontend → Backend/APIs → Database → Security → infra)
to **what RadAssist has today, the gap, and the concrete next step**. Honest by
design: RadAssist is a research/decision-support prototype, not a certified clinical
system — this plan says what is real vs aspirational.

Legend: ✅ done · 🟡 partial · ⛔ not started · 🔒 deliberately deferred (needs data/infra we don't have)

---

## 1. Frontend ✅ (mature)

**Have:** React 18 + Vite 6; design-system tokens (light/dark + accent/depth/density); marketing site (Home + 3D three.js hero, About, Help, Evidence), console shell (Sidebar/TopBar/AppShell), redesigned 3-pane workspace, Login; client-side logging + LogViewer; jsPDF export; page-state routing.

**Gaps → steps:**
1. **Code-splitting** — the main bundle is ~1.3 MB (three.js + html2canvas + jsPDF). Step: `React.lazy` + dynamic `import()` for the 3D hero, jsPDF/html2canvas (load only on export), and CT/MRI viewer; add `manualChunks`. Target < 300 KB initial.
2. **Router** — replace the hand-rolled `page` state with `react-router` (real URLs, deep-linking, back-button, `/study/:id`). Medium effort; improves shareability + the "open a specific study" flow.
3. **State** — introduce a light store (Zustand) for cross-screen session state (studies, current analysis, prefs) so search/worklist/notifications share one source instead of prop-drilling through `App.jsx`.
4. **Frontend tests** — Vitest + React Testing Library for the safety-critical surfaces (not-a-normal-read banner, confirm/dismiss gate, sign-off); Playwright smoke for the upload→analyze→report→export flow.
5. **Accessibility + i18n** — audit with axe; extract copy for future localization.

---

## 2. Backend / APIs ✅ (mature)

**Have:** FastAPI, 24+ endpoints, TorchXRayVision DenseNet-121 pipeline, OOD/abstain gate, isotonic calibration, Grad-CAM, CT/MRI viewer + opt-in research CADe + CT/MRI report, validation harness, **244 tests**. OpenAPI auto-docs at `/docs`.

**Gaps → steps:**
1. **API versioning** — prefix `/api/v1` so future changes don't break clients.
2. **Async inference queue** — model inference is CPU-bound and serializes today (single process). Step: move heavy jobs to a task queue (Celery/RQ + Redis, or FastAPI `BackgroundTasks` for light cases) with a job-status endpoint the frontend polls — decouples request latency from model time and enables horizontal scaling.
3. **Structured request IDs + tracing** — attach a correlation id per request, thread it into logs and the frontend logger.
4. **Rate-limit + quota per API key** for any future multi-tenant use.
5. **Contract tests** — schema-validate every response (pydantic already helps); add golden-file tests for the report generators.

---

## 3. Database ⛔ → **top implementable next step**

**Have today: NO database.** State lives in: env vars (`AUTH_USERS` for credentials), JSON/flat files (`behavior_card.json`, audit log, feedback stats), in-memory dicts (2FA enrollments, rate-limit counters, sessions are stateless-signed cookies), and the browser (`localStorage`/`sessionStorage` for drafts + patient identifiers). This is fine for a single-process demo but doesn't persist, scale, or survive a restart.

**Plan — add a database, PHI-safe:**
- **Engine:** SQLite for the demo/dev (zero-config, file-based) → PostgreSQL for any real deployment. Use **SQLModel** (SQLAlchemy + pydantic) + **Alembic** migrations.
- **Schema (no PHI — patient identifiers stay client-side):**
  - `users` (id, username, scrypt hash, role, 2fa_secret, created_at, disabled) — replaces env `AUTH_USERS`, makes 2FA enrollment durable.
  - `sessions` (optional server-side revocation list — today logout can't force-revoke a stolen cookie).
  - `feedback_events` (id, image_hash, label, action confirm/dismiss, reviewer, ts) — replaces the file-based feedback loop; powers the threshold refit + FeedbackAdmin.
  - `audit_log` (id, actor, action, path, ts, ip_hash) — durable, queryable audit (replaces the flat file).
  - `report_drafts` (id, owner, study_hash, structured_json, patient_ref?, ts) — **server-side saved drafts** so "save report with patient name" survives a browser wipe (with an explicit opt-in, since it introduces identifiers — default stays client-only).
  - `behavior_card_runs` (versioned validation snapshots) — history of measured metrics instead of one JSON.
- **PHI boundary:** the DB stores model/feedback/audit data and de-identified study hashes — **never raw pixels or patient names by default**. If server-side named drafts are enabled, they go in an encrypted column with a clear consent gate.
- **Steps:** (1) add SQLModel + a `db.py` engine/session; (2) migrate `users` + 2FA + feedback + audit first (highest value); (3) Alembic baseline; (4) keep the file/env paths as a fallback when `DATABASE_URL` is unset (so the zero-config demo still works).

---

## 4. Security 🟡 (strong for a prototype)

**Have:** scrypt password hashing, stateless HMAC signed-cookie sessions (HttpOnly/Secure/SameSite), TOTP 2FA (stdlib), double-submit CSRF, per-account lockout + per-IP throttle, enumeration-uniform login, session rotation (anti-fixation), CSP/HSTS headers, in-memory DICOM de-identification, secondary-capture quarantine, decode-concurrency limit, PHI-gated `/static`, access-code header option. Red-teamed. Optional auth (open-demo by default).

**Gaps → steps:**
1. **Secrets management** — `SESSION_SECRET`/`AUTH_USERS` come from env; document + integrate a secrets manager (Docker secrets / cloud KMS) for real deploys; enforce a strong random `SESSION_SECRET` (fail-closed if default in prod).
2. **Session revocation** — needs the DB `sessions` table (§3) so logout / admin can kill a live session (today the signed cookie is valid until idle-expiry).
3. **Encryption at rest** — once a DB exists, encrypt sensitive columns; TLS everywhere in transit (reverse proxy, §infra).
4. **Dependency + supply-chain** — add `pip-audit`/`npm audit` + Dependabot in CI; generate an SBOM.
5. **Pen-test cadence + threat model doc** — formalize the existing `SECURITY_NOTES.md` into a living threat model; schedule periodic review.
6. **Clinical safety = security here** — the abstain/not-a-normal-read guarantees (`docs/ACCURACY_AND_SAFETY.md`) are part of the security posture: never emit a confident wrong diagnosis.

---

## 5. Infra layers 🔒 (deferred — cloud/on-prem scope)

Per the agreed scope, these are deferred until the app is complete; here's the target so it's not a black box.

- **Containers** — a `Dockerfile` (multi-stage: build frontend → serve via the FastAPI app) + `docker-compose.yml` (app + Postgres + Redis). Makes on-prem "one command."
- **Servers / Networking** — reverse proxy (Caddy/nginx) terminating TLS, gzip/br, security headers at the edge; the app behind it on a private network.
- **Cloud Infrastructure** — dev on Hugging Face Space (current); prod options: Render/Fly.io (simple) or AWS ECS/Fargate + RDS (scale). IaC via Terraform for repeatability.
- **CI/CD** — GitHub Actions: on PR → `pytest` (244) + `npm run build` + `pip-audit`/`npm audit` + lint; on main → build image + deploy. Block merge on red.
- **CDN** — serve the static frontend bundle + fonts from a CDN; cache-bust on release.
- **Monitoring & Logging** — health endpoint (have) + structured server logs + error tracking (Sentry) + basic metrics (Prometheus/Grafana or the platform's built-in). Alert on error-rate/latency.
- **Backups & Recovery** — automated Postgres dumps (once §3 lands) with tested restore; documented RTO/RPO; the model weights + validation artifacts are reproducible from the harness.

---

## Recommended order (what to build next)
1. **Login demo + test credentials** (this loop) — makes the auth flow experienceable.
2. **Database (§3)** — biggest capability unlock: durable users/2FA, persisted feedback + audit, optional server-side named report drafts.
3. **Frontend code-splitting + router (§1)** — perf + deep-linking.
4. **Async inference queue (§2)** — removes the single-process bottleneck.
5. **Containerize + CI (§5)** — when moving toward a real deployment.

Nothing here changes the honesty posture: RadAssist stays a decision-support prototype, and any new persistence keeps PHI client-side by default.
