# Dependency & Supply-Chain Scanning

Covers Security task 4 of `docs/FULLSTACK_IMPLEMENTATION_PLAN.md` §4: add
`pip-audit` / `npm audit` + Dependabot in CI. This doc explains how to run the
scans, records the current findings with a triage note, and describes the CI +
Dependabot wiring.

RadAssist stays honest: the scans below are the real output run against the
pinned `backend/requirements.txt` and the frontend `package-lock.json`. Nothing
here claims a clean bill of health it doesn't have.

---

## How to run the scans locally

### Python (backend) — pip-audit

`pip-audit` checks installed/declared Python packages against the PyPI Advisory
Database and OSV.

```bash
# from repo root, using the backend venv
backend/.venv/Scripts/pip.exe install pip-audit          # one-time
backend/.venv/Scripts/pip-audit.exe -r backend/requirements.txt
# or, module form:  backend/.venv/Scripts/python.exe -m pip_audit -r backend/requirements.txt
```

Note: `torch` / `torchvision` are intentionally NOT in `requirements.txt` (they
install as CPU-only wheels in the Dockerfile, and the test suite mocks the vision
model). They are therefore out of scope for this file-based audit — audit them
separately in the container image if/when a real deploy is built.

### Frontend — npm audit

`npm audit` checks the resolved dependency tree in `package-lock.json` against the
GitHub Advisory Database. Read-only — **do not run `npm audit fix`** (it can push
a semver-major bump; bumps are deliberate, via Dependabot PRs + review).

```bash
cd frontend
npm audit --omit=dev        # production dependency tree only
npm audit                   # full tree incl. devDependencies (vite, plugin-react)
```

`--omit=dev` (the modern spelling of the deprecated `--production`) is what ships
to users, so that's the primary gate.

---

## Current findings (scanned 2026-07-18)

### Python — `pip-audit -r backend/requirements.txt`

**No known vulnerabilities found.** All runtime deps are pinned (fastapi,
uvicorn, pydicom, pillow, numpy, pandas, scikit-image, scipy, torchxrayvision,
grad-cam, opencv-python-headless, google-generativeai, groq, python-dotenv,
sqlmodel, SQLAlchemy, alembic) and none currently carry an advisory.

Triage: nothing to do. Keep pins current via Dependabot; re-audit on every bump.

### Frontend — `npm audit --omit=dev`

| Package     | Installed | Severity  | Direct/Transitive          | Advisory range | Fix                          |
|-------------|-----------|-----------|----------------------------|----------------|------------------------------|
| `jspdf`     | 2.5.2     | **critical** | **direct** (`dependencies`) | `<= 4.2.0`     | `jspdf@4.2.1` (semver-major) |
| `dompurify` | 2.5.9     | moderate  | transitive (via `jspdf`)   | `<= 3.4.10`    | ships inside `jspdf@4.2.1`   |

Two findings, one root cause: **`jspdf`**. `dompurify` is pulled in only as a
`jspdf` dependency, so fixing `jspdf` resolves both. Summary: `moderate: 1,
critical: 1, total: 2`.

Representative `jspdf` advisories (13 rolled into the one package finding):

- **Critical** — Local File Inclusion / Path Traversal (GHSA-f8cm-6447-x5h2)
- **Critical** — HTML Injection in New Window paths (GHSA-wfv2-pwc8-crg5)
- High — ReDoS (GHSA-w532-jxjh-hjhj); DoS (GHSA-8mvj-3j78-4qmw)
- High — PDF/Object injection → arbitrary JS in AcroForm / addJS / FreeText
  (GHSA-pqxr-3g65-p328, GHSA-9vjf-qc39-jprp, GHSA-p5xg-68wr-hm3m,
  GHSA-7x6v-j9x4-qf24)
- High — DoS via malicious BMP/GIF image dimensions (GHSA-95fx-jjr5-f39c,
  GHSA-67pg-wm7f-q7fj)
- Moderate — XMP metadata injection (GHSA-vm32-vv63-w422); addJS race condition
  (GHSA-cjw8-79x6-5cj4)

`dompurify` (transitive): a cluster of moderate/low XSS-bypass and
prototype-pollution advisories, all in the `< 3.4.x` range shipped by the old
`jspdf`.

#### Triage: `jspdf` — **fix, but deliberately (owned by the frontend agent)**

- **Exposure in RadAssist:** `jspdf` is used **client-side only**, to generate
  the PDF report export in the browser from data the user already sees. There is
  no server-side jsPDF rendering and no untrusted third party feeding the export
  path. That materially lowers the practical risk of the injection/LFI advisories
  (they largely assume attacker-controlled input to the PDF builder), but it does
  **not** make them irrelevant — a malicious/crafted study or report field could
  still reach the exporter.
- **Recommendation: fix now, via a reviewed PR.** The remediation is a
  **semver-major** bump (`jspdf@2.5.2` → `4.2.1`), so it needs an API-compat
  review of the export code, not an automatic `audit fix`. This file does NOT
  auto-bump it (out of this task's file scope, and majors must be validated). The
  jsPDF v3/v4 API changed enough that the export module and the report snapshot
  tests should be re-verified after the bump.
- **Until bumped:** accepted-with-reason on the basis of client-only usage +
  no-untrusted-input export path. CI surfaces it on every run (see below) so it
  stays visible and doesn't quietly rot.

Status classification:
- Python findings: **none** → nothing to fix.
- `jspdf` (+ transitive `dompurify`): **fix now** (semver-major, reviewed PR by
  the frontend owner); interim status = accept-with-reason (client-only export).

---

## CI setup — `.github/workflows/ci.yml`

Runs on every push and pull request. Jobs:

1. **Backend tests (DB off)** — installs `requirements.txt` +
   `requirements-dev.txt`, runs `pytest backend/tests -p no:warnings -q` with
   **no `DATABASE_URL`** (the zero-config demo path). torch/torchvision are not
   installed — the suite mocks the model.
2. **Backend tests (DB on, sqlite)** — same, but with
   `DATABASE_URL=sqlite:///./_ci.db` to exercise the opt-in persistence layer,
   then removes the SQLite file.
3. **Frontend build** — `npm ci` + `npm run build`.
4. **Security scans** — `pip-audit -r backend/requirements.txt` and
   `npm audit --omit=dev`, each uploading a report artifact.

### Why the audit steps are non-blocking (for now)

The `security-scans` job runs on every push/PR but is marked
`continue-on-error: true`, so a newly-published transitive advisory (like the
`dompurify`/`jspdf` cluster above) can't wedge every unrelated PR on day one. The
findings are still **visible**: the step output and the uploaded
`pip-audit-report.txt` / `npm-audit-report.json` artifacts show them on every run.

**Make them blocking once triaged.** After the `jspdf` bump lands (or the accept
decision is formally signed off), remove the `continue-on-error: true` lines in
`ci.yml`. For `npm audit`, the blocking form is
`npm audit --omit=dev --audit-level=high` (fail on high+); for `pip-audit`, drop
the flag so a non-zero exit fails the job. There is a matching comment at each
step in the workflow.

---

## Dependabot — `.github/dependabot.yml`

Weekly (Monday) update PRs for three ecosystems:

- **pip** — `/backend` (`requirements.txt`). Minor/patch bumps grouped into one
  PR (`backend-minor-patch`); majors come individually so they get real review.
- **npm** — `/frontend` (`package-lock.json`). Same grouping
  (`frontend-minor-patch`). The `jspdf` major will arrive as its own PR — that's
  the intended path to remediate the finding above with tests in the loop.
- **github-actions** — `/` (keeps the action versions in `ci.yml` current).

Each Dependabot PR is gated by the CI above: tests must stay green in both DB
modes and the frontend must still build before merge.

---

## Not in scope here (future supply-chain work)

- **SBOM** — `docs/FULLSTACK_IMPLEMENTATION_PLAN.md` §4 also lists generating an
  SBOM. `pip-audit` can emit CycloneDX (`--format cyclonedx-json`) and
  `cyclonedx-npm` covers the frontend; wire these in when an artifact/signing
  pipeline exists.
- **Container image audit** — audit the built Docker image (which *does* include
  torch/torchvision) separately from this file-based `requirements.txt` audit.
- **Backend has no `DATABASE_URL` in CI's DB-off job by construction** — that is
  the guarantee the zero-config demo depends on; don't add one to that job.
