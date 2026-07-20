import { useEffect, useRef } from 'react'

/**
 * How-to-use / Info modal. Explains what RadAssist is (and is NOT — decision
 * support, not diagnosis), the step-by-step workflow, the self-audit gate,
 * confidence & measured accuracy, measurements/caliper, multi-image, CT/MRI
 * status, and supported image formats. Tone: clinical but clear.
 *
 * Rendered as a full-screen overlay so it works from any tab or auth state.
 * Controlled by the parent: mount when open, call onClose() to dismiss.
 */
export default function InfoPage({ onClose }) {
  const closeRef = useRef(null)

  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    // Focus the close button when the dialog opens (accessible entry point).
    if (closeRef.current) closeRef.current.focus()
    // Lock body scroll behind the modal.
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])

  return (
    <div
      className="info-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="info-title"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="info-modal card">
        <div className="info-head">
          <h2 id="info-title">How to use RadAssist</h2>
          <button ref={closeRef} className="btn btn-small info-close" onClick={onClose} aria-label="Close help">
            Close ✕
          </button>
        </div>

        <p className="muted info-lead">
          RadAssist is an AI <strong>decision-support</strong> assistant for chest radiographs.
          It drafts possible findings, highlights the region the model attended to, and helps a
          licensed clinician write and export a report. It does <strong>not</strong> make a
          diagnosis, and nothing it suggests is confirmed until you confirm it.
        </p>

        {/* ---- What it is / is NOT ---- */}
        <section className="info-sec">
          <h3>What this tool is — and is not</h3>
          <div className="info-grid2">
            <div className="info-box info-box-ok">
              <h4>It is</h4>
              <ul>
                <li>A second-reader that <em>suggests</em> findings on frontal chest X-rays.</li>
                <li>A way to see the model’s <em>region of attention</em> and its <em>confidence</em>.</li>
                <li>A report drafting + PDF export tool with a mandatory clinician sign-off.</li>
              </ul>
            </div>
            <div className="info-box info-box-warn">
              <h4>It is not</h4>
              <ul>
                <li>A diagnosis, a medical device, or FDA-cleared.</li>
                <li>A replacement for reading the full images yourself.</li>
                <li>An all-clear — a result with nothing flagged is not “normal”.</li>
              </ul>
            </div>
          </div>
        </section>

        {/* ---- Step by step ---- */}
        <section className="info-sec">
          <h3>Step by step</h3>
          <ol className="info-steps">
            <li><strong>Upload</strong> a chest X-ray (PNG, JPG, or DICOM). You can also add a
              <em> prior</em> study to compare against.</li>
            <li><strong>Self-audit runs first.</strong> The tool checks the image is a plausible
              chest radiograph before it scores anything (see below).</li>
            <li><strong>Review the AI suggestions.</strong> Each flagged finding is a suggestion,
              <em> unchecked by default</em>, shown with a confidence band and a highlighted
              region of attention in the viewer.</li>
            <li><strong>Confirm, edit, or dismiss</strong> each finding. Only what you check
              becomes part of the report — the AI never auto-confirms.</li>
            <li><strong>Sign off.</strong> Enter your name/role to unlock report generation —
              this records that a clinician reviewed the draft.</li>
            <li><strong>Generate &amp; export.</strong> Produce the clinical report, a
              patient-friendly summary, and reference differentials, then export a PDF that
              includes each finding’s region image.</li>
          </ol>
        </section>

        {/* ---- Self-audit gate ---- */}
        <section className="info-sec">
          <h3>The self-audit gate (why an image may be down-weighted or not scored)</h3>
          <p className="muted">
            Before scoring, RadAssist runs a self-audit that estimates whether the image is in
            the kind of data the model was validated on. Based on that check it will:
          </p>
          <ul className="info-list">
            <li><strong>Read</strong> — image looks like a normal frontal chest X-ray; results shown normally.</li>
            <li><strong>Down-weight</strong> — something is off (unusual exposure, cropping, artefacts);
              results shown with reduced competence and extra caution.</li>
            <li><strong>Abstain</strong> — the image does not appear to be a chest radiograph
              (e.g. a photo, a CT slice, a non-chest X-ray); it is <em>not</em> scored, and you are
              told why. This is the safe behaviour — the model declines rather than guessing.</li>
          </ul>
        </section>

        {/* ---- Confidence & accuracy ---- */}
        <section className="info-sec">
          <h3>Confidence and measured accuracy</h3>
          <p className="muted">
            The percentage on each finding is a <strong>raw ranking score</strong> used only to
            rank and flag (a finding is <em>flagged</em> at or above the operating point, ≥50%) —
            it is <strong>not</strong> a calibrated probability of disease and tends to be
            over-confident. When a per-label calibration is available the viewer shows a separate
            calibrated <em>P≈</em>; otherwise it shows a <em>“not calibrated”</em> chip. Read the
            disposition, not the bare score.
          </p>
          <p className="muted">
            Where available, the viewer also shows the model’s <strong>measured accuracy</strong>
            (NIH ChestX-ray14 AUROC) for that finding, so you can weigh a suggestion against how
            well the model actually performs on it. High confidence on a finding the model is weak
            at still warrants your own read.
          </p>
        </section>

        {/* ---- Measurements / caliper ---- */}
        <section className="info-sec">
          <h3>Measurements and the caliper</h3>
          <p className="muted">
            The viewer reports per-finding size estimates and a manual <strong>caliper</strong>.
            Units depend on the calibration source:
          </p>
          <ul className="info-list">
            <li><strong>DICOM (.dcm)</strong> carries real pixel spacing, so measurements are in
              <strong> millimetres</strong> automatically (anisotropic spacing is respected).</li>
            <li><strong>PNG / JPG</strong> have no physical scale. Measure a reference of known
              length (e.g. a scale marker) to <strong>calibrate</strong>, after which the caliper
              reads in millimetres; without calibration it falls back to pixels.</li>
          </ul>
          <p className="muted small">
            All sizes are estimates from the region of attention and must be verified against the
            images before being used clinically.
          </p>
        </section>

        {/* ---- Multi-image & prior ---- */}
        <section className="info-sec">
          <h3>Multiple images and prior studies</h3>
          <p className="muted">
            You can load a <strong>current</strong> and a <strong>prior</strong> study. When both
            are present, RadAssist reports the <em>change in model confidence</em> per finding
            between them. This indicates how the model’s output shifted — it is <strong>not</strong>
            a confirmation of disease progression, which only a clinician can determine.
          </p>
        </section>

        {/* ---- CT / MRI ---- */}
        <section className="info-sec">
          <h3>CT and MRI status</h3>
          <p className="muted">
            Chest X-ray analysis is the primary AI pipeline. The CT/MRI viewer is a
            model-free image viewer by default, plus <strong>two opt-in, default-off AI channels</strong>:
          </p>
          <ul className="muted">
            <li>
              <strong>Anatomy overlay</strong> — labels/segments organs &amp; tissues and measures
              regions. It labels anatomy only and makes <em>no</em> disease claim.
            </li>
            <li>
              <strong>Candidate findings (RESEARCH, unvalidated)</strong> — surfaces disease
              <em> candidate</em> regions (e.g. lung nodule, calcification, effusion) for a
              radiologist to confirm/dismiss. These are <strong>not validated</strong>, not a
              diagnosis, and not a medical device; they may miss real disease and flag normal
              anatomy. Both channels are off unless you enable them, and each carries its own
              persistent disclaimer.
            </li>
          </ul>
        </section>

        {/* ---- Supported formats ---- */}
        <section className="info-sec">
          <h3>Supported image formats</h3>
          <div className="info-table-wrap">
            <table className="info-table">
              <thead>
                <tr><th>Format</th><th>Extension</th><th>Measurements</th><th>Notes</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td>PNG</td><td>.png</td><td>Pixels (calibrate for mm)</td>
                  <td>Grayscale or RGB. Best exported directly from the modality/PACS.</td>
                </tr>
                <tr>
                  <td>JPEG</td><td>.jpg / .jpeg</td><td>Pixels (calibrate for mm)</td>
                  <td>Avoid heavy compression — artefacts can affect the self-audit.</td>
                </tr>
                <tr>
                  <td>DICOM</td><td>.dcm</td><td><strong>Millimetres</strong> (automatic)</td>
                  <td>Preferred. Carries pixel spacing; identifiers are de-identified on upload.</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="muted small">
            Single frontal (PA/AP) chest radiographs work best. Lateral and non-frontal views are
            outside the model’s validated scope.
          </p>
        </section>

        {/* ---- Safety & privacy ---- */}
        <section className="info-sec">
          <h3>Safety and privacy</h3>
          <ul className="info-list">
            <li>Every output must be reviewed and approved by a licensed clinician before any use.</li>
            <li>Optional patient details stay in your browser for the PDF only — they are never
              sent to the server and no patient data is persisted.</li>
            <li>DICOM files are de-identified on upload; uploaded images are swept on a timer.</li>
            <li>This is a research-grade prototype — not FDA-cleared and not a medical device.</li>
          </ul>
        </section>

        <div className="info-foot">
          <button className="btn primary" onClick={onClose}>Got it</button>
        </div>
      </div>
    </div>
  )
}
