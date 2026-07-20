// Honesty panel: a negative read is NOT an all-clear. Lists conditions outside
// the model's label set so an empty result is never mistaken for "normal".
const NOT_CHECKED = [
  'Free air under the diaphragm (perforation)',
  'Aortic dissection / widened mediastinum specifics',
  'Malpositioned tubes and lines (ETT, central line, NG)',
  'Tension physiology / mediastinal shift',
  'Pneumomediastinum',
  'Subtle or early findings below the model’s operating point',
  'Anything outside the chest, and lateral / non-frontal views',
]

export default function WhatNotChecked({ notAssessed }) {
  return (
    <details className="card not-checked">
      <summary>What this tool did <strong>not</strong> check</summary>
      <p className="muted small">
        The model recognizes a fixed set of common chest findings. A result with nothing
        flagged is <strong>not</strong> an all-clear — these are examples of important things
        it does not look for and that only a clinician reading the full images can assess:
      </p>
      <ul className="nc-list">
        {NOT_CHECKED.map((x) => <li key={x}>{x}</li>)}
      </ul>
      {/* Labels the model CAN emit but are too unreliable to show — an honest scope
          statement ("this tool does not assess for X"), never "no X". */}
      {notAssessed && notAssessed.length > 0 && (
        <>
          <p className="muted small" style={{ marginTop: 10 }}>
            Deliberately <strong>not shown</strong> because this model's label for them is unreliable —
            this tool does <strong>not</strong> assess for these (it is not saying they are absent):
          </p>
          <ul className="nc-list">
            {notAssessed.map((x) => (
              <li key={x.label}>
                <strong>{x.display}</strong> — {x.reason}
                {x.auroc != null ? ` (AUROC ${x.auroc})` : ''}
              </li>
            ))}
          </ul>
        </>
      )}
    </details>
  )
}
