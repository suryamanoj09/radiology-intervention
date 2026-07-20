import { useMemo } from 'react'

/**
 * PatientIntake — OPTIONAL, DEMO-SAFE patient identifiers.
 *
 * Privacy contract (do NOT weaken):
 *  - These fields live only in client-side React state (lifted to App) mirrored
 *    into sessionStorage (ephemeral: cleared when the tab closes).
 *  - They are NEVER placed in any /api request body. The server never sees them
 *    and nothing is persisted server-side (no PHI at rest).
 *  - They are rendered in exactly one place: the header of the in-browser PDF
 *    the clinician exports locally.
 *  - Age is captured instead of date-of-birth, and any age >= 90 is collapsed to
 *    "90+" (HIPAA Safe-Harbor style) so an exact advanced age is never recorded.
 *  - Name/phone are soft-warned so a user is nudged away from entering real,
 *    directly-identifying data in a demo.
 */

export function emptyPatient() {
  return { name: '', age: '', phone: '' }
}

// >= 6 consecutive digits inside the name field looks like an MRN / record id.
const MRN_LIKE = /\d{6,}/
// Loose phone shape: 7+ digits once separators are stripped.
const PHONE_DIGITS = /\d/g

export default function PatientIntake({ patient, onChange }) {
  const p = patient || emptyPatient()

  function set(key, value) {
    onChange({ ...p, [key]: value })
  }

  // Age: keep only digits; collapse anything >= 90 to the "90+" bucket.
  function setAge(raw) {
    const digits = (raw || '').replace(/[^\d]/g, '')
    if (digits === '') return set('age', '')
    let n = parseInt(digits, 10)
    if (isNaN(n)) return set('age', '')
    if (n > 120) n = 120
    set('age', n >= 90 ? '90+' : String(n))
  }

  function clear() {
    onChange(emptyPatient())
    try { sessionStorage.removeItem('radassist_patient') } catch { /* ignore */ }
  }

  const warnings = useMemo(() => {
    const w = []
    if (p.name && MRN_LIKE.test(p.name)) {
      w.push('That looks like an ID/MRN. For this demo, use a name or initials only — never a real record number.')
    }
    if (p.phone) {
      const count = (p.phone.match(PHONE_DIGITS) || []).length
      if (count >= 7) {
        w.push('A phone number is a direct identifier. It is optional and discouraged here — leave blank for de-identified/demo use.')
      }
    }
    return w
  }, [p.name, p.phone])

  const hasAny = p.name || p.age || p.phone

  return (
    <div className="card intake-card">
      <div className="report-head">
        <h3>Patient details <span className="muted small" style={{ fontWeight: 400 }}>· optional</span></h3>
        {hasAny && (
          <button type="button" className="btn btn-small" onClick={clear}>Clear</button>
        )}
      </div>

      <div className="intake-notice" role="note">
        Demo / de-identified data only. These fields stay in your browser, are never
        sent to the server, and appear only on the PDF you export locally. Do not
        enter real patient-identifying information.
      </div>

      <div className="field-row">
        <label className="field">
          Name or initials
          <input
            type="text"
            name="demo-subject-freeform"
            value={p.name}
            placeholder="e.g., J.D. (demo)"
            autoComplete="off"
            data-1p-ignore data-lpignore="true"
            onChange={(e) => set('name', e.target.value)}
          />
        </label>
        <label className="field">
          Age
          <input
            type="text"
            inputMode="numeric"
            name="demo-years-freeform"
            value={p.age}
            placeholder="years"
            autoComplete="off"
            data-1p-ignore data-lpignore="true"
            onChange={(e) => setAge(e.target.value)}
          />
        </label>
      </div>

      <label className="field">
        Contact phone (optional, discouraged)
        {/* type=text (NOT tel) + a non-semantic name so the browser never
            recognizes this as a phone field and offers to autofill a REAL saved
            number into an app that promises no PHI. */}
        <input
          type="text"
          inputMode="tel"
          name="demo-contact-freeform"
          value={p.phone}
          placeholder="leave blank for de-identified demo"
          autoComplete="off"
          data-1p-ignore data-lpignore="true"
          onChange={(e) => set('phone', e.target.value)}
        />
      </label>

      {warnings.map((msg, i) => (
        <div key={i} className="intake-warn" role="alert">⚠ {msg}</div>
      ))}

      <p className="muted small">
        Age is used instead of date of birth; 90 and over is recorded as “90+”.
        Cleared automatically when you load a new study or sign out.
      </p>
    </div>
  )
}
