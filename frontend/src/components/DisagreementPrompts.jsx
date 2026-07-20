import { useState } from 'react'
import { KEY_DISPLAY, mentionedInText } from '../labelMap.js'

// DISAGREEMENT SURFACING (decision-support, human-in-the-loop).
// Mirror of backend completeness.py rule (a) "discordance": the model flagged a
// finding the clinician has neither confirmed (structured[key]) nor addressed in
// free text. Surfaced here reactively next to the findings form — as the
// clinician edits, not only at report time — so an AI-flagged signal is never
// silently dropped. Framing is model confidence / region of model attention,
// never a diagnosis; the clinician always decides. Each prompt is gently
// dismissible: confirm it, or mark it reviewed & dismissed.
export default function DisagreementPrompts({ suggestions, structured, onConfirm }) {
  const [dismissed, setDismissed] = useState(() => new Set())

  const discordant = (suggestions || []).filter(
    (s) =>
      !structured[s.key] &&
      !mentionedInText(s.key, structured.free_text) &&
      !dismissed.has(s.key),
  )

  if (discordant.length === 0) return null

  function dismiss(key) {
    setDismissed((prev) => {
      const next = new Set(prev)
      next.add(key)
      return next
    })
  }

  return (
    <div className="card disagreement" role="status" aria-label="AI disagreements">
      <h4>Before you sign off</h4>
      <p className="muted small">
        The AI flagged findings you haven&apos;t recorded. Confirm each one, or mark it
        reviewed &amp; dismissed — the decision is yours.
      </p>
      {discordant.map((s) => {
        const name = KEY_DISPLAY[s.key] || s.label
        return (
          <div key={s.key} className="disagree-row">
            <span className="disagree-msg">
              The AI flagged <strong>{name}</strong> ({Math.round(s.probability * 100)}% model
              score) you didn&apos;t record — confirm dismissed?
            </span>
            <span className="disagree-actions">
              <button
                type="button"
                className="btn btn-small"
                onClick={() => onConfirm(s.key)}
              >
                Record it
              </button>
              <button
                type="button"
                className="btn btn-small"
                onClick={() => dismiss(s.key)}
                title="Keep it dismissed — you reviewed and chose not to record it"
              >
                Dismiss
              </button>
            </span>
          </div>
        )
      })}
    </div>
  )
}
