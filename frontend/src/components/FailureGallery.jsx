import { useEffect, useRef } from 'react'

/**
 * Failure gallery — a first-class, in-app catalogue of cases where THIS system is
 * wrong, with the measured evidence. A tool that shows its own failures earns more
 * trust than any headline accuracy number. Every entry here is something we
 * actually measured with the repo's own tools (marker_ablation.py,
 * pointing_game.py, cam_divergence.py, perturbation_stability.py).
 *
 * Full-screen modal; reuses the shared `.info-*` styles. Controlled by the parent.
 */
const CASES = [
  {
    tag: 'Shortcut learning',
    title: 'The model read the "PORTABLE" marker, not the lungs',
    evidence: 'On study 4e2a03879b53 the Effusion attention centroid sat at x=91%, ' +
      'y=13% — 94% of the hottest pixels were inside the burned-in corner text. The ' +
      'marker-ablation tool showed P(Effusion) barely moved when the marker was removed ' +
      '(Δ≈+0.003): the shortcut lived in the attention, not the score.',
    fix: 'Burned-in markers are now inpainted before the model sees the image; the ' +
      'attention centroid moved off the corner (0% in-marker), and the anatomy gate ' +
      'suppresses the marker-driven Effusion/Edema flags.',
  },
  {
    tag: 'Unproven localization',
    title: 'The heatmap does not beat "guess the centre of the chest"',
    evidence: 'With the default 224 model (7×7 grid), pointing-game hit-rate (CAM peak ' +
      'inside the expert box) was ≈28% vs a ≈31% centre-of-chest baseline — BELOW ' +
      'baseline. The 7×7 grid is the ceiling: one cell ≈ one lung zone.',
    fix: 'The 16×16 res512 localizer (opt-in) flips it ABOVE baseline: ≈50% hit vs 41% ' +
      'baseline (+9.4% lift; Effusion +25%, Infiltration +50%) on its measured subset. ' +
      'The overlay is still framed as "region of model attention", never a lesion ' +
      'boundary, and the behaviour card reports the number instead of hiding it.',
  },
  {
    tag: 'Coarse resolution',
    title: 'A crisp contour at 7×7 would be a lie',
    evidence: 'The DenseNet Grad-CAM is a 7×7 grid (~one cell per lung zone) upsampled ' +
      'to ~1000px. A sharp outline implies a boundary the model can not support.',
    fix: 'No crisp contour is drawn below a 16×16 grid — only a soft gradient — and the ' +
      'caption says so. Findings whose attention is spread over >40% of the frame are ' +
      'labelled "diffuse / non-localizing" and get no region at all.',
  },
  {
    tag: 'Silent-blank maps',
    title: 'Some flagged findings produce an empty attention map',
    evidence: 'On several films Pneumothorax and Mass produced an all-zero CAM — an ' +
      'overlay that looked blank with no explanation.',
    fix: 'Every finding now carries an explicit state (localized / diffuse / suppressed / ' +
      'none / not-computed / error) and a caption, so a blank is never ambiguous.',
  },
  {
    tag: 'Miscalibration',
    title: 'The confidence number is overconfident — it is not a probability of disease',
    evidence: 'Measured Expected Calibration Error ≈ 0.24 (0 = perfect) over 4,200 ' +
      'label-instances. The reliability diagram shows the busy 0.50–0.60 confidence bin ' +
      '(n=1,480) has an observed positive rate of only ~8%. So "52% confidence" does NOT ' +
      'mean a 52% chance of disease — the score is a ranking at the operating point, and ' +
      'this is exactly why many labels flag near 0.50 on hard portable films.',
    fix: 'The behaviour card reports ECE + the reliability table (surfaced, not hidden); ' +
      'each flag carries an explicit disposition ("borderline — below a confident ' +
      'reporting threshold" vs "recommend correlation" vs "urgent") rather than leaning ' +
      'on the raw number; a calibrated-probability mapping (isotonic) is the measured ' +
      'next step.',
  },
  {
    tag: 'Safety gate can harm',
    title: 'The anatomy gate deletes ~1 in 9 true findings it should keep',
    evidence: 'The anatomy gate suppresses a flag whose attention is off the expected ' +
      'anatomy — but if PSPNet mis-segments, it deletes a REAL finding. Measured on NIH ' +
      'ground-truth boxes: it suppressed 3 of 26 score-flagged GT-positive findings, an ' +
      '11.5% false-negative rate (worst on Atelectasis and Mass). An unmeasured safety ' +
      'gate is an unvalidated one.',
    fix: 'The FN rate is now measured into the behaviour card (anatomy_gate.fn_rate); ' +
      'ANATOMY_GATE_MODE=warn_only keeps the flag with a caution instead of deleting it; ' +
      'and a suppressed finding is always shown in the map-status list with its reason.',
  },
  {
    tag: 'Instability',
    title: 'A finding that flips under a 3° rotation is noise',
    evidence: 'The perturbation-stability tool re-scores the same film under horizontal ' +
      'flip, ±3° rotation, and a small crop and reports the flag-decision "flip rate". A ' +
      'finding that appears at 0.52 and vanishes at 0.48 under a tiny rotation is not ' +
      'localizing disease.',
    fix: 'The flip rate is a reported robustness metric; unstable, near-threshold flags ' +
      'are exactly the ones marked "borderline".',
  },
]

export default function FailureGallery({ onClose }) {
  const closeRef = useRef(null)
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    if (closeRef.current) closeRef.current.focus()
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [onClose])

  return (
    <div className="info-overlay" role="dialog" aria-modal="true" aria-labelledby="fg-title"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="info-modal card">
        <div className="info-head">
          <h2 id="fg-title">Where this system fails</h2>
          <button ref={closeRef} className="btn btn-small info-close" onClick={onClose} aria-label="Close failure gallery">
            Close ✕
          </button>
        </div>
        <div className="info-box info-box-warn info-lead">
          <p className="muted" style={{ margin: 0 }}>
            These are real, <strong>measured</strong> failure modes of this system — found with the
            repo's own tools. We show them on purpose: a model you can trust is one whose
            failures you can see. The specific figures below are from a point-in-time validation
            run; the live evidence page always reflects the current behaviour card.
          </p>
        </div>
        {CASES.map((c) => (
          <section className="info-sec fg-case" key={c.title}>
            <span className="fg-tag">{c.tag}</span>
            <h3>{c.title}</h3>
            <p className="muted"><strong>What we measured:</strong> {c.evidence}</p>
            <p className="muted"><strong>What we do about it:</strong> {c.fix}</p>
          </section>
        ))}
        <div className="info-foot">
          <button className="btn primary" onClick={onClose}>Got it</button>
        </div>
      </div>
    </div>
  )
}
