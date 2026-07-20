const BASE = ''

// --- CSRF double-submit -----------------------------------------------------
// When AUTH_ENABLED, the backend sets a readable (non-HttpOnly) `radassist_csrf`
// cookie on login / 2fa-verify / GET /api/csrf. Every state-changing request under
// the cookie session must echo that value in the `X-CSRF-Token` header, or the
// AuthMiddleware returns 403 `csrf_failed`. When the cookie is absent (open demo /
// auth disabled) we send no header, so every call behaves exactly as before.
function csrfHeaders(extra = {}) {
  try {
    const m = document.cookie.match(/(?:^|;\s*)radassist_csrf=([^;]+)/)
    if (m && m[1]) return { 'X-CSRF-Token': decodeURIComponent(m[1]), ...extra }
  } catch { /* ignore — no document.cookie access */ }
  return { ...extra }
}

// Fetch (and thereby set) a fresh CSRF token/cookie. Best-effort; returns
// { csrf_token, header, enabled } or { enabled:false } on any failure.
export async function csrf() {
  try {
    const res = await fetch(`${BASE}/api/csrf`)
    if (!res.ok) return { enabled: false }
    return res.json()
  } catch {
    return { enabled: false }
  }
}

export async function analyzeImage(file, window = null) {
  const form = new FormData()
  form.append('file', file)
  if (window) form.append('window', window)
  const res = await fetch(`${BASE}/api/analyze`, { method: 'POST', body: form, headers: csrfHeaders() })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Analysis failed')
  return res.json()
}

// Multi-image study: upload several CURRENT views at once. `items` is an array of
// { file, view } where view is 'PA' | 'AP' | 'Lateral' | 'Other' | 'auto'. The
// `views` form fields are sent parallel to the files so the server can tag each.
export async function analyzeStudy(items, window = null) {
  const form = new FormData()
  for (const it of items) {
    form.append('files', it.file)
    form.append('views', it.view || 'auto')
  }
  if (window) form.append('window', window)
  const res = await fetch(`${BASE}/api/analyze-study`, { method: 'POST', body: form, headers: csrfHeaders() })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Study analysis failed')
  return res.json()
}

// CT/MRI DICOM viewer (NO AI). Uploads one or more DICOM files (a series) and
// returns ordered rendered slice URLs + technical metadata. `window` is a CT
// preset name (brain/stroke/subdural/bone/skeletal/lung/mediastinum/liver/angio)
// or null (file window for CT, percentile for MR).
export async function dicomView(files, window = null) {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  if (window) form.append('window', window)
  const res = await fetch(`${BASE}/api/dicom-view`, { method: 'POST', body: form, headers: csrfHeaders() })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not render DICOM')
  return res.json()
}

// MRI/CT SERIES viewer: returns { series:[...], pairs:[...] } grouped by series.
export async function dicomViewSeries(files, window = null) {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  if (window) form.append('window', window)
  const res = await fetch(`${BASE}/api/dicom-view-series`, { method: 'POST', body: form, headers: csrfHeaders() })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not render series')
  return res.json()
}

// Region statistics on the 16-bit intensity (HU/a.u.) for an ROI. `shape` is a
// rect/ellipse in normalised [0,1] coords {type, nx, ny, nw, nh}.
export async function dicomRoi(files, shape, opts = {}) {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  form.append('shape', JSON.stringify(shape))
  if (opts.seriesId) form.append('series_id', opts.seriesId)
  if (opts.slicePosition != null) form.append('slice_position', String(opts.slicePosition))
  const res = await fetch(`${BASE}/api/dicom-roi`, { method: 'POST', body: form, headers: csrfHeaders() })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not compute ROI')
  return res.json()
}

// Volume-pivot: raw int16 intensity of a series' middle slice for canvas windowing.
export async function dicomRaw(files) {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  const res = await fetch(`${BASE}/api/dicom-raw`, { method: 'POST', body: form, headers: csrfHeaders() })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not get raw intensity')
  return res.json()
}

export async function generateReport(payload) {
  const res = await fetch(`${BASE}/api/generate-report`, {
    method: 'POST',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Report generation failed')
  return res.json()
}

// --- CT/MRI research report (#9 / WF7) --------------------------------------
// Build a research SUMMARY of clinician-CONFIRMED candidates + anatomy measurements.
// It is NOT a diagnosis, NOT triage, NOT a probability — the backend forces the
// modality by endpoint (a body `modality` is ignored) and runs a server-side guard
// that refuses any diagnostic/probability phrasing. `payload` is a CtReportRequest:
// { technique, clinical_history, series_id, measurements[], candidates[] }.
async function _postCtMrReport(path, payload) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Report generation failed')
  return res.json()
}

export async function generateCtReport(payload) {
  return _postCtMrReport('/api/ct-report', payload)
}

export async function generateMrReport(payload) {
  return _postCtMrReport('/api/mr-report', payload)
}

export async function checkCompleteness(payload) {
  const res = await fetch(`${BASE}/api/completeness-check`, {
    method: 'POST',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error('Completeness check failed')
  return res.json()
}

export async function compareStudies(priorId, currentId, priorDate = null) {
  const res = await fetch(`${BASE}/api/compare`, {
    method: 'POST',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      prior_image_id: priorId,
      current_image_id: currentId,
      prior_date: priorDate,
    }),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Comparison failed')
  return res.json()
}

export async function getBehaviorCard() {
  const res = await fetch(`${BASE}/api/behavior-card`)
  if (!res.ok) return { available: false }
  return res.json()
}

export async function health() {
  const res = await fetch(`${BASE}/api/health`)
  return res.json()
}

// Session probe: { auth_enabled, authenticated, user }. Best-effort (never throws).
export async function me() {
  try {
    const res = await fetch(`${BASE}/api/me`)
    if (!res.ok) return { auth_enabled: false, authenticated: false, user: null }
    return res.json()
  } catch {
    return { auth_enabled: false, authenticated: false, user: null }
  }
}

export async function login(username, password) {
  const res = await fetch(`${BASE}/api/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Login failed')
  return res.json()
}

export async function logout() {
  await fetch(`${BASE}/api/logout`, { method: 'POST', headers: csrfHeaders() }).catch(() => {})
}

// Begin TOTP enrollment for the CURRENT session's user. Returns
// { secret, otpauth_uri, issuer, digits, period, algorithm, confirmed:false }.
// The enrollment is PENDING until verify2fa() confirms a code.
export async function enroll2fa() {
  const res = await fetch(`${BASE}/api/2fa/enroll`, { method: 'POST', headers: csrfHeaders() })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not start two-factor enrollment')
  return res.json()
}

// Verify a 6-digit TOTP code — confirms a pending enrollment AND/OR completes a
// half-authenticated login. On success the backend rotates the session + CSRF
// cookies. Returns { authenticated:true, mfa:true, user }.
export async function verify2fa(code) {
  const res = await fetch(`${BASE}/api/2fa/verify`, {
    method: 'POST',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ code }),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Invalid or expired code')
  return res.json()
}

// Turn OFF TOTP 2FA for the current user. `code` is a current 6-digit TOTP; it is
// only required when the account currently has CONFIRMED 2FA (possession proof).
// Returns { disabled:true, mfa_enrolled:false, user }. On a bad code the backend
// answers 401 { code:'totp_invalid' }.
export async function disable2fa(code) {
  const res = await fetch(`${BASE}/api/2fa/disable`, {
    method: 'POST',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ code: code || '' }),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not disable two-factor authentication')
  return res.json()
}

// --- Per-user session self-management (requires DATABASE_URL server-side) ----
// List the CURRENT user's own live sessions, newest first. Returns
// { supported:true, sessions:[{id, sid, created_at, last_seen, user_agent, ip_hash,
// is_current}] } when the DB is on, or { supported:false, sessions:[] } (honest
// "session history needs the database") when the app is stateless. Never throws.
export async function sessions() {
  try {
    const res = await fetch(`${BASE}/api/sessions`)
    if (!res.ok) return { supported: false, sessions: [] }
    return res.json()
  } catch {
    return { supported: false, sessions: [] }
  }
}

// Revoke ONE of the caller's own sessions by `sid`. Revoking the current sid logs
// this device out on its next request. Returns { revoked, sid }.
export async function revokeSession(sid) {
  const res = await fetch(`${BASE}/api/sessions/revoke`, {
    method: 'POST',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ sid }),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not revoke that session')
  return res.json()
}

// Sign out of all OTHER devices (no body): revoke every live session for the caller
// except the current one. Returns { revoked, kept }.
export async function revokeOtherSessions() {
  const res = await fetch(`${BASE}/api/sessions/revoke-others`, { method: 'POST', headers: csrfHeaders() })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not sign out other devices')
  return res.json()
}

// Reviewer thumbs-up/down feedback. `event` is PHI-free by construction:
// { target: 'finding'|'report', rating: 'up'|'down', label, model_note, action, timestamp }.
export async function submitFeedback(event) {
  const res = await fetch(`${BASE}/api/feedback`, {
    method: 'POST',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(event),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Feedback failed')
  return res.json()
}

// --- Anatomy-overlay segmentation (opt-in, NON-DIAGNOSTIC) ------------------
// These label/segment anatomy and measure regions ONLY. `modality` is 'CT' or 'MR'
// and selects the modality-guarded endpoint. Both are default-OFF server-side.
export async function startAnatomySegment(files, modality, opts = {}) {
  const path = modality === 'CT' ? '/api/segment' : '/api/mr-segment'
  const form = new FormData()
  for (const f of files) form.append('files', f)
  if (opts.task) form.append('task', opts.task)
  if (opts.roiSubset) form.append('roi_subset', opts.roiSubset)
  // Segment the SAME series the viewer displays (MR), so the overlay can never land
  // on a different series.
  if (opts.seriesId) form.append('series_id', opts.seriesId)
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: form, headers: csrfHeaders() })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Anatomical analysis failed')
  return res.json()
}

export async function pollAnatomySegment(jobId) {
  const res = await fetch(`${BASE}/api/segment/${jobId}`)
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not poll analysis')
  return res.json()
}

// Belt-and-suspenders client guard: throws if the server ever leaked a diagnosis-
// shaped KEY into a segment response (the server enforces this at the schema layer;
// this catches any regression). Scans KEY NAMES only — the `disclaimer` VALUE
// legitimately contains words like "disease"/"abnormality" in its honest negation.
const _DIAGNOSIS_KEY = /finding|probab|impression|malign|abnormal|diagnos|severity|lesion|tumou?r|cancer|nodule|\bmass\b|bleed|h(a)?emorrha|infarct|stroke|aneurysm|effusion|o?edema|fracture|stenosis|patholog|suspic|detect|\bscore\b|coverage|confidence|likelihood|birads|lirads|pirads|flagged|triage|heatmap/i
// Feedback-loop admin summary: per-label confirm/dismiss + current vs proposed threshold.
export async function feedbackSummary() {
  const res = await fetch(`${BASE}/api/feedback/summary`)
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not load feedback summary')
  return res.json()
}

// --- Research CADe: disease-CANDIDATE detection on CT/MR (opt-in, UNVALIDATED) ---
// `modality` is 'CT' or 'MR' and selects the modality-guarded endpoint.
export async function startDetect(files, modality, seriesId) {
  const path = modality === 'MR' ? '/api/mr-detect' : '/api/ct-detect'
  const form = new FormData()
  for (const f of files) form.append('files', f)
  if (seriesId) form.append('series_id', seriesId)
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: form, headers: csrfHeaders() })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Candidate detection failed')
  return res.json()
}

export async function pollDetect(jobId, modality) {
  const path = modality === 'MR' ? '/api/mr-detect' : '/api/ct-detect'
  const res = await fetch(`${BASE}${path}/${jobId}`)
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not poll detection')
  return res.json()
}

export function assertNoDiagnosisFields(obj) {
  const walk = (o) => {
    if (Array.isArray(o)) { o.forEach(walk); return }
    if (o && typeof o === 'object') {
      for (const k of Object.keys(o)) {
        if (_DIAGNOSIS_KEY.test(k)) {
          throw new Error(`anatomy overlay returned a diagnosis-shaped field "${k}" — refusing to display`)
        }
        walk(o[k])
      }
    }
  }
  walk(obj)
  return obj
}
