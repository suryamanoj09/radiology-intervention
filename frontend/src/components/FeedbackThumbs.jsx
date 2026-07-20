import { useState } from 'react'
import { submitFeedback } from '../api.js'

// Reviewer feedback. The most VALUABLE signal is Confirm / Dismiss on a finding —
// a dismissed AI finding is a labeled negative (real training data), not a vibe.
// Every event is SELF-CONTAINED and PHI-free: raw label, scores, states, and the
// image content-hash (public-image identity) — no patient data, no analysis id.
export default function FeedbackThumbs({
  target,
  label = null,
  modelNote = null,
  prompt = 'Was this useful?',
  finding = null,      // when present, enables Confirm/Dismiss with full context
  imageSha256 = null,
}) {
  const [state, setState] = useState('idle') // idle | sending | done | error
  const [chosen, setChosen] = useState(null)

  function context() {
    if (!finding) return {}
    return {
      image_sha256: imageSha256,
      image_source: 'user_upload',
      raw_label: finding.label,
      display_label: finding.title || finding.label,
      raw_score: finding.probability ?? null,
      calibrated_p: finding.calibrated_probability ?? null,
      calibration_state: finding.calibration_state ?? null,
      heatmap_state: finding.heatmap_state ?? null,
    }
  }

  async function send(event, extra) {
    if (state === 'sending' || state === 'done') return
    setChosen(event)
    setState('sending')
    try {
      await submitFeedback({
        event,
        ...context(),
        // back-compat fields for the report-level thumbs
        target, rating: extra?.rating ?? null, label,
        model_note: modelNote, action: extra?.action ?? event,
        timestamp: new Date().toISOString(),
      })
      setState('done')
    } catch {
      setState('error')
    }
  }

  if (state === 'done') {
    const word = { confirmed: 'confirmed ✓', dismissed: 'dismissed ✕',
      thumb_up: '👍', thumb_down: '👎' }[chosen] || 'recorded'
    return (
      <div className="feedback-thumbs done" aria-live="polite">
        <span className="feedback-recorded">Feedback recorded ({word}) — thank you.</span>
      </div>
    )
  }

  return (
    <div className="feedback-thumbs" role="group" aria-label={prompt}>
      {finding ? (
        <>
          <span className="feedback-prompt muted small">Your read:</span>
          <button type="button" className="btn btn-small" disabled={state === 'sending'}
            title="A real finding — confirm (labeled positive)"
            onClick={() => send('confirmed', { rating: 'up', action: 'agree' })}>✓ Confirm</button>
          <button type="button" className="btn btn-small" disabled={state === 'sending'}
            title="Not a real finding — dismiss (labeled negative; the valuable signal)"
            onClick={() => send('dismissed', { rating: 'down', action: 'disagree' })}>✕ Dismiss</button>
        </>
      ) : (
        <>
          <span className="feedback-prompt muted small">{prompt}</span>
          <button type="button" className="btn-thumb" aria-label="Useful" title="Useful"
            disabled={state === 'sending'} onClick={() => send('thumb_up', { rating: 'up' })}>👍</button>
          <button type="button" className="btn-thumb" aria-label="Not useful" title="Not useful"
            disabled={state === 'sending'} onClick={() => send('thumb_down', { rating: 'down' })}>👎</button>
        </>
      )}
      {state === 'error' && (
        <span className="feedback-err muted small" role="alert">Could not record — please try again.</span>
      )}
    </div>
  )
}
