import { useEffect, useState } from 'react'
import { login, verify2fa, csrf, me } from '../api.js'
import ThemeToggle from './ThemeToggle.jsx'

/**
 * Sign-in screen (design lines 1014-1050): a 2-column layout — a branded left
 * panel with honest product stats, and a right-hand credential form.
 *
 * Real auth, wired to the hardened backend contract:
 *   1. POST /api/login (work-email + password). If the account has confirmed 2FA,
 *      the backend answers { authenticated:false, mfa_required:true } and sets a
 *      HALF session; we then reveal the 2FA code step.
 *   2. POST /api/2fa/verify { code } completes the login (backend rotates the
 *      session + issues a fresh CSRF cookie).
 *   3. On full success we prime a CSRF token and call onAuthed(user) so App flips
 *      into the authenticated console.
 *
 * HONESTY: SSO/SAML is a clearly-disabled Roadmap affordance (never a working
 * login). "Forgot password?" opens an operator/roadmap note, not a fake reset.
 * The 2FA step only appears when the backend actually demands it for this account.
 */
const REMEMBER_KEY = 'radassist_login_email'

export default function Login({ onAuthed, onNav }) {
  const [step, setStep] = useState('creds') // 'creds' | '2fa'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [remember, setRemember] = useState(false)
  const [forgotOpen, setForgotOpen] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)

  // "Remember me" (honest, local-only): prefill the last work-email. The session
  // lifetime is fixed server-side, so we don't pretend to extend it — we just save
  // the identifier the user opted to have remembered.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(REMEMBER_KEY)
      if (saved) { setEmail(saved); setRemember(true) }
    } catch { /* ignore */ }
  }, [])

  // Demo login: when the backend runs in AUTH_DEMO_MODE it publishes test
  // credentials so anyone can experience the real login flow. Shown ONLY when the
  // server reports demo mode (never surfaced in a real deployment with real users).
  const [demo, setDemo] = useState(null)
  useEffect(() => {
    let live = true
    me().then((info) => {
      if (live && info?.demo_mode && info?.demo_credentials) setDemo(info.demo_credentials)
    }).catch(() => { /* ignore */ })
    return () => { live = false }
  }, [])

  async function finish(user) {
    // Ensure a fresh CSRF token/cookie is in place before the app makes its first
    // protected, state-changing request.
    try { await csrf() } catch { /* best-effort */ }
    try {
      if (remember) localStorage.setItem(REMEMBER_KEY, email.trim())
      else localStorage.removeItem(REMEMBER_KEY)
    } catch { /* ignore */ }
    setPassword(''); setCode('')
    onAuthed?.(user)
  }

  async function handleCreds(e) {
    e.preventDefault()
    if (busy) return
    setBusy(true); setError(null); setNotice(null)
    try {
      const res = await login(email.trim(), password)
      if (res?.authenticated) {
        await finish(res.user)
      } else if (res?.mfa_required) {
        setStep('2fa') // account has confirmed 2FA — reveal the code step
      } else if (res && res.auth_enabled === false) {
        setNotice(res.detail || 'Authentication is disabled; the demo is open.')
      } else {
        setError(res?.detail || 'Sign in failed.')
      }
    } catch (err) {
      setError(err.message || 'Sign in failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleVerify(e) {
    e.preventDefault()
    if (busy) return
    setBusy(true); setError(null)
    try {
      const res = await verify2fa(code.trim())
      if (res?.authenticated) await finish(res.user)
      else setError(res?.detail || 'Verification failed.')
    } catch (err) {
      setError(err.message || 'Invalid or expired code.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-grid" style={S.root}>
      {/* Scoped responsive rule: on narrow viewports the two-column layout would
          cram the fixed-padding brand panel against the form and overflow, so we
          collapse to a single column and hide the decorative brand panel. */}
      <style>{`
        @media (max-width: 820px) {
          .login-grid { grid-template-columns: 1fr !important; }
          .login-brand { display: none !important; }
        }
      `}</style>
      {/* ---- Left: brand panel + honest stats ---- */}
      <div className="login-brand" style={S.brand}>
        <div aria-hidden="true" style={S.brandGlow} />
        <button type="button" onClick={() => onNav?.('home')} style={S.logoBtn}>
          <span style={S.logoMark}>
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round">
              <path d="M12 3v18M3 12h18" /><circle cx="12" cy="12" r="9" />
            </svg>
          </span>
          <span style={S.logoWord}>Rad<span style={{ color: '#6db2ff' }}>Assist</span></span>
        </button>

        <div style={{ marginTop: 'auto', position: 'relative', zIndex: 2 }}>
          <div style={S.pill}>
            <span style={S.pillDot} />Explainable AI radiology
          </div>
          <h1 style={S.brandHead}>Welcome back to<br />your reading room</h1>
          <p style={S.brandSub}>
            Pick up your worklist, review AI suggestions and sign reports — with every
            finding traceable to its evidence.
          </p>
          <div style={{ display: 'flex', gap: 26, marginTop: 32, flexWrap: 'wrap' }}>
            <Stat value="18" label="pathologies / film" />
            <Stat value="100%" label="clinician-signed" />
          </div>
        </div>
      </div>

      {/* ---- Right: form ---- */}
      <div style={S.formPane}>
        <div style={{ width: '100%', maxWidth: 380 }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 24 }}>
            <ThemeToggle />
          </div>

          {step === 'creds' ? (
            <form onSubmit={handleCreds} noValidate>
              <h2 style={S.h2}>Sign in</h2>
              <p style={S.lede}>Use your organisation credentials.</p>

              {/* Demo access — only rendered when the backend is in AUTH_DEMO_MODE */}
              {demo && (
                <div style={S.demoCard} role="note">
                  <div style={S.demoHead}>
                    <span style={S.demoBadge}>Demo</span>
                    <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--ink)' }}>Test credentials</span>
                  </div>
                  <div style={S.demoRow}><span style={S.demoK}>User</span><code style={S.demoV}>{demo.username}</code></div>
                  <div style={S.demoRow}><span style={S.demoK}>Pass</span><code style={S.demoV}>{demo.password}</code></div>
                  <button type="button" style={S.demoBtn}
                    onClick={() => { setEmail(demo.username); setPassword(demo.password); setError(null); setNotice(null) }}>
                    Fill demo credentials
                  </button>
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8, lineHeight: 1.4 }}>
                    Published demo login — insecure by design, for evaluation only.
                  </div>
                </div>
              )}

              {/* SSO/SAML — clearly disabled Roadmap affordance, never a working login */}
              <button type="button" disabled aria-disabled="true"
                title="Single sign-on is on the roadmap and not available yet" style={S.ssoBtn}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: .8 }}>
                  <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3" />
                </svg>
                Continue with SSO (SAML)
                <span style={S.roadmapTag}>Roadmap</span>
              </button>

              <div style={S.divider}>
                <span style={S.dividerLine} /><span style={S.dividerTxt}>or</span><span style={S.dividerLine} />
              </div>

              <label htmlFor="login-email" style={S.label}>Work email</label>
              <Input id="login-email" type="email" autoComplete="username" placeholder="a.rao@metroimaging.org"
                value={email} onChange={setEmail} disabled={busy} required />

              <label htmlFor="login-password" style={{ ...S.label, display: 'block', marginTop: 14 }}>Password</label>
              <PasswordInput id="login-password" autoComplete="current-password" placeholder="••••••••••"
                value={password} onChange={setPassword} disabled={busy} required />

              <div style={S.row}>
                <label style={S.remember}>
                  <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)}
                    style={{ accentColor: 'var(--primary)', width: 15, height: 15 }} />
                  Remember me
                </label>
                <button type="button" onClick={() => setForgotOpen((v) => !v)} style={S.link}>Forgot password?</button>
              </div>

              {forgotOpen && (
                <div style={S.note} role="note">
                  Password resets are handled by your organisation's identity administrator —
                  RadAssist has no self-service reset in this build. {onNav && (
                    <button type="button" onClick={() => onNav('help')} style={S.noteLink}>See Help</button>
                  )}
                </div>
              )}

              {error && <div style={S.error} role="alert">{error}</div>}
              {notice && <div style={S.notice} role="status">{notice}</div>}

              <PrimaryButton disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</PrimaryButton>

              <div style={S.secline}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" />
                </svg>
                Session secured with a signed, HttpOnly cookie
              </div>

              <div style={S.foot}>
                New to RadAssist?{' '}
                <button type="button" onClick={() => onNav?.('home')} style={S.footLink}>Learn more</button>
              </div>
            </form>
          ) : (
            /* ---- 2FA step: shown ONLY when the backend demanded it for this login ---- */
            <form onSubmit={handleVerify} noValidate>
              <h2 style={S.h2}>Two-factor verification</h2>
              <p style={S.lede}>
                Enter the 6-digit code from your authenticator app to finish signing in
                {email.trim() ? <> as <strong style={{ color: 'var(--ink)' }}>{email.trim()}</strong></> : null}.
              </p>

              <label htmlFor="login-code" style={{ ...S.label, display: 'block', marginTop: 6 }}>Authentication code</label>
              <Input id="login-code" type="text" inputMode="numeric" autoComplete="one-time-code"
                placeholder="123 456" value={code}
                onChange={(v) => setCode(v.replace(/[^\d]/g, '').slice(0, 6))}
                disabled={busy} autoFocus mono required />

              {error && <div style={S.error} role="alert">{error}</div>}

              <PrimaryButton disabled={busy || code.length < 6}>{busy ? 'Verifying…' : 'Verify & sign in'}</PrimaryButton>

              <div style={S.secline}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" />
                </svg>
                Two-factor authentication is enabled for this account
              </div>

              <div style={S.foot}>
                <button type="button" onClick={() => { setStep('creds'); setError(null); setCode('') }} style={S.footLink}>
                  ← Back to sign in
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

function Stat({ value, label }) {
  return (
    <div>
      <div className="mono" style={{ fontSize: 26, fontWeight: 600, color: '#fff' }}>{value}</div>
      <div style={{ fontSize: 12, color: '#8fb3e6' }}>{label}</div>
    </div>
  )
}

// Text input with a focus ring driven by React state (inline styles can't use :focus).
function Input({ value, onChange, mono = false, ...rest }) {
  const [foc, setFoc] = useState(false)
  return (
    <input
      {...rest}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onFocus={() => setFoc(true)}
      onBlur={() => setFoc(false)}
      className={mono ? 'mono' : undefined}
      style={{
        width: '100%', marginTop: 6, padding: '12px 14px', borderRadius: 11,
        border: `1px solid ${foc ? 'var(--primary)' : 'var(--border)'}`,
        background: 'var(--surface)', fontFamily: mono ? undefined : 'inherit',
        fontSize: mono ? 18 : 14, letterSpacing: mono ? '.28em' : undefined,
        color: 'var(--ink)', outline: 'none',
        boxShadow: foc ? 'var(--ring)' : 'none', boxSizing: 'border-box',
      }}
    />
  )
}

// Password input with a show/hide eye toggle. State-driven focus ring (inline
// styles can't use :focus), and the type flips between password/text on toggle.
function PasswordInput({ value, onChange, ...rest }) {
  const [foc, setFoc] = useState(false)
  const [show, setShow] = useState(false)
  return (
    <div style={{ position: 'relative', marginTop: 6 }}>
      <input
        {...rest}
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFoc(true)}
        onBlur={() => setFoc(false)}
        style={{
          width: '100%', padding: '12px 46px 12px 14px', borderRadius: 11,
          border: `1px solid ${foc ? 'var(--primary)' : 'var(--border)'}`,
          background: 'var(--surface)', fontFamily: 'inherit', fontSize: 14,
          color: 'var(--ink)', outline: 'none',
          boxShadow: foc ? 'var(--ring)' : 'none', boxSizing: 'border-box',
        }}
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? 'Hide password' : 'Show password'}
        aria-pressed={show}
        title={show ? 'Hide password' : 'Show password'}
        style={{
          position: 'absolute', top: '50%', right: 7, transform: 'translateY(-50%)',
          width: 32, height: 32, display: 'grid', placeItems: 'center', borderRadius: 8,
          background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)',
        }}
      >
        {show ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a13.2 13.2 0 0 1-1.67 2.68" />
            <path d="M6.61 6.61A13.5 13.5 0 0 0 2 12s3 8 10 8a9.7 9.7 0 0 0 5.39-1.61" />
            <line x1="2" y1="2" x2="22" y2="22" />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M2 12s3-8 10-8 10 8 10 8-3 8-10 8-10-8-10-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        )}
      </button>
    </div>
  )
}

function PrimaryButton({ children, disabled }) {
  const [hot, setHot] = useState(false)
  return (
    <button type="submit" disabled={disabled}
      onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{
        width: '100%', marginTop: 20, padding: 13, borderRadius: 11, border: 'none',
        background: disabled ? 'var(--primary)' : hot ? 'var(--primary-2)' : 'var(--primary)',
        color: '#fff', fontWeight: 600, fontSize: 15, fontFamily: 'inherit',
        cursor: disabled ? 'default' : 'pointer', opacity: disabled ? .72 : 1,
        boxShadow: 'var(--shadow-sm)',
      }}>
      {children}
    </button>
  )
}

// ---- Inline style map (mirrors design lines 1014-1050) --------------------
const S = {
  root: { minHeight: '100vh', display: 'grid', gridTemplateColumns: '1.05fr .95fr' },
  brand: {
    position: 'relative', background: 'linear-gradient(155deg,var(--navy),#0a1526)',
    overflow: 'hidden', padding: '52px 56px', display: 'flex', flexDirection: 'column', color: '#fff',
  },
  brandGlow: {
    position: 'absolute', inset: 0,
    background: 'radial-gradient(600px 400px at 80% 10%,rgba(34,211,199,.18),transparent 60%),radial-gradient(500px 400px at 10% 90%,rgba(59,130,246,.2),transparent 55%)',
  },
  logoBtn: { display: 'flex', alignItems: 'center', gap: 11, background: 'none', border: 'none', cursor: 'pointer', padding: 0, position: 'relative', zIndex: 2 },
  logoMark: { width: 36, height: 36, borderRadius: 10, display: 'grid', placeItems: 'center', background: 'linear-gradient(135deg,var(--primary),var(--teal))' },
  logoWord: { fontFamily: 'var(--font-head)', fontWeight: 700, fontSize: 20, color: '#fff' },
  pill: {
    display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 13px', borderRadius: 99,
    background: 'rgba(34,211,199,.14)', border: '1px solid rgba(34,211,199,.3)', color: '#5eead4', fontWeight: 600, fontSize: 12.5,
  },
  pillDot: { width: 7, height: 7, borderRadius: 99, background: '#22d3c7', animation: 'pulseDot 1.8s infinite' },
  brandHead: { fontSize: 38, fontWeight: 800, margin: '20px 0 0', letterSpacing: '-.03em', color: '#fff', lineHeight: 1.1 },
  brandSub: { color: '#a9c0e0', fontSize: 16, margin: '16px 0 0', maxWidth: 400, lineHeight: 1.6 },
  formPane: { display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 32px', background: 'var(--bg)' },
  h2: { fontSize: 26, fontWeight: 700 },
  lede: { color: 'var(--muted)', fontSize: 14, marginTop: 5, lineHeight: 1.5 },
  demoCard: {
    marginTop: 16, padding: '14px 16px', borderRadius: 12, background: 'var(--teal-tint)',
    border: '1px solid color-mix(in srgb, var(--teal) 34%, transparent)',
  },
  demoHead: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 },
  demoBadge: {
    fontSize: 10.5, fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase',
    padding: '2px 8px', borderRadius: 99, background: 'var(--teal-2)', color: '#fff',
  },
  demoRow: { display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 },
  demoK: { fontSize: 11.5, fontWeight: 600, color: 'var(--muted)', width: 38 },
  demoV: {
    fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink)', background: 'var(--surface)',
    padding: '2px 8px', borderRadius: 6, border: '1px solid var(--border)',
  },
  demoBtn: {
    marginTop: 12, width: '100%', padding: 9, borderRadius: 9, border: '1px solid var(--teal-2)',
    background: 'var(--surface)', color: 'var(--teal-2)', fontWeight: 600, fontSize: 13,
    cursor: 'pointer', fontFamily: 'inherit',
  },
  ssoBtn: {
    width: '100%', marginTop: 22, padding: 12, borderRadius: 11, border: '1px solid var(--border-2)',
    background: 'var(--surface)', color: 'var(--faint)', fontWeight: 600, fontSize: 14, fontFamily: 'inherit',
    cursor: 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
  },
  roadmapTag: {
    marginLeft: 2, fontSize: 10.5, fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase',
    padding: '2px 7px', borderRadius: 99, background: 'var(--primary-tint)', color: 'var(--primary)',
  },
  divider: { display: 'flex', alignItems: 'center', gap: 12, margin: '20px 0' },
  dividerLine: { flex: 1, height: 1, background: 'var(--border)' },
  dividerTxt: { fontSize: 12, color: 'var(--faint)' },
  label: { fontSize: 12.5, fontWeight: 600, color: 'var(--ink-2)' },
  row: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 14, gap: 12 },
  remember: { fontSize: 13, color: 'var(--ink-2)', display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' },
  link: { fontSize: 13, fontWeight: 600, color: 'var(--primary)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: 0 },
  note: {
    marginTop: 12, padding: '10px 12px', borderRadius: 10, background: 'var(--surface-2, var(--surface))',
    border: '1px solid var(--border)', fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.5,
  },
  noteLink: { color: 'var(--primary)', fontWeight: 600, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 12.5, padding: 0 },
  error: {
    marginTop: 14, padding: '10px 12px', borderRadius: 10, background: 'var(--danger-tint, rgba(220,38,38,.1))',
    border: '1px solid var(--danger, #dc2626)', color: 'var(--danger, #dc2626)', fontSize: 13, lineHeight: 1.4,
  },
  notice: {
    marginTop: 14, padding: '10px 12px', borderRadius: 10, background: 'var(--primary-tint)',
    border: '1px solid var(--border)', color: 'var(--ink-2)', fontSize: 13, lineHeight: 1.4,
  },
  secline: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, fontSize: 12, color: 'var(--muted)', justifyContent: 'center' },
  foot: { textAlign: 'center', marginTop: 22, fontSize: 13, color: 'var(--muted)' },
  footLink: { color: 'var(--primary)', fontWeight: 600, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, padding: 0 },
}
