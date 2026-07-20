// Privacy policy — describes the ACTUAL data handling. Kept honest and specific; if
// the data flow changes, this must change with it.
export default function PrivacyPolicy({ onNav }) {
  return (
    <div className="page">
      <div className="page-head">
        <h1>Privacy Policy</h1>
        <p className="muted">How RadAssist handles the data you provide. This is a research/education
          prototype, <b>not</b> a HIPAA-covered clinical system — use public or fully de-identified
          images only.</p>
      </div>

      <div className="page-body">
        <section className="card">
          <h3>1. Patient identifiers stay in your browser</h3>
          <p className="muted">Any patient name, age, or phone number you type for the printed report is
            kept only in your browser session (<code>sessionStorage</code>, cleared when the tab closes).
            It is <b>never sent to the server</b> and is rendered only into the PDF you export locally.</p>
        </section>

        <section className="card">
          <h3>2. Images you upload</h3>
          <ul className="muted">
            <li>Uploaded images/DICOM <b>are sent to the server</b> to be analysed or rendered.</li>
            <li>DICOM files are <b>de-identified in memory</b> — direct identifier tags are scrubbed, dates
              and private tags removed, and Study/Series/SOP UIDs regenerated — before any rendering or storage.</li>
            <li><b>Burned-in pixel text is NOT removed.</b> If a name/MRN is baked into the image pixels, it can
              persist in a rendered view. A "burned-in: yes/unknown" warning is shown. Do not upload such images.</li>
            <li>Rendered slices/heatmaps/masks are stored <b>ephemerally</b> (purged on a short TTL, hours) under
              opaque, unguessable filenames, then deleted. This box is not a durable record store or PACS.</li>
          </ul>
        </section>

        <section className="card">
          <h3>3. Report generation &amp; third parties</h3>
          <p className="muted">By default reports use a <b>deterministic on-server template</b> — no external
            service is contacted. If a deployment configures an LLM provider (e.g. Gemini or Groq), the
            structured findings and history text you enter are sent to that provider to format the prose;
            image pixels are not. This is a deploy-time configuration and is off unless a key is set.</p>
        </section>

        <section className="card">
          <h3>4. Reviewer feedback</h3>
          <p className="muted">Confirm/dismiss feedback is stored to improve the model. It is
            <b> PHI-free by construction</b> (a finding label, a score, an image hash — never patient identifiers
            or the image itself) and is used only for operating-point tuning.</p>
        </section>

        <section className="card">
          <h3>5. Diagnostic logs (in your browser)</h3>
          <p className="muted">The in-app log (Settings → Diagnostics) records API calls, timings, and errors
            <b> locally in your browser only</b>. It never captures response bodies (no findings or pixels) and is
            not transmitted anywhere; clearing it or closing the tab removes it.</p>
        </section>

        <section className="card">
          <h3>6. Authentication &amp; cookies</h3>
          <p className="muted">When a deployment enables authentication, a single signed session cookie is used
            for login. The open demo uses no login and no tracking/analytics cookies.</p>
        </section>

        <section className="card">
          <h3>7. Security</h3>
          <p className="muted">The app applies de-identification, secondary-capture quarantine, upload/decode
            bounds, per-IP rate limits, and security headers. It has undergone an adversarial security review.
            It is still a prototype — see the deployment security notes before any real use.</p>
        </section>

        <p className="muted small">
          Questions or issues? This is a prototype without a support desk — report through your deployment owner.
          {' '}<button className="linklike" onClick={() => onNav('about')}>About this project →</button>
        </p>
      </div>
    </div>
  )
}
