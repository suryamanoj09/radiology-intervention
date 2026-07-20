import { explainForFinding } from '../labelMap.js'
import FeedbackThumbs from './FeedbackThumbs.jsx'

// Estimated size line, ONLY when the measurement workstream has populated the
// (optional) fields on the finding. Always labelled as an estimate from the
// region of model attention — the caliper remains the source of truth.
function measurementLine(f) {
  const parts = []
  if (typeof f.est_max_2d_mm === 'number' && isFinite(f.est_max_2d_mm)) {
    parts.push(`longest axis ≈ ${f.est_max_2d_mm.toFixed(0)} mm`)
  }
  if (typeof f.est_area_mm2 === 'number' && isFinite(f.est_area_mm2)) {
    parts.push(`area ≈ ${Math.round(f.est_area_mm2)} mm²`)
  }
  if (!parts.length) return null
  return `Estimated ${parts.join(', ')} — estimated from the region of model attention; confirm with the caliper.`
}

export default function FindingExplanation({ finding, onFocus, imageSha256 = null }) {
  if (!finding) return null
  const e = explainForFinding(finding)
  const pct = Math.round((finding.probability || 0) * 100)
  const meas = measurementLine(finding)
  return (
    <div
      className="explain-card"
      tabIndex={0}
      onMouseEnter={() => onFocus?.(finding.label)}
      onMouseLeave={() => onFocus?.(null)}
      onFocus={() => onFocus?.(finding.label)}
      onBlur={() => onFocus?.(null)}
    >
      <div className="explain-head">
        <span className="explain-title">{e?.title || finding.label}</span>
        <span className="explain-conf">
          {finding.calibration_state === 'calibrated' || finding.calibrated_probability != null ? (
            <>
              score {pct}%
              {finding.calibrated_probability != null && (
                <span className="explain-cal" title="Calibrated P(disease) — the honest number; the raw score is overconfident.">
                  {' '}· P≈{Math.round(finding.calibrated_probability * 100)}%
                </span>
              )}
            </>
          ) : (
            <span className="explain-uncal" title="No calibration for this label — the score is not a probability.">not calibrated</span>
          )}
        </span>
      </div>
      {e?.what && (
        <p className="explain-what">{e.what.charAt(0).toUpperCase() + e.what.slice(1)}.</p>
      )}
      <details className="why-flagged">
        <summary className="why-flagged-summary">Why was this flagged?</summary>
        <div className="why-flagged-body">
          {finding.calibration_state === 'calibrated' || finding.calibrated_probability != null ? (
            <p className="muted small">
              The model assigned a <strong>{pct}% ranking score</strong> to this pathology and
              highlighted a <strong>region of model attention</strong> for it. The score is not a
              probability of disease{finding.calibrated_probability != null
                ? <> — the calibrated estimate is ≈{Math.round(finding.calibrated_probability * 100)}%</>
                : ''}. This is a signal for review, not a diagnosis.
            </p>
          ) : (
            <p className="muted small">
              This label was flagged, but it is <strong>not calibrated on our validation set</strong>,
              so the raw score is not interpretable as a probability and is not shown. Read the image
              independently — this is a signal for review, not a diagnosis.
            </p>
          )}
          <p className="muted small">
            Raw model label: <code>{finding.label}</code>
            {finding.label === 'Fracture'
              ? ' — CheXpert-derived, generic; the model does not localize a bone or specify a site.'
              : ''}
          </p>
          <p className="muted small">
            The overlay shows where the model looked (Grad-CAM). Grad-CAM highlights regions
            correlated with the prediction; it is coarse, can be misleading, and does not
            explain clinical reasoning.
          </p>
          {finding.reliability_note && (
            <p className="small why-flagged-reliability">
              Reliability: {finding.reliability_note}
            </p>
          )}
          <p className="muted small">
            This marks the region of model attention only — not a measured, outlined, or
            confirmed lesion.
          </p>
        </div>
      </details>
      {meas && <p className="muted small explain-meas">{meas}</p>}
      {e?.differentials?.length > 0 && (
        <div className="explain-diffs">
          <div className="explain-diffs-head">
            Differential considerations — for physician review, not a diagnosis:
          </div>
          <ul>
            {e.differentials.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>
      )}
      <FeedbackThumbs
        target="finding"
        label={finding.label}
        modelNote={`${e?.title || finding.label} — model score ${pct}%`}
        finding={{ ...finding, title: e?.title || finding.label }}
        imageSha256={imageSha256}
        prompt="Was this finding useful?"
      />
    </div>
  )
}
