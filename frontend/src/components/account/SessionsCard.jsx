import { useEffect, useState, useCallback } from 'react'
import { sessions as fetchSessions, revokeSession, revokeOtherSessions } from '../../api.js'
import Btn from './Btn.jsx'
import { cardStyle, headingStyle } from './ui.js'

// ACTIVE SESSIONS card. Lists ONLY the caller's own live sessions (the server scopes
// them). Honest about the stateless case: when the DB is off (supported=false) it says
// so instead of faking history. Shows only facts the server truly has — created /
// last-seen timestamps + the raw User-Agent string; NEVER a raw IP (ip_hash only, and
// even that is shown as an opaque short fingerprint). Any action re-fetches the list.
export default function SessionsCard({ onCurrentRevoked }) {
  const [state, setState] = useState({ loading: true, supported: true, sessions: [] })
  const [busySid, setBusySid] = useState(null)   // sid being revoked, or '__others__'
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    const r = await fetchSessions()
    setState({ loading: false, supported: r.supported !== false, sessions: r.sessions || [] })
  }, [])

  useEffect(() => { load() }, [load])

  async function onRevoke(s) {
    setBusySid(s.sid); setError(null)
    try {
      await revokeSession(s.sid)
      if (s.is_current) { onCurrentRevoked?.(); return }
      await load()
    } catch (e) {
      setError(e.message || 'Could not revoke that session.')
    } finally {
      setBusySid(null)
    }
  }

  async function onRevokeOthers() {
    setBusySid('__others__'); setError(null)
    try {
      await revokeOtherSessions()
      await load()
    } catch (e) {
      setError(e.message || 'Could not sign out other devices.')
    } finally {
      setBusySid(null)
    }
  }

  const others = state.sessions.filter((s) => !s.is_current).length

  return (
    <section style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={headingStyle}>
          <DevicesIcon />
          Active sessions
        </div>
        {state.supported && !state.loading && others > 0 && (
          <Btn size="sm" variant="danger" onClick={onRevokeOthers} disabled={busySid === '__others__'}>
            {busySid === '__others__' ? 'Signing out…' : 'Sign out of all other devices'}
          </Btn>
        )}
      </div>

      {state.loading && (
        <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 14 }}>Loading sessions…</p>
      )}

      {/* Honest stateless case */}
      {!state.loading && !state.supported && (
        <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 14, lineHeight: 1.55 }}>
          Session history requires the database. This deployment is stateless
          (<code style={inlineMono}>DATABASE_URL</code> is not set), so individual sessions
          aren’t tracked and can’t be listed or revoked here.
        </p>
      )}

      {!state.loading && state.supported && state.sessions.length === 0 && (
        <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 14 }}>No active sessions found.</p>
      )}

      {!state.loading && state.supported && state.sessions.length > 0 && (
        <ul style={{ listStyle: 'none', marginTop: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {state.sessions.map((s) => (
            <li key={s.sid} style={{
              display: 'flex', gap: 12, alignItems: 'flex-start', justifyContent: 'space-between',
              flexWrap: 'wrap', padding: '12px 14px', borderRadius: 12,
              border: '1px solid var(--border)',
              background: s.is_current ? 'var(--primary-tint)' : 'var(--surface-2)',
            }}>
              <div style={{ minWidth: 200, flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>
                    {deviceLabel(s.user_agent)}
                  </span>
                  {s.is_current && (
                    <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--primary)', background: 'var(--surface)', border: '1px solid var(--primary)', borderRadius: 99, padding: '1px 8px' }}>
                      This device
                    </span>
                  )}
                </div>
                {s.user_agent && (
                  <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 4, wordBreak: 'break-word' }}>
                    {s.user_agent}
                  </div>
                )}
                <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 5, display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                  <span>Signed in {fmt(s.created_at)}</span>
                  <span>Last active {fmt(s.last_seen)}</span>
                </div>
              </div>
              <Btn size="sm" variant="danger" onClick={() => onRevoke(s)} disabled={busySid === s.sid}>
                {busySid === s.sid ? 'Revoking…' : s.is_current ? 'Sign out' : 'Revoke'}
              </Btn>
            </li>
          ))}
        </ul>
      )}

      {error && <div role="alert" style={errorStyle}>{error}</div>}
    </section>
  )
}

// A coarse, honest device label from the User-Agent (no invented OS/location strings).
// We only surface what the UA string itself contains; unknown -> a neutral label.
function deviceLabel(ua) {
  if (!ua) return 'Unknown device'
  const s = ua.toLowerCase()
  let os = ''
  if (s.includes('windows')) os = 'Windows'
  else if (s.includes('mac os') || s.includes('macintosh')) os = 'macOS'
  else if (s.includes('android')) os = 'Android'
  else if (s.includes('iphone') || s.includes('ipad') || s.includes('ios')) os = 'iOS'
  else if (s.includes('linux')) os = 'Linux'
  let br = ''
  if (s.includes('edg/')) br = 'Edge'
  else if (s.includes('chrome/') && !s.includes('edg/')) br = 'Chrome'
  else if (s.includes('firefox/')) br = 'Firefox'
  else if (s.includes('safari/') && !s.includes('chrome/')) br = 'Safari'
  const parts = [br, os].filter(Boolean)
  return parts.length ? parts.join(' on ') : 'Browser session'
}

function fmt(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

const inlineMono = { fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-2)' }
const errorStyle = {
  marginTop: 12, fontSize: 12.5, color: 'var(--danger)', background: 'var(--danger-tint)',
  border: '1px solid color-mix(in srgb, var(--danger) 38%, transparent)',
  borderRadius: 8, padding: '8px 10px',
}

function DevicesIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="4" width="14" height="10" rx="2" /><path d="M2 18h14" /><rect x="18" y="9" width="4" height="11" rx="1" />
    </svg>
  )
}
