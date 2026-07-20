// About / project detail page. Explains the mission, how the AI actually works,
// its intended use & measured limits, and the release history.
//
// HONESTY: every number in the "Intended use & limits" panel is sourced live from
// the behavior card (GET /api/behavior-card) when available, and falls back to the
// last measured values only so the layout never shows a blank. Nothing here asserts
// more than the model does: no FDA clearance, no "medical device", no invented
// accuracy figures, no fabricated testimonials or certifications.

// ---- metric helpers: numbers come ONLY from the live behavior card. When the
// card is unavailable we render "—" rather than a baked-in constant that would
// masquerade as a measurement (parity with HomePage/EvidencePage). ------------
function fmt(n, digits) {
  return typeof n === 'number' && !Number.isNaN(n) ? n.toFixed(digits) : '—'
}
function pneumoniaRow(bc) {
  return bc?.detection?.find?.((d) => d.pathology === 'Pneumonia') || null
}

// Development history of the prototype. Each entry describes real, shipped
// capability milestones — no marketing claims, no calendar precision implied.
const RELEASE_NOTES = [
  {
    v: 'v0.4',
    date: 'Current build',
    items: [
      'OHIF-parity CT/MRI viewer: cine, 2-up compare, hotkeys, unified AI rail',
      'Measurement suite — length, angle, and HU/a.u. ROI stats on true 16-bit intensity',
      'Security hardening: unauthenticated-DoS bounds, PHI-safe static serving, rate limiting',
    ],
  },
  {
    v: 'v0.3',
    date: 'Prototype',
    items: [
      'Opt-in CT/MRI anatomy overlay (labels organs/tissue — never disease)',
      'Research disease-CANDIDATE detector, clearly marked unvalidated and disclaimered',
      'Synthetic-image out-of-distribution abstain and reviewer feedback → threshold refit',
    ],
  },
  {
    v: 'v0.2',
    date: 'Prototype',
    items: [
      'On-repo validation harness: measured AUROC, sensitivity, specificity, calibration (ECE)',
      'Marker-masking defence against shortcut learning and an anatomy-plausibility gate',
      'Structured report, patient-friendly summary, prior-study compare, triage queue',
    ],
  },
  {
    v: 'v0.1',
    date: 'Prototype',
    items: [
      'Chest X-ray analysis with a TorchXRayVision DenseNet-121 ensemble',
      'Grad-CAM attention overlays and a non-chest / OOD abstain gate',
      'Human-in-the-loop review: no AI output auto-populates a signed report',
    ],
  },
]

export default function AboutPage({ onLaunch, onNav, behaviorCard = null }) {
  const bc = behaviorCard
  const live = !!(bc && bc.available !== false && Array.isArray(bc.detection) && bc.detection.length)
  const ece = live ? fmt(bc?.calibration?.overall?.ece, 4) : '—'
  const studies = live && bc?.images_scored != null ? bc.images_scored : null
  const paAuroc = live ? fmt(bc?.subgroup?.groups?.PA?.micro_auroc, 3) : '—'
  const apAuroc = live ? fmt(bc?.subgroup?.groups?.AP?.micro_auroc, 3) : '—'
  const pneuRow = live ? pneumoniaRow(bc) : null
  const pneumonia = fmt(pneuRow?.auroc, 3)
  const pneuPos = pneuRow?.positives
  const paImages = live ? (bc?.subgroup?.groups?.PA?.images ?? null) : null
  const eceN = live ? (bc?.calibration?.overall?.n ?? null) : null

  return (
    <div id="about-root">
      {/* ---- Mission hero -------------------------------------------------- */}
      <section style={{ maxWidth: 900, margin: '0 auto', padding: '64px 28px 24px', textAlign: 'center' }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 13px', borderRadius: 99,
          background: 'var(--primary-tint)', color: 'var(--primary)', fontWeight: 600, fontSize: 12.5, whiteSpace: 'nowrap',
        }}>Our mission</div>
        <h1 style={{ fontSize: 46, fontWeight: 800, margin: '20px 0 0', letterSpacing: '-.03em', fontFamily: 'var(--font-head)' }}>
          Make expert radiology<br />faster, safer and explainable
        </h1>
        <p style={{ fontSize: 18, color: 'var(--muted)', margin: '20px auto 0', maxWidth: 640, lineHeight: 1.6 }}>
          RadAssist exists to give every radiologist a tireless second reader — one that shows its reasoning, admits its
          limits, and never overrules the clinician.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 30, flexWrap: 'wrap' }}>
          <button onClick={onLaunch} style={{
            padding: '13px 24px', borderRadius: 12, border: 'none', background: 'var(--primary)', color: 'var(--on-primary,#fff)',
            fontWeight: 600, fontSize: 15, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
          }}>Launch the analyzer →</button>
          <button onClick={() => onNav('privacy')} style={{
            padding: '13px 22px', borderRadius: 12, border: '1px solid var(--border-2)', background: 'var(--surface)',
            color: 'var(--ink)', fontWeight: 600, fontSize: 15, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
          }}>Privacy policy</button>
        </div>
      </section>

      {/* ---- How the AI actually works ------------------------------------ */}
      <section style={{ maxWidth: 1140, margin: '0 auto', padding: '40px 28px 24px' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <h2 style={{ fontSize: 30, fontWeight: 700, fontFamily: 'var(--font-head)' }}>How the AI actually works</h2>
          <p style={{ color: 'var(--muted)', fontSize: 16, marginTop: 10 }}>
            A safety architecture in one sentence: the model formats and highlights, it never invents findings.
          </p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 18 }}>
          {[
            {
              n: '01', t: 'Capture & mask',
              d: 'DICOM/PNG/JPG is windowed and converted. Burned-in markers are masked and an anatomy gate rejects non-chest images before scoring.',
            },
            {
              n: '02', t: 'Vision model + Grad-CAM',
              d: 'A pretrained TorchXRayVision DenseNet-121 ensemble scores 18 pathologies and produces a Grad-CAM attention map for the top finding.',
            },
            {
              n: '03', t: 'LLM formats, never invents',
              d: 'The report generator only formats and translates findings the clinician and vision model supplied — with a deterministic template fallback when no model is configured.',
            },
          ].map((c) => (
            <div key={c.n} style={{
              background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: 24,
              boxShadow: 'var(--shadow-sm)',
            }}>
              <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--primary)', fontWeight: 600, fontSize: 14 }}>{c.n}</div>
              <div style={{ fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: 17, marginTop: 8 }}>{c.t}</div>
              <p style={{ fontSize: 14, color: 'var(--muted)', marginTop: 8, lineHeight: 1.55 }}>{c.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Intended use & limits (measured metrics) --------------------- */}
      <section style={{ maxWidth: 1140, margin: '0 auto', padding: '24px 28px' }}>
        <div className="about-perf-grid" style={{
          background: 'linear-gradient(150deg,color-mix(in srgb,var(--navy) 94%,#000),#0b1728)',
          borderRadius: 22, padding: '40px 38px', boxShadow: 'var(--shadow-lg)',
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: 32, alignItems: 'center',
        }}>
          <div>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 8, padding: '5px 12px', borderRadius: 99,
              background: 'rgba(255,120,120,.14)', border: '1px solid rgba(255,120,120,.3)', color: '#ffb3b3',
              fontWeight: 600, fontSize: 12.5,
            }}>Intended use &amp; limits</div>
            <h2 style={{ color: '#f0f6ff', fontSize: 28, fontWeight: 700, margin: '18px 0 0', fontFamily: 'var(--font-head)' }}>
              Decision support — not a diagnosis
            </h2>
            <p style={{ color: '#a9c0e0', fontSize: 15, margin: '14px 0 0', lineHeight: 1.6 }}>
              All outputs are AI-generated and may be incorrect. They must be reviewed, corrected and approved by a
              licensed radiologist before any clinical use. RadAssist is not FDA-cleared and is not a medical device.
            </p>
            <p style={{ color: '#7f97ba', fontSize: 12.5, margin: '14px 0 0', lineHeight: 1.55 }}>
              {live
                ? `Figures below are sourced live from the on-repo validation harness (${studies != null ? `${studies} public studies` : 'public studies'}${eceN != null ? ` · ${eceN} label-instances` : ''}). The shown score is a ranking score at the operating point, not a calibrated probability of disease.`
                : 'Measured metrics are currently unavailable — we show "—" rather than an accuracy figure we have not measured. The shown score is a ranking score at the operating point, not a calibrated probability of disease.'}
            </p>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {[
              { v: ece, c: '#fff', l: 'Calibration error (ECE)' },
              { v: studies != null ? String(studies) : '—', c: '#fff', l: 'Public studies scored' },
              { v: paAuroc, c: '#fff', l: `Micro-AUROC · PA views${paImages != null ? ` (${paImages} img)` : ''}` },
              { v: pneumonia, c: '#ff9b9b', l: `Pneumonia AUROC — a known weak spot${pneuPos != null ? ` (${pneuPos} positive${pneuPos === 1 ? '' : 's'})` : ''}` },
            ].map((m, i) => (
              <div key={i} style={{
                background: 'rgba(255,255,255,.05)', border: '1px solid rgba(120,160,220,.16)', borderRadius: 14, padding: 16,
              }}>
                <div style={{ fontFamily: 'var(--font-mono)', color: m.c, fontSize: 24, fontWeight: 600 }}>{m.v}</div>
                <div style={{ color: '#9db4d6', fontSize: 12, marginTop: 3 }}>{m.l}</div>
              </div>
            ))}
          </div>
        </div>
        <p style={{ color: 'var(--faint)', fontSize: 12.5, margin: '12px 4px 0', lineHeight: 1.55 }}>
          Performance shifts by view (PA {paAuroc} vs AP {apAuroc}); Grad-CAM localization is weak; some pathologies have
          too few positives to trust. These are engineering sanity checks on a research-grade pretrained model, not clinical
          validation — the analyzer's <b>"⚠ Known limitations"</b> and <b>"🔬 Where it fails"</b> panels go deeper with the
          measured failure cases.
        </p>
      </section>

      {/* ---- The principle that governs everything ------------------------ */}
      <section style={{ maxWidth: 900, margin: '0 auto', padding: '24px 28px' }}>
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 18, padding: '28px 30px',
          boxShadow: 'var(--shadow-sm)',
        }}>
          <h2 style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-head)' }}>The principle that governs everything</h2>
          <blockquote style={{
            margin: '14px 0 6px', paddingLeft: 16, borderLeft: '3px solid var(--primary)', color: 'var(--ink)',
            fontSize: 17, fontStyle: 'italic', lineHeight: 1.5,
          }}>"The display layer must never assert more than the model does."</blockquote>
          <ul style={{ color: 'var(--muted)', fontSize: 14.5, lineHeight: 1.6, margin: '10px 0 0', paddingLeft: 18 }}>
            <li>Every number is either <b>measured</b> (AUROC, sensitivity, specificity, calibration error) or explicitly
              marked <b>"not calibrated / unvalidated"</b>. We never invent accuracy figures.</li>
            <li>The score shown is a <b>ranking score at the operating point</b>, not a calibrated probability of disease;
              a separate calibrated P≈ is shown when available.</li>
            <li><b>Human-in-the-loop, always.</b> No AI output auto-populates a signed report; the clinician confirms every flag.</li>
            <li><b>Abstain over guess.</b> If the input is not the right kind of image, the system refuses rather than
              emit confident nonsense.</li>
          </ul>
        </div>
      </section>

      {/* ---- Under the hood ----------------------------------------------- */}
      <section style={{ maxWidth: 1140, margin: '0 auto', padding: '24px 28px' }}>
        <div style={{ textAlign: 'center', marginBottom: 22 }}>
          <h2 style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-head)' }}>Under the hood</h2>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 14 }}>
          {[
            { t: 'Backend', d: 'FastAPI · TorchXRayVision · pytorch-grad-cam · pydicom · numpy/scipy/scikit-image · OpenCV' },
            { t: 'Frontend', d: 'React + Vite · canvas/SVG overlays · jsPDF export · system/light/dark theming' },
            { t: 'Models', d: 'DenseNet-121 ensemble (Apache-2.0 weights) · classical HU/intensity segmentation & CADe · pluggable license-clean heavy-model seam' },
            { t: 'Safety', d: 'DICOM de-identification · secondary-capture quarantine · decode/upload bounds · rate limiting · audited' },
          ].map((x) => (
            <div key={x.t} style={{
              background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, padding: '18px 20px',
              boxShadow: 'var(--shadow-sm)',
            }}>
              <div style={{ fontWeight: 700, fontSize: 14.5, fontFamily: 'var(--font-head)' }}>{x.t}</div>
              <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 6, lineHeight: 1.55 }}>{x.d}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Release history ---------------------------------------------- */}
      <section style={{ maxWidth: 900, margin: '0 auto', padding: '40px 28px 24px' }}>
        <h2 style={{ fontSize: 28, fontWeight: 700, textAlign: 'center', marginBottom: 26, fontFamily: 'var(--font-head)' }}>
          Release history
        </h2>
        <p style={{ color: 'var(--faint)', fontSize: 12.5, textAlign: 'center', margin: '-14px 0 24px' }}>
          Development milestones of a research prototype — capability, not calendar, is the honest unit here.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {RELEASE_NOTES.map((r) => (
            <div key={r.v} className="about-rel-row" style={{
              background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: '20px 22px',
              boxShadow: 'var(--shadow-sm)', display: 'grid', gridTemplateColumns: '120px 1fr', gap: 20,
            }}>
              <div>
                <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 16, color: 'var(--primary)' }}>{r.v}</div>
                <div style={{ fontSize: 12.5, color: 'var(--faint)', marginTop: 2 }}>{r.date}</div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {r.items.map((it, i) => (
                  <div key={i} style={{ display: 'flex', gap: 9, fontSize: 13.5, color: 'var(--ink-2)' }}>
                    <span style={{ color: 'var(--teal-2)', flex: 'none' }}>▹</span>{it}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Contact ------------------------------------------------------ */}
      <section style={{ maxWidth: 1140, margin: '0 auto', padding: '24px 28px 64px' }}>
        <div style={{
          borderRadius: 22, background: 'var(--surface)', border: '1px solid var(--border)', padding: 40,
          textAlign: 'center', boxShadow: 'var(--shadow-sm)',
        }}>
          <h2 style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-head)' }}>Talk to the team</h2>
          <p style={{ color: 'var(--muted)', fontSize: 15, margin: '10px auto 0', maxWidth: 440 }}>
            Questions about validation, deployment or research collaboration? We publish where the model fails — ask us anything.
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 22, flexWrap: 'wrap' }}>
            <button onClick={() => onNav('help')} style={{
              padding: '12px 22px', borderRadius: 11, border: 'none', background: 'var(--primary)', color: 'var(--on-primary,#fff)',
              fontWeight: 600, fontSize: 14.5, cursor: 'pointer', fontFamily: 'inherit',
            }}>Get help</button>
            <button onClick={onLaunch} style={{
              padding: '12px 20px', borderRadius: 11, border: '1px solid var(--border-2)', background: 'var(--surface)',
              color: 'var(--ink)', fontWeight: 600, fontSize: 14.5, cursor: 'pointer', fontFamily: 'inherit',
            }}>Launch the analyzer</button>
          </div>
        </div>
      </section>
    </div>
  )
}
