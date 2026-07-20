// Concise, two-tier priority banner. The headline is <= ~10 words (a wall of text
// at the top of a worklist gets ignored, and an ignored banner is worse than none);
// the full per-finding reasons live in an expandable detail. The banner only ever
// fires on a CALIBRATED probability (backend triage.assess gates on it), so an
// overconfident raw score cannot manufacture an alarm.
export default function TriageBanner({ triage, reasons }) {
  if (triage === 'routine') return null
  const urgent = triage === 'urgent'
  const headline = urgent ? 'Urgent review' : 'Elevated review priority'
  // One short lead reason for the chip; the rest expand.
  const lead = (reasons && reasons[0]) || 'calibrated finding above priority threshold'
  return (
    <div
      className={urgent ? 'triage triage-urgent' : 'triage triage-priority'}
      role={urgent ? 'alert' : 'status'}
      aria-live={urgent ? 'assertive' : 'polite'}
    >
      <span className="triage-chip">{urgent ? '⚠' : '•'} {headline} · {lead}</span>
      {reasons && reasons.length > 0 && (
        <details className="triage-detail">
          <summary>details</summary>
          <ul>
            {reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
          <p className="muted small">Calibrated model estimate — confirm on review; not a diagnosis.</p>
        </details>
      )}
    </div>
  )
}
