import { useState } from 'react'
import { enroll2fa, verify2fa, disable2fa } from '../../api.js'
import Btn from './Btn.jsx'
import { cardStyle, headingStyle, pillStyle } from './ui.js'

// TWO-FACTOR AUTHENTICATION card. Honest, server-truthful states only:
//   mfaEnrolled=true            -> On   (offer Disable)
//   mfaPending=true             -> Pending (a confirmed enrollment exists but this
//                                  session hasn't cleared it; nothing to do here)
//   otherwise                   -> Off  (offer Enable)
// Enable: POST /api/2fa/enroll -> render the otpauth QR (bundled `qrcode`, data URL,
// CSP-safe) + the copyable base32 secret -> user scans -> 6-digit verify. Disable:
// require the current TOTP code -> POST /api/2fa/disable. onChanged() re-probes me().
export default function TwoFactorCard({ mfaEnrolled, mfaPending, onChanged }) {
  // mode: 'idle' | 'enrolling' | 'disabling'
  const [mode, setMode] = useState('idle')
  const [enroll, setEnroll] = useState(null)   // { secret, otpauth_uri, ... }
  const [qr, setQr] = useState(null)           // data-URL PNG, or null if lib fell back
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)

  const status = mfaEnrolled
    ? { label: 'On', color: 'var(--success)', tint: 'var(--success-tint)' }
    : mfaPending
      ? { label: 'Pending', color: 'var(--warn)', tint: 'var(--warn-tint)' }
      : { label: 'Off', color: 'var(--muted)', tint: 'var(--surface-3)' }

  function reset() {
    setMode('idle'); setEnroll(null); setQr(null); setCode(''); setError(null); setBusy(false); setCopied(false)
  }

  async function startEnroll() {
    setBusy(true); setError(null)
    try {
      const r = await enroll2fa()
      setEnroll(r); setMode('enrolling'); setCode('')
      // Render the QR from the otpauth URI with the bundled lib -> a data: URL PNG
      // (no network, CSP-safe). If it ever fails we simply show the secret + URI as
      // copyable text below — never a fabricated/placeholder QR.
      try {
        const QRCode = (await import('qrcode')).default
        const url = await QRCode.toDataURL(r.otpauth_uri, { margin: 1, width: 200 })
        setQr(url)
      } catch {
        setQr(null)
      }
    } catch (e) {
      setError(e.message || 'Could not start two-factor enrollment.')
    } finally {
      setBusy(false)
    }
  }

  async function confirmEnroll(e) {
    e?.preventDefault?.()
    setBusy(true); setError(null)
    try {
      await verify2fa(code.trim())
      reset()
      onChanged?.()
    } catch (err) {
      setError(err.message || 'Invalid or expired code.')
    } finally {
      setBusy(false)
    }
  }

  async function confirmDisable(e) {
    e?.preventDefault?.()
    setBusy(true); setError(null)
    try {
      await disable2fa(code.trim())
      reset()
      onChanged?.()
    } catch (err) {
      setError(err.message || 'Could not disable two-factor authentication.')
    } finally {
      setBusy(false)
    }
  }

  function copySecret() {
    const s = enroll?.secret
    if (!s) return
    navigator.clipboard?.writeText(s).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 1600)
    }).catch(() => { /* clipboard unavailable — the secret is visible to copy manually */ })
  }

  return (
    <section style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={headingStyle}>
          <LockIcon />
          Two-factor authentication
        </div>
        <span style={pillStyle(status.color, status.tint)}>
          <span style={{ width: 8, height: 8, borderRadius: 99, background: status.color }} />
          {status.label}
        </span>
      </div>

      <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 12, lineHeight: 1.5 }}>
        {mfaEnrolled
          ? 'A time-based code from your authenticator app is required at every sign-in.'
          : mfaPending
            ? 'This account has a confirmed authenticator, but this session has not completed a code challenge.'
            : 'Add a second step at sign-in with a time-based code from an authenticator app.'}
      </p>

      {/* ---- OFF: enable flow ---- */}
      {!mfaEnrolled && !mfaPending && mode === 'idle' && (
        <div style={{ marginTop: 14 }}>
          <Btn variant="primary" onClick={startEnroll} disabled={busy}>
            {busy ? 'Starting…' : 'Enable 2FA'}
          </Btn>
        </div>
      )}

      {mode === 'enrolling' && enroll && (
        <div style={{ marginTop: 16 }}>
          <ol style={{ margin: '0 0 14px', paddingLeft: 18, fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.7 }}>
            <li>Open your authenticator app (Google Authenticator, Authy, 1Password…).</li>
            <li>Scan the QR code below, or enter the secret key by hand.</li>
            <li>Enter the 6-digit code the app shows to confirm.</li>
          </ol>

          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'flex-start' }}>
            {qr ? (
              <img
                src={qr} width={180} height={180} alt="Two-factor QR code for your authenticator app"
                style={{ borderRadius: 12, border: '1px solid var(--border)', background: '#fff', padding: 8, flex: 'none' }}
              />
            ) : (
              <div style={{ fontSize: 12.5, color: 'var(--muted)', maxWidth: 280, lineHeight: 1.6 }}>
                QR rendering is unavailable in this build — add the account to your app using the
                setup key and the URI below.
                <div style={{ ...secretBox, marginTop: 8, wordBreak: 'break-all', fontSize: 11.5 }}>{enroll.otpauth_uri}</div>
              </div>
            )}

            <div style={{ flex: 1, minWidth: 220 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 6, fontWeight: 600 }}>Setup key</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <code style={secretBox}>{enroll.secret}</code>
                <Btn size="sm" onClick={copySecret}>{copied ? 'Copied' : 'Copy'}</Btn>
              </div>

              <form onSubmit={confirmEnroll} style={{ marginTop: 16 }}>
                <label htmlFor="tfa-enroll-code" style={labelStyle}>6-digit code</label>
                <input
                  id="tfa-enroll-code" type="text" inputMode="numeric" autoComplete="one-time-code"
                  placeholder="123 456" value={code}
                  onChange={(e) => setCode(e.target.value.replace(/[^\d]/g, '').slice(0, 6))}
                  disabled={busy} autoFocus style={codeInputStyle}
                />
                {error && <div role="alert" style={errorStyle}>{error}</div>}
                <div style={{ display: 'flex', gap: 9, marginTop: 12, flexWrap: 'wrap' }}>
                  <Btn type="submit" variant="primary" disabled={busy || code.length < 6}>
                    {busy ? 'Verifying…' : 'Verify & turn on'}
                  </Btn>
                  <Btn variant="ghost" onClick={reset} disabled={busy}>Cancel</Btn>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ---- ON: disable flow ---- */}
      {mfaEnrolled && mode === 'idle' && (
        <div style={{ marginTop: 14 }}>
          <Btn variant="danger" onClick={() => { setMode('disabling'); setCode(''); setError(null) }}>
            Disable 2FA
          </Btn>
        </div>
      )}

      {mode === 'disabling' && (
        <form onSubmit={confirmDisable} style={{ marginTop: 16, maxWidth: 320 }}>
          <p style={{ fontSize: 13, color: 'var(--ink-2)', marginBottom: 12, lineHeight: 1.5 }}>
            Enter a current code from your authenticator app to confirm turning off two-factor authentication.
          </p>
          <label htmlFor="tfa-disable-code" style={labelStyle}>Current 6-digit code</label>
          <input
            id="tfa-disable-code" type="text" inputMode="numeric" autoComplete="one-time-code"
            placeholder="123 456" value={code}
            onChange={(e) => setCode(e.target.value.replace(/[^\d]/g, '').slice(0, 6))}
            disabled={busy} autoFocus style={codeInputStyle}
          />
          {error && <div role="alert" style={errorStyle}>{error}</div>}
          <div style={{ display: 'flex', gap: 9, marginTop: 12, flexWrap: 'wrap' }}>
            <Btn type="submit" variant="danger" disabled={busy || code.length < 6}>
              {busy ? 'Turning off…' : 'Confirm & turn off'}
            </Btn>
            <Btn variant="ghost" onClick={reset} disabled={busy}>Cancel</Btn>
          </div>
        </form>
      )}
    </section>
  )
}

const secretBox = {
  fontFamily: 'var(--font-mono)', fontSize: 13, letterSpacing: '.5px',
  background: 'var(--surface-2)', border: '1px solid var(--border)',
  borderRadius: 8, padding: '7px 10px', color: 'var(--ink)',
}
const labelStyle = { display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 6 }
const codeInputStyle = {
  width: '100%', boxSizing: 'border-box', padding: '10px 12px', borderRadius: 10,
  border: '1px solid var(--border-2)', background: 'var(--surface)', color: 'var(--ink)',
  fontFamily: 'var(--font-mono)', fontSize: 16, letterSpacing: '3px',
}
const errorStyle = {
  marginTop: 10, fontSize: 12.5, color: 'var(--danger)', background: 'var(--danger-tint)',
  border: '1px solid color-mix(in srgb, var(--danger) 38%, transparent)',
  borderRadius: 8, padding: '8px 10px',
}

function LockIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  )
}
