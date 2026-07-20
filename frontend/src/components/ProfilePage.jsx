import { useEffect, useState, useCallback } from 'react'
import { me, logout } from '../api.js'
import TwoFactorCard from './account/TwoFactorCard.jsx'
import SessionsCard from './account/SessionsCard.jsx'

// Account hub in the console look. Every value is derived from the live me() probe —
// never invented. When AUTH_ENABLED is on and the caller is signed in, this becomes a
// real self-service account/security surface (2FA + active sessions). When auth is off
// (open demo) or the caller is signed out, it honestly explains that 2FA and session
// management require signing in on an auth-enabled deployment.
//   meInfo?: { auth_enabled, authenticated, user, mfa_enrolled, mfa_pending }
//   onNav?:  (route) => void
//   onSignedOut?: (freshMe) => void  — parent's meInfo setter; also used to push a
//                                       refreshed me() after any account change.
export default function ProfilePage({ meInfo = null, onNav, onSignedOut } = {}) {
  const [info, setInfo] = useState(meInfo)

  useEffect(() => {
    if (meInfo) { setInfo(meInfo); return }
    let alive = true
    me().then((r) => { if (alive) setInfo(r) })
    return () => { alive = false }
  }, [meInfo])

  // Re-probe me() and propagate to the parent so the whole console (and the auth gate)
  // reflects any account change made here (2FA on/off, current session revoked).
  const refresh = useCallback(async () => {
    const r = await me()
    setInfo(r)
    onSignedOut?.(r)
    return r
  }, [onSignedOut])

  const authed = !!info?.authenticated
  const authOn = !!info?.auth_enabled

  // Persona derived strictly from the session — no placeholder identity.
  let initials, name, role, status
  if (!info) {
    initials = '·'; name = 'Checking session…'; role = 'Contacting the workspace'; status = null
  } else if (authed) {
    initials = (info.user?.trim()?.[0] || 'U').toUpperCase()
    name = info.user || 'Signed-in user'
    role = 'Authenticated session'
    status = { label: 'Signed in', color: 'var(--success)', tint: 'var(--success-tint)' }
  } else if (authOn) {
    initials = '🔒'
    name = 'Not signed in'
    role = 'Authentication is enabled on this deployment'
    status = { label: 'Signed out', color: 'var(--warn)', tint: 'var(--warn-tint)' }
  } else {
    initials = 'G'
    name = 'Guest'
    role = 'Open demo — this deployment runs without sign-in'
    status = { label: 'Open demo', color: 'var(--muted)', tint: 'var(--surface-3)' }
  }

  const sessionRows = [
    { label: 'Sign-in', value: authed ? 'Signed in' : 'Not signed in' },
    { label: 'Authentication', value: info == null ? '…' : authOn ? 'Enabled on this deployment' : 'Not enabled (open demo)' },
    { label: 'Account', value: authed ? (info.user || '—') : 'No server-side account in this build' },
    { label: 'Two-factor', value: !authed ? '—' : info.mfa_enrolled ? 'On' : info.mfa_pending ? 'Pending' : 'Off' },
  ]

  const card = {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 16, padding: '20px 22px', boxShadow: 'var(--shadow-sm)',
  }
  const heading = { fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: 16, marginBottom: 14 }

  return (
    <div style={{ padding: '26px 28px 44px', maxWidth: 1100, margin: '0 auto' }}>
      {/* Banner + identity header */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 18, overflow: 'hidden', boxShadow: 'var(--shadow-sm)' }}>
        <div style={{ height: 96, background: 'linear-gradient(120deg,var(--primary),var(--teal))', position: 'relative' }}>
          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(400px 160px at 78% -20%,rgba(255,255,255,.25),transparent 60%)' }} aria-hidden="true" />
        </div>
        <div style={{ padding: '16px 26px 22px', display: 'flex', alignItems: 'flex-end', gap: 18, flexWrap: 'wrap' }}>
          <div aria-hidden="true" style={{ width: 84, height: 84, flex: 'none', borderRadius: 22, background: 'linear-gradient(135deg,var(--primary),var(--teal))', display: 'grid', placeItems: 'center', color: '#fff', fontFamily: 'var(--font-head)', fontWeight: 700, fontSize: 30, border: '4px solid var(--surface)', boxShadow: 'var(--shadow)', marginTop: -58, marginBottom: -4 }}>
            {initials}
          </div>
          <div style={{ flex: 1, minWidth: 200, paddingBottom: 2 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <h2 style={{ fontSize: 23, fontWeight: 700 }}>{name}</h2>
              {status && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 600, color: status.color, background: status.tint, padding: '3px 9px', borderRadius: 99 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 99, background: status.color }} />
                  {status.label}
                </span>
              )}
            </div>
            <div style={{ fontSize: 14, color: 'var(--muted)', marginTop: 3 }}>{role}</div>
          </div>
          <div style={{ display: 'flex', gap: 9, paddingBottom: 2, flexWrap: 'wrap' }}>
            {onNav && <HeaderBtn onClick={() => onNav('settings')}>Settings</HeaderBtn>}
            {authed && (
              <HeaderBtn primary onClick={() => logout().then(refresh)}>Sign out</HeaderBtn>
            )}
          </div>
        </div>
      </div>

      {/* Two-column detail — honest session facts + privacy posture */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: 16, marginTop: 16 }}>
        <section style={card}>
          <div style={heading}>Session</div>
          {sessionRows.map((r, i) => (
            <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, padding: '10px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border)' }}>
              <span style={{ fontSize: 13.5, color: 'var(--muted)' }}>{r.label}</span>
              <span style={{ fontSize: 13.5, color: 'var(--ink)', fontWeight: 500, textAlign: 'right' }}>{r.value}</span>
            </div>
          ))}
          {info && authOn && !authed && (
            <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 12, lineHeight: 1.5 }}>
              Sign in to use the protected features on this deployment.
            </p>
          )}
        </section>

        <section style={card}>
          <div style={heading}>What we keep about you</div>
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[
              'No personal account, profile data, or tracking is stored on the server.',
              'Patient identifiers you enter for a report live only in this browser and never reach the server.',
              'Your theme choice and diagnostics log are local to this browser (manage them in Settings).',
            ].map((t) => (
              <li key={t} style={{ display: 'flex', gap: 10, fontSize: 13.5, color: 'var(--muted)', lineHeight: 1.5 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--teal-2)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" style={{ flex: 'none', marginTop: 2 }} aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* Security surface — real self-service ONLY when signed in on an auth deployment. */}
      {authed ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16, marginTop: 16 }}>
          <TwoFactorCard
            mfaEnrolled={!!info.mfa_enrolled}
            mfaPending={!!info.mfa_pending}
            onChanged={refresh}
          />
          <SessionsCard onCurrentRevoked={refresh} />
        </div>
      ) : (
        <section style={{ ...card, marginTop: 16 }}>
          <div style={heading}>Security</div>
          <p style={{ fontSize: 13.5, color: 'var(--muted)', lineHeight: 1.6 }}>
            {authOn
              ? 'Two-factor authentication and active-session management become available here once you sign in.'
              : 'This is an open demo running without sign-in, so there is no account to secure. Two-factor authentication and session management are available only on a deployment with authentication enabled.'}
          </p>
        </section>
      )}
    </div>
  )
}

// Header action button with hover + keyboard focus ring (inline-styled, CSS-var driven).
function HeaderBtn({ children, onClick, primary = false }) {
  const [hot, setHot] = useState(false)
  const [foc, setFoc] = useState(false)
  const base = {
    padding: '10px 16px', borderRadius: 10, fontWeight: 600, fontSize: 13.5,
    cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
    transition: 'background .15s,border-color .15s,color .15s',
    outline: foc ? '2px solid transparent' : 'none',
    boxShadow: foc ? 'var(--ring)' : primary ? 'var(--shadow-sm)' : 'none',
  }
  const style = primary
    ? { ...base, border: 'none', background: hot ? 'var(--primary-2)' : 'var(--primary)', color: '#fff' }
    : { ...base, border: '1px solid var(--border-2)', background: 'var(--surface)', color: hot ? 'var(--primary)' : 'var(--ink)', borderColor: hot ? 'var(--primary)' : 'var(--border-2)' }
  return (
    <button
      type="button" onClick={onClick} style={style}
      onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      onFocus={() => setFoc(true)} onBlur={() => setFoc(false)}
    >
      {children}
    </button>
  )
}
