# RadAssist — Functional UI Audit (read-only findings)

Scope: React frontend at `frontend/src`. This is an audit — no code was changed.
Every claim is anchored to `file:line`. Fixes are proposed, not applied.

---

## Summary table

| # | Control / area | State | Root cause (file:line) |
|---|----------------|-------|------------------------|
| 1 | TopBar "Search studies in session" | **Dead** | `App.jsx:310-323` renders `<AppShell>` without `onSearch`; prop is optional and never passed. |
| 2 | Notifications bell | **Dead (decorative)** | `TopBar.jsx:95-112` has no `onClick`; `hasAlerts` never passed (`App.jsx:310-323`). |
| 3 | Upload → analyze → workspace | **Works, with rough edges** | `App.jsx:203-211` navigates immediately; `UploadScreen.jsx` queue never resolves. |
| 4 | PDF export | **Client download only** | `ReportPanel.jsx:88-178` uses `doc.save()`; filename uses `image_id`, not patient. |
| 5 | Save report WITH patient name | **Gap** | Patient name wiped on analyze (`App.jsx:126`); PDF filename ignores it (`ReportPanel.jsx:178`). |
| 6 | Stale analysis after a refused upload | **Confirmed bug** | `handleUpload`/`handlePriorUpload` catch blocks don't clear prior state (`App.jsx:134-139, 156-162`). |
| 7 | Other dead/degraded controls | Several minor | See section 7. |

---

## 1. SEARCH — TopBar "Search studies in session"

**Wiring trace**
- Input renders and calls the prop on every keystroke: `TopBar.jsx:77-88` → `onChange={(e) => onSearch && onSearch(e.target.value)}` (line 81). The `onSearch &&` guard means an unset prop is a silent no-op.
- `AppShell` forwards it: `AppShell.jsx:49` destructures `onSearch`, `AppShell.jsx:70` passes `onSearch={onSearch}` to `TopBar`.
- **App never provides it.** `App.jsx:310-323` mounts `<AppShell route title user onNav items themeSlot>` — no `onSearch`, no `hasAlerts`. So `onSearch` is `undefined` all the way down and typing does nothing.

Confirmed dead. The component author even flagged it: `TopBar.jsx:18` "Safe no-op stub for now; wire to session filtering later."

**What session study state actually exists to search over**
- `analysis` — the single current study (`App.jsx:35`). Contains `image_id`, `findings[]` (each `{label, probability, ...}`), `triage`, `competence`, `view`, `top_finding`.
- `prior` — the prior study for comparison (`App.jsx:36`).
- `sessionStudies` — derived worklist, currently `analysis ? [analysis] : []` (`App.jsx:168`).
- `structured` — clinician-confirmed findings map (`App.jsx:40`).
- `history` — clinical-history draft text (`App.jsx:41`).
- `patient` — client-only identifiers (name/age/phone), sessionStorage (`App.jsx:54`).
- A `radassist_report_session` localStorage draft (`App.jsx:93-113`).

There is **no server PHI worklist** — the honest search corpus is exactly the in-session study/studies plus the confirmed findings and history draft.

**Concrete fix**
1. In `App.jsx`, add `const [studyQuery, setStudyQuery] = useState('')`.
2. Pass `onSearch={setStudyQuery}` to `<AppShell>` (`App.jsx:310-323`).
3. Build a filter over `sessionStudies` (extend it to hold all analysed studies, not just the latest — keep an array in state) matching the query against: `image_id`/ANON token, each `findings[].label`, `triage`, `competence`, and `history`. On the Dashboard, filter `rows`; in the workspace, dim/scroll to matching finding cards.
4. Minimum honest version (matches the current single-study model): treat the search as a **findings filter** — pass `studyQuery` into the Dashboard `Worklist`/AiRail so it filters the finding list of the current study, and show a "no matches in this session" state. Keep the existing "client-only, non-PHI" copy at `TopBar.jsx:8-10`.

---

## 2. NOTIFICATIONS BELL

**State:** decorative only. `TopBar.jsx:95-112` — the `<button>` has `aria-label`, hover state, and an optional unread dot gated on `hasAlerts`, but **no `onClick`**. `hasAlerts` defaults to `false` (`TopBar.jsx:43`) and is never passed by `App.jsx`. Clicking does nothing; the dot never appears.

**Honest, non-fabricated behavior it could have** (all derivable from real state, no invented alerts):
- Unread dot (`hasAlerts`) driven by real conditions: `analysis?.triage === 'urgent'`, `analysis?.competence === 'abstain'`, or `draftRestored === true`.
- `onClick` opens a small popover listing only true, current notices:
  - "Current study triaged **URGENT** — awaiting your sign-off" (from `analysis.triage` / `analysis.triage_reasons`).
  - "Study **abstained** (off-domain) — not scored" (from `analysis.competence`).
  - "Restored an unsaved draft from this browser" (from `draftRestored`, `App.jsx:90`), with a Dismiss action reusing `onDismissDraft`.
  - Empty state: "No notifications for this session."

**Fix:** add `onClick`/`items` props to `TopBar`, compute an `alerts` array in `App.jsx` from `analysis.triage`, `analysis.competence`, and `draftRestored`, pass `hasAlerts={alerts.length > 0}` and the list down through `AppShell`.

---

## 3. UPLOAD — end-to-end trace

**Path:** `UploadScreen.pick()` (`UploadScreen.jsx:49-53`) → `onAnalyze(file)` → `App.jsx:206` `onAnalyze={(file) => { handleUpload(file); setPage('app') }}` → `handleUpload` (`App.jsx:115-140`) → `analyzeImage` (`api.js:29`) → `setAnalysis` → workspace renders.

**Verdict:** the core path **works** — a picked/dropped file is analysed and the workspace shows the result. Rough edges:

- **Queue row never resolves / "Analysing…" is a flash.** `onAnalyze` calls `setPage('app')` synchronously right after firing the async `handleUpload` (`App.jsx:206`). `UploadScreen` unmounts immediately, so the live queue row (`UploadScreen.jsx:187-222`, hard-coded label "Analysing…" at line 211) and its "Clear" button (`UploadScreen.jsx:167-175`) are effectively **unreachable** — the user never sees success/failure reflected on the upload screen. The `picked` state and the indeterminate progress bar are dead UI in practice.
- **No success/error surfaced on the upload screen.** Because we navigate away, a 422/abstain is only visible later in the workspace (`WorkspaceLayout.jsx:117` error bar / `129-137` abstain card). The upload screen itself can't say "rejected."
- **`.dcm` accepted but chest-only messaging.** `ACCEPT` includes `.dcm,.dicom` (`UploadScreen.jsx:29`) and the copy says "chest X-ray only" (`:121, :158`) — consistent, but any non-chest DICOM will silently abstain/throw downstream with no upfront hint.

**Fix options:** either (a) don't navigate until `handleUpload` resolves — make `onAnalyze` await and only `setPage('app')` on success, showing the queue row transition to Done/Failed on the upload screen; or (b) keep instant navigation but drop the pretense — remove the never-seen queue/Clear UI. Option (a) is the better UX and makes the existing queue markup real.

---

## 4. PDF STORAGE

**Confirmed: purely client-side download, no server copy.**
- `ReportPanel.exportPdf()` (`ReportPanel.jsx:88-179`) builds the PDF in-browser with jsPDF (`import { jsPDF } from 'jspdf'`, line 2) and ends with `doc.save(\`radiology-report-draft-${analysis?.image_id || 'study'}.pdf\`)` (`ReportPanel.jsx:178`). `doc.save()` triggers a browser download to the user's Downloads folder — nothing is POSTed.
- No `/api` call touches the PDF; the only network calls in this component are `generateReport`/`checkCompleteness` for the text (`ReportPanel.jsx:3, 81, 73`), which by contract exclude patient identifiers (`ReportPanel.jsx:55-56`).

**Filename pattern:** `radiology-report-draft-<image_id>.pdf` (or `...-study.pdf` when no id). **Patient name is NOT used in the filename** — even though the name IS rendered into the PDF header (`ReportPanel.jsx:127-136`).

---

## 5. PATIENT-NAME SAVE

**Where identity is captured**
- `PatientIntake.jsx` (fields: `name`, `age`, `phone`; `emptyPatient()` at `:19-21`).
- App state `patient` + sessionStorage mirror (`App.jsx:54-60`).
- Rendered in exactly one place: the PDF header (`ReportPanel.jsx:127-136`).
- Two mount points: the upload screen (`UploadScreen.jsx:227`) and the workspace Report tab (`AiRail.jsx:123`).

**The concrete gaps**
1. **Name entered on the upload screen is wiped by analysis.** `handleUpload` calls `setPatient(emptyPatient())` on success (`App.jsx:126`, "clear identifiers on a new study"). Because the upload screen mounts `PatientIntake` (`UploadScreen.jsx:227`) and then fires analyze, **anything the user typed there is erased the moment analysis returns.** In practice the only workable place to enter a name is the workspace Report tab (`AiRail.jsx:123`), which is non-obvious. This directly frustrates "save it WITH the patient name."
2. **PDF filename ignores the name.** `ReportPanel.jsx:178` uses `image_id` only. A clinician exporting several studies gets `radiology-report-draft-<hash>.pdf` files that are indistinguishable by name.
3. **No named local drafts list.** The autosave draft (`radassist_report_session`, `App.jsx:106-113`) deliberately excludes patient identifiers and keeps only one draft; there's no "saved as <name>" concept.

**Minimal change (respecting the no-PHI-to-server contract)**
- Filename: derive a safe slug from `patient.name` and prepend it, e.g.
  `radiology-report-${slug(patient?.name) || 'study'}-${analysis?.image_id || 'draft'}.pdf` at `ReportPanel.jsx:178` (strip to `[A-Za-z0-9-]`, cap length).
- Header already prints the name (`ReportPanel.jsx:129`) — keep it; it satisfies "save the report with the patient name."
- Don't clear the name on analyze when it was just entered on the upload screen: either move the `setPatient(emptyPatient())` reset (`App.jsx:126`) to fire on *new file pick from the upload screen before intake*, or drop the auto-clear and rely on PatientIntake's explicit Clear (`PatientIntake.jsx:45-48`). Simplest: pass a flag so `handleUpload` preserves a name the user set on the intake screen.
- Optional: a named local drafts map in localStorage keyed by slug(name)+image_id, surfaced as a "Saved reports (this browser)" list — still client-only, no server PHI.

---

## 6. STALE ANALYSIS BUG — CONFIRMED

**Mechanism**
- `analyzeImage` **throws** on any non-2xx (`api.js:34` `if (!res.ok) throw ...`). A hard-rejected image (e.g. 422 "not a chest radiograph") throws; an image the model *scores then abstains* returns 200 with `competence: 'abstain'` and is handled normally.
- `handleUpload` (`App.jsx:115-140`): the `try` sets `setComparison(null)`/`setComparisonError(null)` up front (lines 118-119) but **the `catch` (lines 134-137) only sets `error` and logs.** It does **not** clear `analysis`, `structured`, `history`, `focusedFinding`, or `prior`.
- Result: when a new upload is **rejected**, the previously analysed study stays fully rendered — Viewer, finding cards, confirmed findings, and the generated report all persist (`WorkspaceLayout.jsx:175-240`), with only an error bar added (`WorkspaceLayout.jsx:117`). This is exactly the "stale finding on a non-chest photo" the user reported.
- Same defect in `handlePriorUpload` catch (`App.jsx:156-159`) — a failed prior leaves the old `prior`/`comparison` in place.
- Note: the `localStorage` autosave (`App.jsx:106-113`) will also keep persisting the stale `analysis` until it's cleared.

**Exact fix**
In `handleUpload`'s `catch` (`App.jsx:134-137`), before/after setting the error, clear current-study state:
```js
} catch (e) {
  setError(e.message)
  setAnalysis(null)
  setStructured(emptyStructured())
  setHistory('')
  setFocusedFinding(null)
  setComparison(null)
  setComparisonError(null)
  try { localStorage.removeItem('radassist_report_session') } catch { /* ignore */ }
  log.error('Analyze failed', { reason: e.message })
}
```
In `handlePriorUpload`'s `catch` (`App.jsx:156-159`), clear the prior slot:
```js
} catch (e) {
  setError(e.message)
  setPrior(null)
  setComparison(null)
  setComparisonError(null)
  log.error('Prior analyze failed', { reason: e.message })
}
```
(Alternative: clear the state at the *top* of the `try` before the `await` so the screen goes to a clean "analysing…" state and a failure simply leaves it empty. Clearing in `catch` is the minimal, lowest-risk change.)

---

## 7. OTHER CONTROLS DOING NOTHING (or degraded)

- **Dashboard MiniChart has no interactivity.** `MiniChart.jsx` (AreaChart `:10-62`, Donut `:67-96`) is static SVG — no hover, tooltip, or focus on data points; the last-point marker (`:47-49`) and day labels (`:58`) are display-only. Confirmed inert (not broken, but non-interactive as the user noted). Fix: add `<title>`/`<desc>` per point or a hover tooltip layer; give the marker a focusable target.
- **`hasAlerts` prop chain is fully plumbed but never fed** (`AppShell.jsx:71`, `TopBar.jsx:43,97,106`) — see item 2. Dead until App supplies it.
- **TopBar profile button works** (`TopBar.jsx:115-136`, `onNav('profile')`) — OK. Sidebar nav buttons all wired via `go()` (`Sidebar.jsx:92-102`) — OK. Promo card "Open →" wired (`Sidebar.jsx:147-156`) — OK.
- **UploadScreen "Clear" button + live queue** — functionally unreachable due to instant navigation (item 3). Not a broken handler, but dead in practice.
- **HelpPage search is real** (`HelpPage.jsx:224-239`, filters `shown` topics) — NOT dead; do not confuse with the TopBar search.
- **Dashboard "Review now" / Worklist rows / KPIs** — all wired to real handlers (`Dashboard.jsx:163-168, 124-144`; `Worklist.jsx:46-56, 58-86`). `onOpenStudy` currently just routes to `'app'` (`App.jsx:200`) rather than selecting a specific study — acceptable given the single-study session model, but worth noting once multi-study lands.

---

## Priority order for fixing

1. **#6 stale analysis** (clinical-safety: refused image shows the previous patient's findings) — highest.
2. **#5 patient-name save** (name wiped on analyze + filename ignores it) — user's explicit ask.
3. **#1 search** and **#2 bell** (visible dead controls) — wire to real session state or hide.
4. **#3 upload queue** (await before navigate, or remove the never-seen queue UI).
5. **#4 PDF** — already client-side/correct; only the filename change (folds into #5).
6. **#7 chart interactivity** — polish.
