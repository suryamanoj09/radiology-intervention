# RadAssist UI Audit — Interactive Control Inventory & Fix Plan

Read-only audit of the re-skinned RadAssist frontend (`frontend/src`). Every
control below was traced through `App.jsx` → `AppShell` → shells/components to
confirm whether its handler is actually wired and whether any persisted state is
ever consumed. Line references verified against source on audit date.

Scope: marketing site, console shell (TopBar / Sidebar / AppShell), dashboard,
upload, analyzer workspace (X-ray Viewer + CT/MRI DicomViewer), findings, report,
account screens. No code was modified.

---

## 1. Main category buttons

The primary navigation and action controls the user asked to see listed, grouped.

### Global navigation (marketing shell)
- **MarketingHeader:** Logo → Home · Platform (`#platform`) · Modalities (`#modalities`) · Evidence · Security (`#security`) · About · Theme toggle · Sign in · **Launch console**
- **MarketingFooter:** Brand/logo · Product (Overview / Evidence / Help & docs) · Company (About / Evidence) · Legal (Privacy / Help & docs)

### Console shell (authenticated app chrome)
- **TopBar:** Session search · Theme toggle · Notifications bell · Profile
- **Sidebar → CLINICAL:** Dashboard · New analysis · Upload
- **Sidebar → ACCOUNT:** Profile · Settings
- **Sidebar promo:** "Model behaviour card → Open"

### Dashboard (primary actions)
- **Upload studies** · **New AI analysis** · Priority-banner **Review now** · **See full measured evidence →**
- Worklist: **New analysis →**, study rows, empty-state **Analyse a study**

### Upload screen
- Dropzone (click / drag-drop) · **Clear** · Patient intake fields · **← Back to workspace**

### Analyzer workspace — top bar (StudyContextBar)
- Modality tabs: **Chest X-ray / CT / MRI** · **? How to use** · **⚠ Limitations** · **🔬 Where it fails** · **📊 Model tuning** · **⇤ Focus viewer / ⇥ Show report**

### Analyzer workspace — X-ray Viewer
- **Fullscreen** · Overlay mode **Off / Heatmap / Contour** · Opacity · **Caliper** · Units **mm / px** · WL presets **Default / Lung / Bone / Soft tissue** · B/C sliders · **Invert** · Region chips · Zoom / Pan / **Reset view** · Threshold slider · Finding rows

### Analyzer workspace — findings & report (AiRail)
- Tabs: **AI findings / Report**
- FindingsForm: AI suggestion chips · finding checkboxes · **🎙 Dictate** · attest checkbox
- DisagreementPrompts: **Record it / Dismiss**
- ReportPanel: Reviewer name · Attest · **Check findings** · **Generate report** · **Export PDF** · sub-tabs **Clinical / Patient / Differentials** · Feedback thumbs

### Analyzer workspace — CT/MRI (DicomViewer)
- File input · **Viewer & findings / Report** · series rail · CT window presets · slice ‹ / › · tools **Length / Angle / ROI** · **Undo / Redo** · **Cine ▶/⏸** · fps · B/C · **Raw window** · **▥ Compare** · **⌨ Keys** · AI tabs **Anatomy / Candidates**
- AnatomyOverlayPanel: overlay toggle · **Run anatomical analysis** · opacity · structure legend
- CandidateFindings: enable · **Run candidate detection** · **✓ Confirm / ✗ Dismiss**
- CtReportPanel: technique/history · reviewer/attest · **Generate research summary** · **Export PDF**

### Account & auth
- **Login:** email / password / Remember me / Forgot password / **Sign in** / SSO (disabled) / 2FA code / **Verify & sign in**
- **ProfilePage:** Settings · Sign out
- **SettingsPage:** Theme · Accent swatches · Density · toggles (Auto-Grad-CAM / Voice dictation / Email digests / Critical alerts) · **Clear patient identifiers** · **Clear saved report draft** · **Reset theme**

---

## 2. Full control inventory (DEAD / MISSING-HANDLER / PLACEHOLDER first)

| Status | Screen | Control | File:line | What it does |
|---|---|---|---|---|
| **DEAD-NOOP** | TopBar | Session search input | `shell/TopBar.jsx:77-88` | `onChange` calls `onSearch && onSearch(...)`; **`App.jsx:312-319` never passes `onSearch`** through `AppShell` → typing filters nothing |
| **DEAD-NOOP** | TopBar | Notifications bell | `shell/TopBar.jsx:95-112` | **No `onClick` at all**; `hasAlerts` never passed (`App.jsx:312-319`) so dot never shows. Pure decoration |
| **PLACEHOLDER** | Settings | Auto-show Grad-CAM toggle | `SettingsPage.jsx:202` | Writes `radassist_pref_auto_heatmap`; **read nowhere** — viewer never consumes it |
| **PLACEHOLDER** | Settings | Voice dictation toggle | `SettingsPage.jsx:206` | Writes `radassist_pref_dictation`; **read nowhere** — FindingsForm dictation isn't gated on it |
| **PLACEHOLDER** | Settings | Email digests toggle | `SettingsPage.jsx:217` | Writes `radassist_pref_notify_email`; **no delivery consumer** |
| **PLACEHOLDER** | Settings | Critical-finding alerts toggle | `SettingsPage.jsx:221` | Writes `radassist_pref_notify_critical`; **no alert consumer** |
| **PLACEHOLDER** | Dashboard | AreaChart "This session's activity" | `dashboard/MiniChart.jsx:10-62` | Static inline SVG — **no hover, tooltip, or point interaction**; day labels `aria-hidden` |
| **PLACEHOLDER** | Dashboard | Donut "Modality mix" | `dashboard/MiniChart.jsx:67-96` | Static SVG arcs — **no hover / click / legend** interactivity |
| **PARTIAL** | Marketing header | Platform / Modalities / Security anchors | `shell/MarketingHeader.jsx` | `#platform` / `#modalities` / `#security` only resolve on Home (ids live in HomePage); **dead on About/Help/Evidence/Privacy** |
| **PARTIAL** | Dashboard | Priority-banner "Review now" | `dashboard/Dashboard.jsx:163` | Calls `onOpenStudy(study)` but **`App.jsx:200` discards the arg** → just `setPage('app')`; can't target the flagged study |
| **PARTIAL** | Worklist | Study row buttons | `dashboard/Worklist.jsx:58-86` | Clickable, but `onOpenStudy(w.study)` → `App.jsx:200` discards the row's study; loads whatever is already current |
| **PARTIAL** | Upload | "Clear" (queue) | `UploadScreen.jsx:168-174` | `setPicked(null)` clears the local queue row only; **does not cancel the in-flight analyze** (App owns busy) |
| **PARTIAL** | Upload | Analysing queue row / progress / Clear | `UploadScreen.jsx:187-222` | `onAnalyze` navigates to 'app' **synchronously** (`App.jsx:206`), so UploadScreen unmounts instantly — the queue UI, progress bar and Clear are effectively **unreachable** |
| **PARTIAL** | Report | "Export PDF" | `ReportPanel.jsx:178` | `doc.save(\`radiology-report-draft-${image_id||'study'}.pdf\`)` — client download to Downloads; **filename uses `image_id`, not patient name** (name only inside the PDF header) |
| **PARTIAL** | Home | "Book a walkthrough" | `HomePage.jsx:549` | `onNav('help')` — label promises scheduling; only navigates. No booking flow |
| **PARTIAL** | About | "Contact support" | `AboutPage.jsx:273` | `onNav('help')` — no contact form; label implies support |
| INFO-ONLY | Settings | Chest X-ray / CT-MRI status chips | `SettingsPage.jsx:232/238` | Read-only server-gated status badges (by design) |
| INFO-ONLY | Sidebar | Brand block | `Sidebar.jsx:113` | Plain div, non-interactive (unlike header/footer logos) |
| INFO-ONLY | Help | Keyboard-shortcuts panel | `HelpPage.jsx:347-358` | Static list (keys act only inside workspace) |
| INFO-ONLY | Evidence | Per-pathology table rows | `EvidencePage.jsx:250+` | Non-interactive (title tooltips only) |
| PLACEHOLDER (by design) | Login | Continue with SSO (SAML) | `Login.jsx:146` | `disabled`, "Roadmap" tag — intentional |
| WORKS | *(all other controls)* | — | — | Marketing nav, Help search, Sidebar nav, Viewer, DicomViewer, FindingsForm, DisagreementPrompts, ReportPanel controls, CtReportPanel, Login flow, ProfilePage, Settings theme/accent/density/clear actions — all wired and functional (see per-screen tables in source audit) |

**Note — do NOT confuse:** HelpPage search (`HelpPage.jsx:224-239`) is genuinely functional client-side filtering. The DEAD search is the *TopBar* one only.

---

## 3. Confirmed bugs (with exact fixes)

### BUG 1 — Stale analysis persists after a refused/abstained/failed upload (SAFETY, P0)
**Confirmed.** `analyzeImage` throws on non-2xx (`api.js:34`). A hard-rejected
(e.g. 422 non-chest) image throws, and the catch in `handleUpload`
(`App.jsx:134-137`) sets **only** `error` — it never clears `analysis`,
`structured`, `history`, `focusedFinding`, or `comparison`. The previous study's
viewer, findings and report stay on screen under an error bar. This is the
reported "stale finding on a non-chest photo." Same defect in `handlePriorUpload`
catch (`App.jsx:156-159`).

**Fix — `App.jsx`, `handleUpload` catch block (`:134`):**
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
**Fix — `handlePriorUpload` catch (`:156`):**
```js
} catch (e) {
  setError(e.message)
  setPrior(null)
  setComparison(null)
  setComparisonError(null)
  log.error('Prior analyze failed', { reason: e.message })
}
```
(Clearing the autosaved draft on failure is important — otherwise the reload-restore
effect at `App.jsx:91-105` re-hydrates the stale study on next load.)

### BUG 2 — TopBar session search is dead (P0)
**Confirmed.** `TopBar.jsx:81` calls `onSearch && onSearch(...)`; `AppShell.jsx:66-72`
forwards `onSearch`, but `App.jsx:312-319` mounts `<AppShell>` **without** an
`onSearch` prop (author flagged it a stub at `TopBar.jsx:18`). Typing is a silent no-op.

**Fix:** add `const [studyQuery, setStudyQuery] = useState('')` in `App.jsx`; pass
`onSearch={setStudyQuery}` to `<AppShell>` (`:312`); thread `studyQuery` into the
Dashboard/Worklist so session study rows (and the current study's finding cards)
filter on `label` / `triage` / `competence` / `history`. Keep the honest
"local, client-only, non-PHI" framing already in `TopBar.jsx:4-10`.

### BUG 3 — Notifications bell is dead (P0)
**Confirmed.** `TopBar.jsx:95-112` button has **no `onClick`**; `hasAlerts`
defaults `false` (`:43`) and is never supplied by `App.jsx`.

**Fix (honest, no fabricated alerts):** derive real alert state in `App.jsx` from
existing session state — `analysis?.triage === 'urgent'`, `analysis?.competence === 'abstain'`,
and `draftRestored` (`App.jsx:90`). Pass `hasAlerts={alerts.length > 0}` and add an
`onOpen` handler to TopBar that opens a small popover listing only those real items,
with Dismiss reusing `onDismissDraft`. Do not invent notifications.

### BUG 4 — PDF filename ignores patient name (P1)
**Confirmed.** `ReportPanel.jsx:178`:
`doc.save(\`radiology-report-draft-${analysis?.image_id || 'study'}.pdf\`)`.
The patient name IS printed in the header (`:129-136`) but never used in the
filename.

**Fix:** slugify `patient.name` into the filename:
```js
const slug = (patient?.name || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
doc.save(`radiology-report-${slug || 'study'}-${analysis?.image_id || 'draft'}.pdf`)
```

### BUG 5 — Patient name typed at upload intake is wiped by analysis (P1)
**Confirmed.** `handleUpload` calls `setPatient(emptyPatient())` on success
(`App.jsx:126`) to prevent cross-patient bleed, but this also erases a name the
user typed into the upload-screen intake (`UploadScreen.jsx:227`). The only
reliable entry point becomes the workspace Report tab (`AiRail.jsx:123`).

**Fix:** stop auto-clearing a name the user explicitly set at intake — clear
identifiers only when starting a genuinely new study without pre-entered intake,
or preserve `patient` when the upload came from the intake screen. Combine with
BUG 4 so the entered name reaches both the header and the filename.

### BUG 6 — Marketing header anchors dead off-Home (P1)
**Confirmed.** `#platform` / `#modalities` / `#security` (MarketingHeader) resolve
only on Home, where those ids live in HomePage. On About/Help/Evidence/Privacy the
header still renders them, pointing at nothing.

**Fix:** make these route to Home then scroll (`onNav('home')` + a pending
scroll-to-id), or hide the anchor links when `route !== 'home'`.

### Non-bug but label-honesty gaps
- "Book a walkthrough" (`HomePage.jsx:549`) and "Contact support" (`AboutPage.jsx:273`)
  only `onNav('help')` — either build the target or relabel to "See help".

---

## 4. Prioritized FIX PLAN

### P0 — Broken / misleading (features that lie about working or risk patient safety)
1. **Stale analysis on failed/refused upload** (BUG 1). `App.jsx:134-137` & `:156-159` —
   clear `analysis`/`structured`/`history`/`focusedFinding`/`comparison`/`comparisonError`
   and remove the autosaved draft in both catch blocks. *(Highest priority — this is a
   correctness/safety bug: a prior patient's findings shown under a new, rejected image.)*
2. **Dead TopBar search** (BUG 2). `App.jsx:312` — add `studyQuery` state + `onSearch={setStudyQuery}`;
   `Dashboard.jsx`/`Worklist.jsx` — filter session rows. Or remove the input if not scoped.
3. **Dead notifications bell** (BUG 3). `App.jsx` — derive real alerts; `shell/TopBar.jsx:95` —
   add `onClick`/popover; pass `hasAlerts`. Or remove the bell.
4. **Settings placeholder toggles** (4×). Either **consume** the prefs
   (`Viewer` reads `pref_auto_heatmap` to auto-open Grad-CAM; `FindingsForm` gates the
   mic on `pref_dictation`) or, for the two notification prefs with no delivery path,
   relabel them honestly / mark "coming soon" so a flipped switch is not a silent no-op.
   Files: `SettingsPage.jsx:202/206/217/221`, `Viewer.jsx`, `FindingsForm.jsx`.
5. **Marketing anchors dead off-Home** (BUG 6). `shell/MarketingHeader.jsx` — route-to-Home-then-scroll, or hide off-Home.

### P1 — Explicit user asks
6. **Dashboard Power-BI-style chart hover tooltips** (BUG-adjacent). `dashboard/MiniChart.jsx` —
   add `onMouseMove`/`onMouseLeave` hit-testing on the AreaChart to show a value tooltip
   at the nearest point (render the marker on hover, not just the last point); add
   per-segment hover + a legend on the Donut. Keep it dependency-free inline SVG (CSP-safe).
7. **Functional session search** — same wiring as P0 #2; the deliverable the user wants is
   typing in the top bar actually filtering the visible session studies/findings.
8. **Save report with patient name** (BUG 4 + BUG 5). `ReportPanel.jsx:178` — slugify name
   into filename; `App.jsx:126` — stop wiping an intake-entered name; header already carries it.
9. **PDF-storage clarity in the UI.** The "Export PDF" button downloads to the browser
   Downloads folder with no server copy (`ReportPanel.jsx:88-179`, no `/api` call). Add a
   one-line helper near the button ("Downloads a local PDF to this device — not saved on the
   server") so users understand where the file goes. Same note applies to `CtReportPanel.jsx:184`.
10. **Upload rough edges** (BUG-adjacent). `App.jsx:206` / `UploadScreen.jsx` — `await handleUpload`
    and navigate only on success so the "Analysing…" queue row, progress bar and Clear are
    actually seen and errors surface on the upload screen; OR delete the never-reached queue UI.
    Make Upload "Clear" (`UploadScreen.jsx:168`) also cancel/ignore the in-flight result.

### P2 — Polish
11. **`onOpenStudy` targeting** (`App.jsx:200`). Accept the study argument so Dashboard
    "Review now" and Worklist rows load the chosen study (fine to keep single-study model,
    but the arg should not be silently discarded).
12. **Label honesty** on "Book a walkthrough" / "Contact support" — build target or relabel.
13. **Duplicate footer links** (Product→Evidence vs Company→Evidence; Help & docs ×2) — dedupe or differentiate.

---

## 5. Design + button improvement suggestions

All suggestions honor RadAssist's honest decision-support framing — no fabricated
features, metrics, or clinical claims.

### Button hierarchy — make primary / secondary / destructive visually distinct
- Today most buttons share the same outlined `var(--surface)` chrome (e.g. TopBar
  icon buttons, viewer toolbar). Establish three tiers:
  - **Primary (filled, accent):** the single main action per screen — "Start AI analysis",
    "New AI analysis", "Generate report", "Sign in".
  - **Secondary (outlined):** navigation and mode toggles — "Explore the console", overlay modes, sub-tabs.
  - **Destructive/caution (danger-tinted outline):** "Clear patient identifiers", "Clear saved report draft", "Dismiss". Currently these read identically to benign buttons.
- One primary button per view; demote the rest. This directly reduces the "so many
  buttons" overwhelm the user reported.

### Disabled & loading states — say *why*, and show progress
- Disabled controls (SSO, mm-when-no-spacing, Generate-until-signed-off) should carry a
  `title`/tooltip explaining the gate ("Enable after sign-off", "No pixel spacing in this image").
- Async actions ("Analysing…", "Run anatomical analysis", "Generate report", "Export PDF")
  need an in-button spinner + disabled-during-flight so double-clicks can't fire twice.
  The upload flow especially (BUG/P1 #10) currently hides its own progress by navigating away.

### Empty & error states — the workspace's weakest moment
- After a refused/abstained upload (once BUG 1 is fixed and the stale study is cleared),
  show a purposeful empty state: the abstain/refusal reason, "This image was not accepted
  as a chest X-ray", and a clear "Upload a different study" action — not just a red error bar
  over blank panes.
- Dashboard already degrades to an empty state when there's no session study; carry the same
  honesty into the Worklist and the (soon-interactive) charts.

### Tooltips explaining each control
- The viewer toolbar is dense (overlay modes, WL presets, caliper, threshold). Add short
  `title`/`aria` tooltips: "Heatmap = region of model attention, not a lesion boundary" (reuse
  the exact PDF disclaimer wording at `ReportPanel.jsx:115`). This both teaches and keeps the
  honest framing consistent between screen and export.

### Notifications bell — make it a real, honest surface (ties to BUG 3)
- Only ever show the unread dot for genuine session state (urgent triage, abstain, restored
  draft). The popover should read like a status list ("This study was triaged URGENT",
  "Model abstained — out of distribution", "Draft restored from your last session"), never a
  fabricated inbox. If there's nothing real to show, keep the bell but with no dot and an empty
  "No alerts in this session" popover — honest and non-dead.

### Dashboard charts — Power-BI feel without a chart library (ties to P1 #6)
- Add hover crosshair + a value tooltip ("Tue — 3 studies") on the AreaChart; highlight the
  hovered point. On the Donut, hover a segment to raise it and show "CT — 40% (2 studies)",
  plus a small clickable legend that can filter the worklist. Keep it inline-SVG/CSP-safe.
  Label the data honestly as "This session" (it already is) so no one reads it as a fleet metric.

### Make the model-behaviour-card promo actionable
- The Sidebar promo and the About behaviour-card are informational. Elevate the confirm/dismiss
  and sign-off affordances instead: the DisagreementPrompts "Record it / Dismiss" and the
  ReportPanel reviewer-name + attest gate are the clinically important actions — give them the
  strongest visual weight (primary styling on "Record it", clear gated state on "Generate report"
  until the attest checkbox + reviewer name are set, which the code already enforces but styles weakly).

### Search — scope it honestly and visibly (ties to BUG 2)
- Keep the existing placeholder honesty ("Search studies in session…"). When it filters and finds
  nothing, show "No studies in this session match" rather than a blank list. Because the session
  worklist is 0–1 study today, consider a subtle helper: "Filters studies analysed in this browser
  session (client-only, non-PHI)."

### Iconography & affordance consistency
- Header/footer logos are links but the Sidebar brand block (`Sidebar.jsx:113`) is an inert div —
  either make all three navigate Home or none, so the brand affordance is predictable.
- Modality tabs, sub-tabs, and AI tabs use three different visual patterns for the same "segmented
  toggle" concept — unify into one segmented-control style so users learn it once.

### Export clarity (ties to P1 #9)
- Add a persistent one-liner under "Export PDF": "Downloads a local, un-signed draft to this device.
  Not stored on the server; not a medical record." This matches the in-PDF disclaimers and closes the
  gap between what the button does and what a clinician might assume.
