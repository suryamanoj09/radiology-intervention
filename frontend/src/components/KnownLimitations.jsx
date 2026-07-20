import { useEffect, useRef } from 'react'

/**
 * "Known limitations" modal. Honest, design-time boundaries of RadAssist — the
 * things a demoer or evaluator must understand before trusting any output.
 * Content mirrors KNOWN-LIMITATIONS.md at the repo root.
 *
 * Reinforces the decision-support framing: the model produces signals for a
 * clinician to review, never a diagnosis. Rendered as a full-screen overlay so
 * it works from any tab or auth state. Reuses the shared `.info-*` modal styles.
 * Controlled by the parent: mount when open, call onClose() to dismiss.
 */
export default function KnownLimitations({ onClose }) {
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
      aria-labelledby="limits-title"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="info-modal card">
        <div className="info-head">
          <h2 id="limits-title">Known limitations</h2>
          <button ref={closeRef} className="btn btn-small info-close" onClick={onClose} aria-label="Close known limitations">
            Close ✕
          </button>
        </div>

        <div className="info-box info-box-warn info-lead">
          <p className="muted" style={{ margin: 0 }}>
            Read this before demoing or evaluating RadAssist. These are honest, design-time
            boundaries — not bugs. Every output is a <strong>signal for a clinician to review</strong>,
            never a diagnosis, and real-world performance is lower than any benchmark number.
          </p>
        </div>

        {/* ---- Vision model ---- */}
        <section className="info-sec">
          <h3>Vision model</h3>
          <ul className="info-list">
            <li><strong>Research-grade, not FDA-cleared.</strong> The chest X-ray model
              (TorchXRayVision DenseNet-121) was trained on public research datasets. Its
              probabilities are signals for review, not diagnoses.</li>
            <li><strong>In-distribution / optimistic metrics.</strong> Published accuracy comes
              from curated benchmarks; performance on your images will be lower.</li>
            <li><strong>The heatmap is model attention, not a lesion boundary.</strong> Grad-CAM
              shows where the model looked when scoring the top finding. It is coarse and can be
              diffuse, off-target, or highlight anatomy (e.g., the heart for cardiomegaly) rather
              than a discrete lesion.</li>
            <li><strong>Frontal-trained; lateral is unreliable.</strong> The model was validated on
              single frontal (PA/AP) chest radiographs. Lateral and non-frontal views are outside
              its scope.</li>
            <li><strong>Size estimates are rough.</strong> The "≈ mm" value is the longest side of a
              box around the attention region, and only meaningful when DICOM pixel spacing is
              present. PNG/JPG uploads have no physical scale, so the caliper reports pixels.</li>
            <li><strong>Probabilities cluster near the threshold.</strong> 0.5 is the operating
              point; several findings hovering at 50–55% on a normal film is expected noise — which
              is why a human confirms every flag.</li>
            <li><strong>AI analysis (chest X-ray only).</strong> The CT/MRI tabs are an image
              viewer plus <em>two opt-in, default-off</em> AI channels: an <strong>anatomy overlay</strong>
              (labels organs/tissue, never disease) and a <strong>research candidate detector</strong>
              (surfaces unvalidated disease candidates for radiologist confirmation). The candidate
              detector is <strong>not validated</strong> — it may miss real disease and flag normal
              anatomy — and is framed as research, not a diagnosis.</li>
          </ul>
        </section>

        {/* ---- Report, comparison & triage ---- */}
        <section className="info-sec">
          <h3>Report, comparison, and triage</h3>
          <ul className="info-list">
            <li><strong>The LLM formats; it does not diagnose.</strong> All clinical content comes
              from the clinician's form entries and the model's flags. If the input is wrong, the
              report is wrong. Without an API key, reports fall back to a plain deterministic template.</li>
            <li><strong>Differentials are static associations</strong> (finding → common causes),
              not patient-specific reasoning. They are labeled "for physician review only".</li>
            <li><strong>Prior-study comparison compares model confidences,</strong> not measured
              anatomy. "Worsened" means the model is more confident, which can be caused by
              positioning, exposure, or image quality — not necessarily disease progression.</li>
            <li><strong>Triage is a rule on model confidence</strong> for a few critical labels. It
              orders a review queue; it is not an alerting system and must not be relied on to catch
              emergencies.</li>
          </ul>
        </section>

        {/* ---- Data & privacy ---- */}
        <section className="info-sec">
          <h3>Data, privacy, and engineering</h3>
          <ul className="info-list">
            <li><strong>Not a HIPAA-grade system — use public / de-identified images only.</strong>
              There ARE now optional authentication, in-memory DICOM de-identification,
              secondary-capture quarantine, a PHI-free audit log, rate limiting, and an adversarial
              security review — but this is still a prototype, not certified clinical infrastructure,
              and burned-in pixel text is not removed. See the privacy policy.</li>
            <li><strong>Patient identifiers stay in your browser.</strong> Anything you type for the PDF
              is kept only in this browser session and is never sent to the server.</li>
            <li><strong>Voice dictation</strong> uses the browser's speech engine; medical
              vocabulary is frequently mis-transcribed — always proofread.</li>
            <li><strong>Prototype infrastructure.</strong> Single-process server, no queue, no
              database; heavy concurrent use will serialize on the CPU model.</li>
          </ul>
        </section>

        <div className="info-foot">
          <button className="btn primary" onClick={onClose}>Got it</button>
        </div>
      </div>
    </div>
  )
}
