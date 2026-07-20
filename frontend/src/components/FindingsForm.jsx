import { useEffect, useRef, useState } from 'react'
import { KEY_DISPLAY } from '../labelMap.js'

const LOCATIONS = ['RUL', 'RML', 'RLL', 'LUL', 'LLL']
const SIDES = ['right', 'left', 'bilateral']

const CHECKS = [
  ['nodule_present', 'Pulmonary nodule / mass'],
  ['consolidation', 'Consolidation / opacity'],
  ['pleural_effusion', 'Pleural effusion'],
  ['pneumothorax', 'Pneumothorax'],
  ['cardiomegaly', 'Enlarged cardiac silhouette'],
  ['rib_fracture', 'Rib fracture (clinician-entered)'],
]

export default function FindingsForm({ structured, onChange, history, onHistoryChange, suggestions }) {
  const [listening, setListening] = useState(false)
  const [voiceSupported] = useState(
    () => 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window,
  )
  // Settings pref: 'Voice dictation'. When off, the mic is present but disabled so
  // the control is honest (it's not silently inert — the title says where to enable
  // it). Defaults false to match SettingsPage. Re-syncs on cross-tab storage change;
  // same-tab Settings changes are picked up on remount when the user returns here.
  const [dictationEnabled, setDictationEnabled] = useState(() => {
    try {
      const v = localStorage.getItem('radassist_pref_dictation')
      return v === '1' || v === 'true'
    } catch {
      return false
    }
  })
  const recRef = useRef(null)

  useEffect(() => () => recRef.current?.stop(), [])

  useEffect(() => {
    const sync = () => {
      try {
        const v = localStorage.getItem('radassist_pref_dictation')
        setDictationEnabled(v === '1' || v === 'true')
      } catch { /* ignore */ }
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  // If dictation is turned off mid-session while listening, stop cleanly.
  useEffect(() => {
    if (!dictationEnabled && listening) {
      recRef.current?.stop()
      setListening(false)
    }
  }, [dictationEnabled, listening])

  function set(key, value) {
    onChange((prev) => ({ ...prev, [key]: value }))
  }

  function acceptSuggestion(key) {
    set(key, true)
  }

  function toggleVoice() {
    if (!dictationEnabled) return
    if (listening) {
      recRef.current?.stop()
      setListening(false)
      return
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    const rec = new SR()
    rec.continuous = true
    rec.interimResults = false
    rec.lang = 'en-US'
    rec.onresult = (e) => {
      let text = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) text += e.results[i][0].transcript + ' '
      }
      if (text) onChange((prev) => ({ ...prev, free_text: (prev.free_text + ' ' + text).trim() }))
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recRef.current = rec
    rec.start()
    setListening(true)
  }

  const pending = suggestions.filter((s) => !structured[s.key])

  return (
    <div className="card">
      <h3>Findings — review &amp; confirm</h3>
      <p className="muted small">
        Nothing here is confirmed until you check it. AI suggestions are unchecked by default —
        accept, edit, or dismiss each one.
      </p>

      {pending.length > 0 && (
        <div className="ai-suggestions" aria-label="AI suggestions">
          <div className="ai-suggestions-head">AI suggested (unconfirmed):</div>
          <div className="chips">
            {pending.map((s) => (
              <button key={s.key} className="chip" onClick={() => acceptSuggestion(s.key)}>
                + {KEY_DISPLAY[s.key] || s.label} · {Math.round(s.probability * 100)}%
              </button>
            ))}
          </div>
        </div>
      )}

      <label className="field">
        Clinical history / indication
        <input
          type="text"
          value={history}
          placeholder="e.g., 62M, smoker, chronic cough"
          onChange={(e) => onHistoryChange(e.target.value)}
        />
      </label>

      <div className="check-grid">
        {CHECKS.map(([key, label]) => (
          <label key={key} className="check">
            <input
              type="checkbox"
              checked={!!structured[key]}
              onChange={(e) => set(key, e.target.checked)}
            />
            {label}
          </label>
        ))}
      </div>

      {structured.nodule_present && (
        <div className="field-row">
          <label className="field">
            Nodule size (mm) — clinician-measured
            <input
              type="number" min="0" step="0.5"
              value={structured.nodule_size_mm ?? ''}
              onChange={(e) => set('nodule_size_mm', e.target.value === '' ? null : parseFloat(e.target.value))}
            />
          </label>
          <label className="field">
            Location
            <select value={structured.nodule_location ?? ''} onChange={(e) => set('nodule_location', e.target.value || null)}>
              <option value="">—</option>
              {LOCATIONS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </label>
        </div>
      )}

      {structured.pleural_effusion && (
        <label className="field">
          Effusion side
          <select value={structured.effusion_side ?? ''} onChange={(e) => set('effusion_side', e.target.value || null)}>
            <option value="">— select side —</option>
            {SIDES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      )}

      {structured.pneumothorax && (
        <label className="field">
          Pneumothorax side
          <select value={structured.pneumothorax_side ?? ''} onChange={(e) => set('pneumothorax_side', e.target.value || null)}>
            <option value="">— select side —</option>
            <option value="right">right</option>
            <option value="left">left</option>
          </select>
        </label>
      )}

      <label className="field">
        <span>
          Additional findings (free text)
          {voiceSupported && (
            <button
              type="button"
              className={listening ? 'btn btn-small mic active' : 'btn btn-small mic'}
              onClick={toggleVoice}
              disabled={!dictationEnabled}
              aria-pressed={listening}
              title={dictationEnabled
                ? 'Dictate findings'
                : 'Voice dictation is turned off — enable it in Settings → Preferences'}
            >
              {listening ? '🎙 Listening… (click to stop)' : '🎙 Dictate'}
            </button>
          )}
        </span>
        <textarea
          rows={3}
          value={structured.free_text}
          placeholder="Anything the checkboxes don't cover…"
          onChange={(e) => set('free_text', e.target.value)}
        />
      </label>

      <label className="check attest">
        <input
          type="checkbox"
          checked={!!structured.reviewed_no_acute}
          onChange={(e) => set('reviewed_no_acute', e.target.checked)}
        />
        I reviewed this study — no acute abnormality (attest when nothing is marked)
      </label>
    </div>
  )
}
