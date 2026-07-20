import { useEffect, useState } from 'react'
import { feedbackSummary } from '../api.js'

// Admin view of the feedback loop: per-label confirm/dismiss counts + precision +
// current vs PROPOSED flag threshold. Read-only — applying a proposal is a deliberate
// ops step (validation/refit_from_feedback.py --apply), never a web action, so a
// request can't silently rewrite model behaviour.
export default function FeedbackAdmin({ onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    feedbackSummary().then(setData).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="info-overlay" role="dialog" aria-modal="true" aria-label="Model tuning" onClick={onClose}>
      <div className="info-modal card fb-admin" onClick={(e) => e.stopPropagation()}>
        <div className="info-head">
          <h2>Feedback &amp; model tuning</h2>
          <button className="btn btn-small info-close" onClick={onClose} aria-label="Close model tuning">✕</button>
        </div>

        <p className="muted small">
          Reviewer <b>Confirm/Dismiss</b> feedback is the training signal. This turns it into
          per-label flag-threshold proposals (over-flagged → raise; reliably-confirmed → lower).
          Applying a proposal is a deliberate ops step
          (<code>python -m validation.refit_from_feedback --apply</code>), never a web action.
        </p>

        {error && <div className="error-bar" role="alert">{error}</div>}
        {!data && !error && <p className="muted">Loading…</p>}

        {data && (
          <>
            <p className="muted small">
              {data.n_events} feedback event(s) recorded · {data.n_proposals} threshold change(s) proposed
              {data.n_proposals === 0 ? ' (need ≥8 events on a label before it moves).' : '.'}
            </p>
            <div className="table-scroll">
              <table className="fb-table">
                <thead>
                  <tr><th>Finding</th><th>✓ Confirm</th><th>✗ Dismiss</th><th>Precision</th>
                    <th>Threshold</th><th>Proposed</th><th>Why</th></tr>
                </thead>
                <tbody>
                  {data.labels.map((r) => (
                    <tr key={r.label} className={r.proposed_threshold != null ? 'fb-changed' : ''}>
                      <td>{r.label}</td>
                      <td>{r.confirmed}</td>
                      <td>{r.dismissed}</td>
                      <td>{r.precision != null ? `${Math.round(r.precision * 100)}%` : '—'}</td>
                      <td>{r.current_threshold}</td>
                      <td>{r.proposed_threshold != null
                        ? <b>{r.proposed_threshold}</b> : <span className="muted">—</span>}</td>
                      <td className="muted small">{r.reason || ''}</td>
                    </tr>
                  ))}
                  {!data.labels.length && (
                    <tr><td colSpan="7" className="muted">No feedback recorded yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
