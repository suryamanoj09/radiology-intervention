import { useEffect, useState } from 'react'
import ThemeToggle, { setTheme, ACCENTS, getAccent, setAccent, getDensity, setDensity } from './ThemeToggle.jsx'
import LogViewer from './LogViewer.jsx'
import { log } from '../logger.js'

// Settings: real client-side preferences (theme, accent, density, AI/notification
// prefs), the CT/MRI AI channel status (read-only, server-gated), the diagnostics
// log viewer, and reset controls. No server/account backend — everything the user
// can change here lives in the browser (localStorage / sessionStorage).

// --- Boolean preferences (persisted to localStorage) --------------------------
// Keys and sensible defaults. Only Grad-CAM auto-reveal, dictation, and the two
// notification prefs are user-settable; the CT/MRI AI channel is server-gated.
const PREFS = {
  autoHeatmap: { key: 'radassist_pref_auto_heatmap', def: false },
  dictation:   { key: 'radassist_pref_dictation',     def: false },
  notifyEmail: { key: 'radassist_pref_notify_email',  def: false },
  notifyCritical: { key: 'radassist_pref_notify_critical', def: true },
}

function getPref(name) {
  const p = PREFS[name]
  try {
    const v = localStorage.getItem(p.key)
    if (v === null) return p.def
    return v === '1' || v === 'true'
  } catch { return p.def }
}
function setPref(name, on) {
  const p = PREFS[name]
  try { localStorage.setItem(p.key, on ? '1' : '0') } catch { /* ignore */ }
}

// --- Presentational helpers (all inline styles referencing WF2's CSS vars) -----
const card = {
  background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16,
  padding: 22, boxShadow: 'var(--shadow-sm)', marginTop: 16,
}
const cardTitle = { fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: 16, color: 'var(--ink)' }
const cardSub = { fontSize: 12.5, color: 'var(--muted)', marginTop: 2 }
const rowLabel = { fontSize: 14, fontWeight: 500, color: 'var(--ink)' }
const rowDesc = { fontSize: 12.5, color: 'var(--muted)', marginTop: 2 }

// A toggle switch matching the design's swTrack/swKnob (lines 1135-1136).
function Toggle({ on, onChange, label }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(!on)}
      style={{
        width: 42, height: 24, borderRadius: 99, border: 'none', cursor: 'pointer', position: 'relative',
        flex: 'none', transition: 'background .15s', padding: 0,
        background: on ? 'var(--primary)' : 'var(--border-2)',
      }}>
      <span style={{
        position: 'absolute', top: 3, left: on ? 21 : 3, width: 18, height: 18, borderRadius: 99,
        background: '#fff', transition: 'left .15s', boxShadow: '0 1px 3px rgba(0,0,0,.35)',
      }} />
    </button>
  )
}

// One label/description + control row with a top divider (design line 972/979).
function Row({ label, desc, first, children }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 16, padding: '14px 0',
      borderTop: first ? 'none' : '1px solid var(--border)',
    }}>
      <div style={{ flex: 1 }}>
        <div style={rowLabel}>{label}</div>
        {desc && <div style={rowDesc}>{desc}</div>}
      </div>
      {children}
    </div>
  )
}

export default function SettingsPage({ behaviorCard } = {}) {
  const [msg, setMsg] = useState(null)

  // Accent + density mirror the shared setters and re-sync on cross-instance events.
  const [accent, setAccentState] = useState(getAccent)
  const [density, setDensityState] = useState(getDensity)
  useEffect(() => {
    const syncA = () => setAccentState(getAccent())
    const syncD = () => setDensityState(getDensity())
    window.addEventListener('radassist-accent-change', syncA)
    window.addEventListener('radassist-density-change', syncD)
    window.addEventListener('storage', syncA)
    window.addEventListener('storage', syncD)
    return () => {
      window.removeEventListener('radassist-accent-change', syncA)
      window.removeEventListener('radassist-density-change', syncD)
      window.removeEventListener('storage', syncA)
      window.removeEventListener('storage', syncD)
    }
  }, [])

  // Effective theme drives which swatch colour (light vs dark primary) to preview.
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === 'dark')
  useEffect(() => {
    const sync = () => setDark(document.documentElement.dataset.theme === 'dark' ||
      (!document.documentElement.dataset.theme && window.matchMedia &&
        window.matchMedia('(prefers-color-scheme: dark)').matches))
    sync()
    window.addEventListener('radassist-theme-change', sync)
    let mq
    try { mq = window.matchMedia('(prefers-color-scheme: dark)'); mq.addEventListener('change', sync) } catch { /* */ }
    return () => {
      window.removeEventListener('radassist-theme-change', sync)
      try { mq && mq.removeEventListener('change', sync) } catch { /* */ }
    }
  }, [])

  // Boolean prefs — local mirror, persisted on change.
  const [autoHeatmap, setAutoHeatmap] = useState(() => getPref('autoHeatmap'))
  const [dictation, setDictation] = useState(() => getPref('dictation'))
  const [notifyEmail, setNotifyEmail] = useState(() => getPref('notifyEmail'))
  const [notifyCritical, setNotifyCritical] = useState(() => getPref('notifyCritical'))
  const togglePref = (name, cur, setter) => () => { const next = !cur; setter(next); setPref(name, next) }

  // CT/MRI AI channel: server-flag gated, defaults OFF, never diagnosis. Read-only
  // here — this surface reflects the server flag, it does not enable anything.
  const ctMriOn = !!(behaviorCard && behaviorCard.channels && behaviorCard.channels.ct_mri_ai_enabled)

  function clearDraft() {
    try { localStorage.removeItem('radassist_report_session') } catch { /* */ }
    log.info('Cleared saved report draft (Settings)')
    setMsg('Saved report draft cleared. Reload the analyzer to see the change.')
  }
  function clearIdentifiers() {
    try { sessionStorage.removeItem('radassist_patient') } catch { /* */ }
    log.info('Cleared patient identifiers (Settings)')
    setMsg('Patient identifiers cleared from this browser session.')
  }
  function resetTheme() {
    setTheme('system')
    setMsg('Theme reset to system default.')
  }

  return (
    <div style={{ padding: '26px 28px 44px', maxWidth: 820, margin: '0 auto' }}>
      <h2 style={{ fontSize: 24, fontWeight: 700, color: 'var(--ink)', fontFamily: 'var(--font-head)' }}>Settings</h2>
      <p style={{ color: 'var(--muted)', fontSize: 14, marginTop: 4 }}>
        Preferences and diagnostics — everything you change here is stored locally in this browser. Nothing on this
        page is sent to the server.
      </p>

      {/* Appearance ----------------------------------------------------------- */}
      <section style={{ ...card, marginTop: 20 }}>
        <div style={cardTitle}>Appearance</div>
        <div style={cardSub}>Choose how RadAssist looks. Dark suits low-light reading rooms.</div>

        <Row label="Theme" desc="System, light, or dark. Default follows your OS." first>
          <ThemeToggle />
        </Row>

        <Row label="Accent" desc="Tints buttons, links, and highlights across the app.">
          <div role="radiogroup" aria-label="Accent colour" style={{ display: 'flex', gap: 10 }}>
            {Object.keys(ACCENTS).map((name) => {
              const a = ACCENTS[name]
              const swatch = dark ? a.pD : a.pL
              const selected = accent === name
              return (
                <button key={name} type="button" role="radio" aria-checked={selected} aria-label={name} title={name}
                  onClick={() => setAccent(name)}
                  style={{
                    width: 28, height: 28, borderRadius: 99, cursor: 'pointer', padding: 0,
                    background: swatch,
                    border: selected ? '2px solid var(--ink)' : '2px solid var(--border)',
                    boxShadow: selected ? 'var(--ring)' : 'none',
                    outline: 'none',
                  }} />
              )
            })}
          </div>
        </Row>

        <Row label="Density" desc="Tighten spacing to fit more studies on screen.">
          <div className="seg" role="group" aria-label="Interface density" style={{ display: 'flex' }}>
            {['comfortable', 'compact'].map((d) => (
              <button key={d} type="button" aria-pressed={density === d} onClick={() => setDensity(d)}
                style={{
                  padding: '7px 14px', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                  border: '1.5px solid ' + (density === d ? 'var(--primary)' : 'var(--border)'),
                  background: density === d ? 'var(--primary-tint)' : 'var(--surface)',
                  color: density === d ? 'var(--primary)' : 'var(--ink-2)',
                  borderRadius: d === 'comfortable' ? '10px 0 0 10px' : '0 10px 10px 0',
                  marginLeft: d === 'compact' ? -1.5 : 0,
                  textTransform: 'capitalize',
                }}>{d}</button>
            ))}
          </div>
        </Row>
      </section>

      {/* Preferences (AI & viewer) ------------------------------------------- */}
      <section style={card}>
        <div style={cardTitle}>Preferences</div>
        <div style={cardSub}>How the analyzer and viewer behave for you.</div>

        <Row label="Auto-show Grad-CAM" desc="Reveal the attention overlay as soon as a study opens." first>
          <Toggle label="Auto-show Grad-CAM" on={autoHeatmap}
            onChange={togglePref('autoHeatmap', autoHeatmap, setAutoHeatmap)} />
        </Row>
        <Row label="Voice dictation" desc="Enable browser speech-to-text in the findings field.">
          <Toggle label="Voice dictation" on={dictation}
            onChange={togglePref('dictation', dictation, setDictation)} />
        </Row>
      </section>

      {/* Notifications (roadmap) --------------------------------------------
          Honest framing: these preferences persist, but this build has no
          delivery path for either one — no email is sent and no push/alert is
          raised. They are saved so the choice survives for when delivery ships.
          Do NOT imply a working mechanism. */}
      <section style={card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={cardTitle}>Notifications</div>
          <span style={{
            fontSize: 10.5, fontWeight: 700, letterSpacing: 0.3, textTransform: 'uppercase',
            padding: '2px 8px', borderRadius: 99,
            background: 'var(--warn-tint)', color: 'var(--warn)',
          }}>Roadmap</span>
        </div>
        <div style={cardSub}>
          Not yet delivered in this build — flipping these saves your choice, but nothing is sent
          or alerted until a delivery path ships. No email leaves this browser.
        </div>

        <Row label="Email digests"
          desc="A periodic summary of your reporting activity. Saved as a preference — no email is delivered in this build."
          first>
          <Toggle label="Email digests" on={notifyEmail}
            onChange={togglePref('notifyEmail', notifyEmail, setNotifyEmail)} />
        </Row>
        <Row label="Critical-finding alerts"
          desc="Would surface an immediate alert when the AI flags a critical finding. Saved as a preference — no alert is raised in this build yet.">
          <Toggle label="Critical-finding alerts" on={notifyCritical}
            onChange={togglePref('notifyCritical', notifyCritical, setNotifyCritical)} />
        </Row>
      </section>

      {/* AI channels (read-only, server-gated) -------------------------------- */}
      <section style={card}>
        <div style={cardTitle}>AI channels</div>
        <div style={cardSub}>Which analysis modules this deployment exposes. Configured on the server, not here.</div>

        <Row label="Chest X-ray" desc="DenseNet-121 ensemble · pathology ranking scores, Grad-CAM, abstains on non-chest input." first>
          <span style={{
            fontSize: 11.5, fontWeight: 700, padding: '4px 11px', borderRadius: 99,
            background: 'var(--success-tint)', color: 'var(--success)',
          }}>LIVE</span>
        </Row>
        <Row label="CT / MRI AI" desc="Two opt-in channels — anatomy segmentation (labels organs, never a diagnosis) and an unvalidated research candidate detector. Server-gated and off by default.">
          <span style={{
            fontSize: 11.5, fontWeight: 700, padding: '4px 11px', borderRadius: 99,
            background: ctMriOn ? 'var(--primary-tint)' : 'var(--surface-3)',
            color: ctMriOn ? 'var(--primary)' : 'var(--muted)',
          }}>{ctMriOn ? 'SEGMENTATION' : 'OFF'}</span>
        </Row>
      </section>

      {/* Your data on this device -------------------------------------------- */}
      <section style={card}>
        <div style={cardTitle}>Your data on this device</div>
        <div style={{ ...cardSub, marginBottom: 14 }}>
          Patient identifiers and the report draft are kept only in this browser (never on the server). Clear them any
          time.
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button className="btn btn-small" onClick={clearIdentifiers}>Clear patient identifiers</button>
          <button className="btn btn-small" onClick={clearDraft}>Clear saved report draft</button>
          <button className="btn btn-small" onClick={resetTheme}>Reset theme</button>
        </div>
        {msg && <p className="muted small set-msg" role="status" style={{ marginTop: 12 }}>{msg}</p>}
      </section>

      {/* Diagnostics --------------------------------------------------------- */}
      <section style={card}>
        <div style={cardTitle}>Diagnostics log</div>
        <div style={{ ...cardSub, marginBottom: 12 }}>
          A local record of API calls, timings, and errors (with reasons) — useful when reporting an issue. Response
          contents are never logged, so this is safe to copy or download.
        </div>
        <LogViewer />
      </section>
    </div>
  )
}
