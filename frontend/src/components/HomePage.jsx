import { useState } from 'react'
import Hero3D from './Hero3D.jsx'

// ---------------------------------------------------------------------------
// HomePage — the RadAssist marketing landing page.
//
// Ported from the design (RadAssist.dc.html, Home section) to inline styles that
// reference the CSS design tokens (var(--primary), var(--teal), …) so it tracks
// light/dark automatically. The hero's right column hosts <Hero3D/> — a CSP-safe,
// locally-bundled THREE scan-volume that is purely decorative (aria-hidden).
//
// HONESTY CONTRACT (this app never asserts more than the model does):
//   • No "certified" compliance claims — the "Built for" strip is reframed to
//     "Built around DICOM/PACS · HIPAA-aware architecture · SOC 2 / ISO 13485 on
//     the roadmap" (aspirational, not achieved).
//   • Testimonials are labelled ILLUSTRATIVE — no real clinician is quoted.
//   • Every number comes from the live behaviour card (`behaviorCard` prop). When
//     it is null/unavailable, tiles show "—" and an explicit loading/unavailable
//     note — we NEVER fabricate an accuracy figure.
//
// Props:
//   onLaunch     : () => void  — launches the analyzer (App maps to setPage('app')).
//   onNav        : (route) => void — marketing-shell navigation.
//   behaviorCard : object | null — the model behaviour card (App holds the state).
// ---------------------------------------------------------------------------

const MONO = 'var(--font-mono)'
const HEAD = 'var(--font-head)'
const SECTION_WIDE = { maxWidth: 1240, margin: '0 auto' }

// ---- honesty-preserving formatters (mirror EvidencePage) ------------------
const prettyName = (s) => String(s || '').replace(/_/g, ' ')
const fmt3 = (v) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(3))
const fmt4 = (v) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(4))
function aurocColor(v) {
  if (v == null) return 'var(--faint)'
  if (v >= 0.85) return 'var(--success)'
  if (v >= 0.78) return 'var(--teal-2)'
  if (v >= 0.68) return 'var(--warn)'
  return 'var(--danger)'
}

// ---- static, honest marketing content -------------------------------------
const FEATURES = [
  { icon: '🩻', title: 'Chest X-ray AI', desc: 'A TorchXRayVision DenseNet-121 ensemble scores 18 pathologies and returns a ranking score plus a Grad-CAM overlay — as suggestions a clinician confirms.' },
  { icon: '🧠', title: 'CT / MRI viewer + AI', desc: 'Windowing, cine and 2-up compare, with two opt-in AI channels: anatomy segmentation and clearly-labelled unvalidated research candidate detection.' },
  { icon: '🔎', title: 'Grad-CAM explainability', desc: 'Every top finding carries an attention overlay showing where the model looked — a region of attention, never a drawn lesion boundary.' },
  { icon: '📏', title: 'Measurement suite', desc: 'Length, angle and HU/a.u. ROI statistics computed on the true 16-bit intensity, with undo/redo and a persistent measurements list.' },
  { icon: '📝', title: 'Structured reporting', desc: 'Drafts a clinical report and a patient-friendly summary. The LLM only formats findings the clinician and vision model supplied — it never invents.' },
  { icon: '🎯', title: 'Calibrated confidence', desc: 'Shows a calibrated P≈ when one is available; otherwise a ranking score, explicitly marked "not a probability of disease".' },
  { icon: '🛡️', title: 'Abstain over guess', desc: 'An anatomy / out-of-distribution gate refuses non-chest or synthetic input instead of emitting a confident but meaningless flag.' },
  { icon: '🔁', title: 'Learns from review', desc: 'Confirm / dismiss feedback is captured and turned into operating-point updates — a transparent refit, never black-box retraining.' },
]

const MODALITIES = [
  { icon: '🩻', title: 'Chest X-ray', badge: 'Live AI', badgeBg: 'var(--success-tint)', badgeFg: 'var(--success)', desc: 'A DenseNet-121 ensemble runs a live model today — findings, Grad-CAM attention and a per-view behaviour card.' },
  { icon: '🧠', title: 'CT', badge: 'Viewer + opt-in AI', badgeBg: 'var(--primary-tint)', badgeFg: 'var(--primary)', desc: 'A high-performance viewer with optional, off-by-default anatomy segmentation and unvalidated research candidate detection.' },
  { icon: '🧲', title: 'MRI', badge: 'Viewer', badgeBg: 'var(--surface-3)', badgeFg: 'var(--ink-2)', desc: 'Windowing, cine and prior-study compare. New license-clean models drop into the same rail without a redesign.' },
]

const ROADMAP = ['Mammography', 'Ultrasound', 'Longitudinal tracking', 'DICOM SR export', 'Report templates', 'Multi-model ensembles', 'PACS integration']

const WORKFLOW = [
  { n: '01', icon: '⬆️', title: 'Upload', desc: 'A chest X-ray or a CT/MR series (DICOM, PNG or JPG). Identifiers stay in your browser.' },
  { n: '02', icon: '🛡️', title: 'Gate & mask', desc: 'Burned-in markers are masked and an anatomy / OOD gate rejects non-chest input before scoring.' },
  { n: '03', icon: '🧠', title: 'AI scores', desc: 'The DenseNet-121 ensemble flags possible pathologies and produces a Grad-CAM map for the top finding.' },
  { n: '04', icon: '✅', title: 'Review', desc: 'Flags arrive unchecked by default. You confirm or dismiss each one — nothing is a finding until you say so.' },
  { n: '05', icon: '✍️', title: 'Sign report', desc: 'A structured report and patient summary are drafted; the radiologist corrects and signs every word.' },
  { n: '06', icon: '📤', title: 'Export & learn', desc: 'Export a PDF locally; your confirm/dismiss feedback feeds a transparent operating-point refit.' },
]

const EXPLAIN_POINTS = [
  'A Grad-CAM attention overlay for the top finding — where the model looked, not a lesion boundary.',
  'A calibrated confidence score when available, otherwise a ranking score explicitly marked as a score.',
  'Anatomical context for the region of attention, surfaced alongside the flag.',
  'Linked differential considerations the radiologist reviews — reference material, never a verdict.',
]

const SECURITY = [
  { icon: '🕵️', title: 'De-identification', desc: 'DICOM identifiers are stripped on ingest; patient identifiers you add stay client-side and are never sent to any API.' },
  { icon: '🚧', title: 'Secondary-capture quarantine', desc: 'Screenshot / secondary-capture DICOMs are quarantined rather than scored, so screen-grabs cannot masquerade as studies.' },
  { icon: '📦', title: 'Decode & upload bounds', desc: 'Strict size and dimension limits guard the decode path against decompression-bomb and unauthenticated-DoS attacks.' },
  { icon: '⏱️', title: 'Rate limiting', desc: 'Per-client rate limits protect the analyze surface; the DoS/PHI surface has been explicitly reviewed.' },
  { icon: '🔒', title: 'PHI-safe static serving', desc: 'Static image routes require auth so uploaded pixels cannot leak through an unauthenticated /static path.' },
  { icon: '🧾', title: 'Auditable & self-hostable', desc: 'A security-reviewed surface with a deploy checklist. Run it entirely on your own infrastructure.' },
]

const TESTIMONIALS = [
  { quote: 'The attention overlay and the honest "where it fails" panel are what make me trust a second reader — it shows its work instead of asserting a verdict.', initials: 'AR', name: 'Illustrative radiologist', role: 'Scenario — not a real endorsement' },
  { quote: 'Findings arriving unchecked by default fits how we actually read. The AI drafts, I decide, and nothing signs itself.', initials: 'CT', name: 'Illustrative clinical lead', role: 'Scenario — not a real endorsement' },
  { quote: 'Publishing the calibration error and per-view AUROC — including the weak spots — is the opposite of the usual accuracy hype.', initials: 'IN', name: 'Illustrative informatics lead', role: 'Scenario — not a real endorsement' },
]

const FAQS = [
  {
    q: 'Is RadAssist a medical device?',
    a: 'No. RadAssist is a research and education decision-support prototype. It is not FDA-cleared or CE-marked and is not a medical device. A licensed radiologist reviews, corrects and signs every finding before any clinical use.',
  },
  {
    q: 'Does the AI diagnose?',
    a: 'No. The model suggests and highlights; the clinician decides. The percentage shown is a ranking score at an operating point, not a calibrated probability that a disease is present.',
  },
  {
    q: 'What images can I upload?',
    a: 'Use public or de-identified images only. Any patient identifiers you enter stay in your browser session and are never sent to the API or persisted server-side — they are rendered only into the locally-exported PDF.',
  },
  {
    q: 'How accurate is it, really?',
    a: 'We publish the model’s measured behaviour on public studies — calibration error, per-pathology AUROC and per-view subgroups — including the pathologies where it does badly. It is an engineering sanity check, not a clinical performance guarantee. See the full evidence page.',
  },
  {
    q: 'Which modalities are supported?',
    a: 'Chest X-ray runs a live AI model today. CT and MRI ship as high-performance viewers with optional, off-by-default AI channels. New license-clean models drop into the same workspace without a redesign.',
  },
]

// ---- reusable style fragments ---------------------------------------------
const btnPrimary = {
  padding: '14px 24px', borderRadius: 12, border: 'none', background: 'var(--primary)',
  color: 'var(--on-primary)', fontWeight: 600, fontSize: 15.5, cursor: 'pointer',
  fontFamily: 'inherit', boxShadow: 'var(--shadow)', display: 'inline-flex',
  alignItems: 'center', gap: 9, whiteSpace: 'nowrap',
}
const btnGhost = {
  padding: '14px 22px', borderRadius: 12, border: '1px solid var(--border-2)',
  background: 'var(--surface)', color: 'var(--ink)', fontWeight: 600, fontSize: 15.5,
  cursor: 'pointer', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center',
  gap: 9, whiteSpace: 'nowrap',
}
const eyebrow = (color) => ({
  color, fontWeight: 600, fontSize: 13, letterSpacing: '.08em', textTransform: 'uppercase',
})

const ArrowIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
)
const PlayIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polygon points="6 4 20 12 6 20 6 4" /></svg>
)
const CheckIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
)

export default function HomePage({ onLaunch, onNav, behaviorCard = null }) {
  const [openFaq, setOpenFaq] = useState(0)

  // ---- derive measured metrics from the behaviour card (never fabricated) --
  const bc = behaviorCard
  const available = !!(bc && bc.available !== false && Array.isArray(bc.detection) && bc.detection.length)
  const ece = bc?.calibration?.overall?.ece ?? null
  const eceN = bc?.calibration?.overall?.n ?? null
  const studies = bc?.images_scored ?? null
  const pa = bc?.subgroup?.groups?.PA ?? null
  const ap = bc?.subgroup?.groups?.AP ?? null
  const rows = available
    ? [...bc.detection].sort((a, b) => {
      if (a.auroc == null && b.auroc == null) return 0
      if (a.auroc == null) return 1
      if (b.auroc == null) return -1
      return b.auroc - a.auroc
    })
    : []
  const topRows = rows.slice(0, 6)

  const heroStats = [
    { value: studies != null ? String(studies) : '—', label: 'Public studies scored' },
    { value: fmt4(ece), label: 'Calibration error (ECE)' },
    { value: pa?.micro_auroc != null ? fmt3(pa.micro_auroc) : '—', label: 'Micro-AUROC · PA views' },
    { value: available ? String(rows.length) : '—', label: 'Pathologies evaluated' },
  ]
  const statNote = available
    ? `Metrics from an engineering sanity-check on public data (${bc.model || 'TorchXRayVision DenseNet-121'}${studies != null ? `, ${studies} studies` : ''}${eceN != null ? ` · ${eceN.toLocaleString()} label-instances` : ''}) — not a clinical performance guarantee.`
    : bc == null
      ? 'Loading measured metrics from the model behaviour card…'
      : 'Measured metrics are currently unavailable — we never display an accuracy number we have not measured on labelled data.'

  const goEvidence = () => onNav && onNav('evidence')

  return (
    <div id="home-root">
      {/* ---- scoped styles: hover, focus, responsive stacking, reduced-motion --- */}
      <style>{`
        #home-root .hp-btn { transition: background .18s, border-color .18s, color .18s, transform .18s; }
        #home-root .hp-btn-primary:hover { background: var(--primary-2); transform: translateY(-1px); }
        #home-root .hp-btn-ghost:hover { border-color: var(--primary); color: var(--primary); }
        #home-root .hp-card { transition: transform .18s, box-shadow .18s, border-color .18s; }
        #home-root .hp-card:hover { transform: translateY(-3px); box-shadow: var(--shadow); border-color: var(--primary-tint2); }
        #home-root button:focus-visible, #home-root a:focus-visible { outline: none; box-shadow: var(--ring); }
        @media (max-width: 920px) {
          #home-root .hp-hero-grid { grid-template-columns: 1fr !important; }
          #home-root .hp-explain-grid { grid-template-columns: 1fr !important; }
          #home-root .hp-perf-grid { grid-template-columns: 1fr !important; }
        }
        @media (max-width: 560px) {
          #home-root .hp-h1 { font-size: 40px !important; }
          #home-root .hp-cta-h2 { font-size: 30px !important; }
        }
        @media (prefers-reduced-motion: reduce) {
          #home-root .hp-btn, #home-root .hp-card { transition: none !important; }
          #home-root [data-anim] { animation: none !important; }
        }
      `}</style>

      {/* ===================== HERO ===================== */}
      <section className="hp-hero-grid reveal" style={{ ...SECTION_WIDE, padding: '72px 28px 40px', display: 'grid', gridTemplateColumns: '1.02fr .98fr', gap: 48, alignItems: 'center' }}>
        <div>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 9, padding: '6px 13px', borderRadius: 99, background: 'var(--teal-tint)', border: '1px solid color-mix(in srgb, var(--teal) 34%, transparent)', color: 'var(--teal-2)', fontWeight: 600, fontSize: 12.5, letterSpacing: '.01em', whiteSpace: 'nowrap' }}>
            <span data-anim style={{ width: 7, height: 7, borderRadius: 99, background: 'var(--teal)', animation: 'pulseDot 1.8s infinite' }} />
            Explainable AI · Radiology decision support
          </div>
          <h1 className="hp-h1" style={{ fontSize: 57, fontWeight: 800, margin: '22px 0 0', letterSpacing: '-.035em', fontFamily: HEAD, lineHeight: 1.05 }}>
            AI that reads<br />alongside your<br />
            <span style={{ background: 'linear-gradient(120deg, var(--primary), var(--teal))', WebkitBackgroundClip: 'text', backgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>radiologists.</span>
          </h1>
          <p style={{ fontSize: 18.5, color: 'var(--muted)', margin: '22px 0 0', maxWidth: 520, lineHeight: 1.6 }}>
            RadAssist accelerates image interpretation across X-ray, CT and MRI — drafting structured reports the radiologist reviews, corrects and signs. The AI suggests; the clinician decides.
          </p>
          <div style={{ display: 'flex', gap: 13, marginTop: 32, flexWrap: 'wrap' }}>
            <button className="hp-btn hp-btn-primary" onClick={onLaunch} style={btnPrimary}>
              Start AI analysis <ArrowIcon />
            </button>
            <button className="hp-btn hp-btn-ghost" onClick={() => onNav && onNav('dashboard')} style={btnGhost}>
              <PlayIcon /> Explore the console
            </button>
          </div>
          {/* Built-for strip — HONESTY-REFRAMED (no certification claimed) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 34, flexWrap: 'wrap', color: 'var(--faint)', fontSize: 12.5, fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase' }}>
            <span>Built around</span>
            <span style={{ color: 'var(--muted)' }}>DICOM / PACS</span>
            <span style={{ color: 'var(--border-2)' }}>·</span>
            <span style={{ color: 'var(--muted)' }}>HIPAA-aware architecture</span>
            <span style={{ color: 'var(--border-2)' }}>·</span>
            <span style={{ color: 'var(--faint)' }}>SOC 2 / ISO 13485 on the roadmap</span>
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--faint)', margin: '14px 0 0', lineHeight: 1.5 }}>
            Research &amp; education prototype · not a medical device · not FDA-cleared · use public or de-identified images only.
          </p>
        </div>

        {/* Hero visual — decorative 3D scan-volume + illustrative chips */}
        <div style={{ position: 'relative' }}>
          <div style={{ position: 'relative', borderRadius: 24, overflow: 'hidden', background: 'linear-gradient(160deg, color-mix(in srgb, var(--navy) 92%, #000), #0a1526)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-lg)', height: 520 }}>
            <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(600px 400px at 70% 20%, rgba(34,211,199,.16), transparent 60%), radial-gradient(500px 400px at 20% 90%, rgba(59,130,246,.18), transparent 55%)' }} />
            <Hero3D />
            <div style={{ position: 'absolute', top: 16, left: 16, display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px', borderRadius: 99, background: 'rgba(6,14,26,.6)', backdropFilter: 'blur(6px)', border: '1px solid rgba(120,160,220,.2)', color: '#cfe0f5', fontSize: 12, fontWeight: 600 }}>
              <span data-anim style={{ width: 7, height: 7, borderRadius: 99, background: '#22d3c7', boxShadow: '0 0 10px #22d3c7', animation: 'pulseDot 1.4s infinite' }} />
              Interactive 3D · illustrative
            </div>
            <div style={{ position: 'absolute', top: 16, right: 16, fontSize: 11, color: '#7f9cc4', fontFamily: MONO }}>drag to orbit</div>
            <div style={{ position: 'absolute', left: 16, bottom: 16, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <div data-anim style={{ padding: '10px 13px', borderRadius: 12, background: 'rgba(9,18,33,.72)', backdropFilter: 'blur(8px)', border: '1px solid rgba(120,160,220,.18)', animation: 'floaty 6s ease-in-out infinite' }}>
                <div style={{ fontSize: 10.5, color: '#7f9cc4', fontWeight: 600, letterSpacing: '.04em' }}>PLEURAL EFFUSION</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 2 }}>
                  <span style={{ color: '#e8f1ff', fontSize: 19, fontWeight: 600, fontFamily: MONO }}>0.72</span>
                  <span style={{ fontSize: 10.5, color: '#22d3c7' }}>score</span>
                </div>
              </div>
              <div data-anim style={{ padding: '10px 13px', borderRadius: 12, background: 'rgba(9,18,33,.72)', backdropFilter: 'blur(8px)', border: '1px solid rgba(120,160,220,.18)', animation: 'floaty2 7s ease-in-out infinite' }}>
                <div style={{ fontSize: 10.5, color: '#7f9cc4', fontWeight: 600, letterSpacing: '.04em' }}>GRAD-CAM</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 2 }}>
                  <span style={{ color: '#e8f1ff', fontSize: 19, fontWeight: 600, fontFamily: MONO }}>RLL</span>
                  <span style={{ fontSize: 10.5, color: '#8fb3e6' }}>attention</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===================== STAT BAND ===================== */}
      <section style={{ ...SECTION_WIDE, padding: '20px 28px 8px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 1, background: 'var(--border)', border: '1px solid var(--border)', borderRadius: 18, overflow: 'hidden', boxShadow: 'var(--shadow-sm)' }}>
          {heroStats.map((s) => (
            <div key={s.label} style={{ background: 'var(--surface)', padding: '22px 24px' }}>
              <div style={{ fontSize: 30, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-.02em', fontFamily: MONO }}>{s.value}</div>
              <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4, fontWeight: 500 }}>{s.label}</div>
            </div>
          ))}
        </div>
        <p style={{ textAlign: 'center', color: 'var(--faint)', fontSize: 12, marginTop: 12 }}>{statNote}</p>
      </section>

      {/* ===================== CAPABILITIES ===================== */}
      <section id="platform" style={{ ...SECTION_WIDE, padding: '64px 28px 24px' }}>
        <div style={{ maxWidth: 640 }}>
          <div style={eyebrow('var(--primary)')}>The platform</div>
          <h2 style={{ fontSize: 38, fontWeight: 700, margin: '12px 0 0', fontFamily: HEAD }}>One workspace, from pixels to signed report</h2>
          <p style={{ fontSize: 17, color: 'var(--muted)', margin: '16px 0 0' }}>Every capability is built around a single principle: the model formats and highlights, the radiologist stays in control of every word.</p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 18, marginTop: 36 }}>
          {FEATURES.map((f) => (
            <div key={f.title} className="hp-card" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: 22, boxShadow: 'var(--shadow-sm)' }}>
              <div aria-hidden="true" style={{ width: 44, height: 44, borderRadius: 12, display: 'grid', placeItems: 'center', background: 'var(--primary-tint)', color: 'var(--primary)', fontSize: 22 }}>{f.icon}</div>
              <div style={{ fontFamily: HEAD, fontWeight: 600, fontSize: 16, marginTop: 16 }}>{f.title}</div>
              <div style={{ fontSize: 14, color: 'var(--muted)', marginTop: 7, lineHeight: 1.55 }}>{f.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ===================== MODALITIES ===================== */}
      <section id="modalities" style={{ ...SECTION_WIDE, padding: '56px 28px 24px' }}>
        <div style={{ maxWidth: 560 }}>
          <div style={eyebrow('var(--teal-2)')}>Modalities</div>
          <h2 style={{ fontSize: 38, fontWeight: 700, margin: '12px 0 0', fontFamily: HEAD }}>Plug-in imaging modules</h2>
          <p style={{ fontSize: 17, color: 'var(--muted)', margin: '16px 0 0' }}>Chest X-ray runs a live AI model today. CT and MRI ship as high-performance viewers. New models drop in without a redesign.</p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(270px,1fr))', gap: 18, marginTop: 32 }}>
          {MODALITIES.map((m) => (
            <div key={m.title} className="hp-card" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: 22, boxShadow: 'var(--shadow-sm)', position: 'relative', overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div aria-hidden="true" style={{ width: 46, height: 46, borderRadius: 12, display: 'grid', placeItems: 'center', background: 'var(--surface-3)', color: 'var(--ink)', fontSize: 22 }}>{m.icon}</div>
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.05em', padding: '4px 10px', borderRadius: 99, background: m.badgeBg, color: m.badgeFg }}>{m.badge}</span>
              </div>
              <div style={{ fontFamily: HEAD, fontWeight: 600, fontSize: 18, marginTop: 16 }}>{m.title}</div>
              <div style={{ fontSize: 14, color: 'var(--muted)', marginTop: 6, lineHeight: 1.55 }}>{m.desc}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 20, padding: '18px 22px', border: '1px dashed var(--border-2)', borderRadius: 14, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', background: 'var(--surface-2)' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-2)' }}>On the roadmap</span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {ROADMAP.map((r) => (
              <span key={r} style={{ fontSize: 12.5, padding: '5px 12px', borderRadius: 99, background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--muted)', fontWeight: 500 }}>{r}</span>
            ))}
          </div>
        </div>
      </section>

      {/* ===================== WORKFLOW ===================== */}
      <section style={{ ...SECTION_WIDE, padding: '56px 28px 24px' }}>
        <div style={{ textAlign: 'center', maxWidth: 640, margin: '0 auto' }}>
          <div style={eyebrow('var(--primary)')}>Workflow</div>
          <h2 style={{ fontSize: 38, fontWeight: 700, margin: '12px 0 0', fontFamily: HEAD }}>From upload to signed report in six steps</h2>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '22px 14px', marginTop: 40 }}>
          {WORKFLOW.map((w) => (
            <div key={w.n} style={{ position: 'relative' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div aria-hidden="true" style={{ width: 38, height: 38, borderRadius: 11, flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--primary)', boxShadow: 'var(--shadow-sm)', fontSize: 18 }}>{w.icon}</div>
                <div style={{ flex: 1, height: 2, background: 'linear-gradient(90deg, var(--border-2), transparent)' }} />
              </div>
              <div style={{ fontSize: 11, color: 'var(--faint)', marginTop: 14, fontFamily: MONO }}>STEP {w.n}</div>
              <div style={{ fontFamily: HEAD, fontWeight: 600, fontSize: 15, marginTop: 3 }}>{w.title}</div>
              <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 5, lineHeight: 1.5 }}>{w.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ===================== EXPLAINABILITY ===================== */}
      <section style={{ ...SECTION_WIDE, padding: '56px 28px 24px' }}>
        <div className="hp-explain-grid" style={{ background: 'linear-gradient(150deg, color-mix(in srgb, var(--navy) 94%, #000), #0b1728)', borderRadius: 24, overflow: 'hidden', border: '1px solid var(--border)', boxShadow: 'var(--shadow-lg)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
          <div style={{ padding: '48px 44px' }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '5px 12px', borderRadius: 99, background: 'rgba(34,211,199,.14)', border: '1px solid rgba(34,211,199,.3)', color: '#5eead4', fontWeight: 600, fontSize: 12.5 }}>Explainable by design</div>
            <h2 style={{ color: '#f0f6ff', fontSize: 34, fontWeight: 700, margin: '20px 0 0', fontFamily: HEAD }}>See <em style={{ fontStyle: 'normal', color: '#22d3c7' }}>why</em>, not just what</h2>
            <p style={{ color: '#a9c0e0', fontSize: 16, margin: '16px 0 0', lineHeight: 1.6 }}>Every AI suggestion carries a Grad-CAM attention overlay, a confidence score, anatomical context and linked differential considerations. Nothing is a black box — and the heat map shows where the model looked, not a lesion boundary.</p>
            <div style={{ marginTop: 26, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {EXPLAIN_POINTS.map((e) => (
                <div key={e} style={{ display: 'flex', alignItems: 'flex-start', gap: 11, color: '#cfe0f5', fontSize: 14.5, lineHeight: 1.5 }}>
                  <span style={{ width: 22, height: 22, borderRadius: 7, flex: 'none', display: 'grid', placeItems: 'center', background: 'rgba(34,211,199,.16)', color: '#5eead4', marginTop: 1 }}><CheckIcon /></span>
                  {e}
                </div>
              ))}
            </div>
          </div>
          <div style={{ position: 'relative', background: 'radial-gradient(400px 300px at 60% 40%, rgba(59,130,246,.2), transparent)', borderLeft: '1px solid rgba(120,160,220,.14)', minHeight: 360, display: 'grid', placeItems: 'center', padding: 32 }}>
            <div style={{ position: 'relative', width: 230, height: 290, borderRadius: 14, background: 'linear-gradient(180deg, #1b2942, #0d1728)', border: '1px solid rgba(120,160,220,.22)', overflow: 'hidden', boxShadow: '0 20px 50px -20px #000' }}>
              <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle at 50% 40%, rgba(200,220,255,.14), transparent 55%)' }} />
              <div style={{ position: 'absolute', left: '50%', top: '34%', transform: 'translate(-50%,-50%)', width: 96, height: 70, borderRadius: '50%', background: 'radial-gradient(circle, rgba(255,120,90,.85), rgba(255,180,60,.35) 55%, transparent 72%)', filter: 'blur(2px)' }} />
              <div style={{ position: 'absolute', left: '50%', top: '34%', transform: 'translate(-50%,-50%)', width: 60, height: 44, border: '2px solid rgba(255,220,120,.9)', borderRadius: 8 }} />
              <div style={{ position: 'absolute', left: 6, top: 6, fontSize: 9, color: '#8fb3e6', fontFamily: MONO }}>PA · 224²</div>
              <div data-anim style={{ position: 'absolute', left: 0, right: 0, height: 2, background: 'linear-gradient(90deg, transparent, #22d3c7, transparent)', animation: 'scanY 3.6s ease-in-out infinite', boxShadow: '0 0 12px #22d3c7' }} />
            </div>
            <div style={{ position: 'absolute', right: 26, bottom: 26, padding: '10px 13px', borderRadius: 11, background: 'rgba(9,18,33,.8)', backdropFilter: 'blur(8px)', border: '1px solid rgba(120,160,220,.2)' }}>
              <div style={{ fontSize: 10, color: '#7f9cc4', letterSpacing: '.05em' }}>ATTENTION</div>
              <div style={{ color: '#e8f1ff', fontSize: 16, fontWeight: 600, fontFamily: MONO }}>region-level</div>
            </div>
            <div style={{ position: 'absolute', left: 20, bottom: 20, fontSize: 10, color: '#7f9cc4', fontFamily: MONO }}>illustrative</div>
          </div>
        </div>
      </section>

      {/* ===================== PERFORMANCE / EVIDENCE ===================== */}
      <section id="performance" style={{ ...SECTION_WIDE, padding: '56px 28px 24px' }}>
        <div className="hp-perf-grid" style={{ display: 'grid', gridTemplateColumns: '.9fr 1.1fr', gap: 36, alignItems: 'start' }}>
          <div>
            <div style={eyebrow('var(--teal-2)')}>Measured, not claimed</div>
            <h2 style={{ fontSize: 36, fontWeight: 700, margin: '12px 0 0', fontFamily: HEAD }}>Radical transparency about performance</h2>
            <p style={{ fontSize: 16, color: 'var(--muted)', margin: '16px 0 0', lineHeight: 1.6 }}>
              We publish the model’s real behaviour on public studies — including where it fails. The confidence shown is a ranking score, never a calibrated probability or a diagnosis.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 24 }}>
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, padding: 18, boxShadow: 'var(--shadow-sm)' }}>
                <div style={{ fontSize: 26, fontWeight: 600, color: 'var(--ink)', fontFamily: MONO }}>{fmt4(ece)}</div>
                <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 3, lineHeight: 1.4 }}>Expected calibration error — the % is a score, not a probability</div>
              </div>
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, padding: 18, boxShadow: 'var(--shadow-sm)' }}>
                <div style={{ fontSize: 26, fontWeight: 600, color: 'var(--ink)', fontFamily: MONO }}>
                  {pa?.micro_auroc != null ? fmt3(pa.micro_auroc) : '—'} / {ap?.micro_auroc != null ? fmt3(ap.micro_auroc) : '—'}
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 3, lineHeight: 1.4 }}>Micro-AUROC on PA vs AP views — performance shifts on portable films</div>
              </div>
            </div>
            <button className="hp-btn hp-btn-ghost" onClick={goEvidence} style={{ ...btnGhost, marginTop: 20, padding: '11px 18px', borderRadius: 11, fontSize: 14 }}>
              See full evidence <ArrowIcon />
            </button>
          </div>

          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 18, padding: 8, boxShadow: 'var(--shadow)', overflowX: 'auto' }}>
            <div style={{ minWidth: 460 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.7fr .62fr 1.05fr', gap: 8, padding: '12px 16px 8px', fontSize: 11, fontWeight: 700, letterSpacing: '.05em', color: 'var(--faint)', textTransform: 'uppercase' }}>
                <span>Pathology</span><span style={{ textAlign: 'right' }}>AUROC</span><span>Sensitivity</span>
              </div>
              {available ? topRows.map((d) => {
                const sens = d.sensitivity
                const sensPct = sens == null ? 0 : Math.max(0, Math.min(1, sens)) * 100
                return (
                  <div key={d.pathology} style={{ display: 'grid', gridTemplateColumns: '1.7fr .62fr 1.05fr', gap: 8, alignItems: 'center', padding: '9px 16px', borderTop: '1px solid var(--border)' }}>
                    <span style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: 8 }}>
                      {prettyName(d.pathology)}
                      {d.reliable
                        ? <span title="reliable sample size (≥20 positives)" style={{ width: 6, height: 6, borderRadius: 99, background: 'var(--success)', flex: 'none' }} />
                        : <span title={d.positives === 0 ? 'not measurable — 0 positives in sample' : `indicative only — ${d.positives} positive(s)`} style={{ width: 6, height: 6, borderRadius: 99, background: 'var(--faint)', opacity: .6, flex: 'none' }} />}
                    </span>
                    <span style={{ textAlign: 'right', fontSize: 13.5, fontWeight: 600, color: aurocColor(d.auroc), fontFamily: MONO }}>{fmt3(d.auroc)}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, height: 6, borderRadius: 99, background: 'var(--surface-3)', overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${sensPct}%`, background: sens === 0 ? 'var(--danger)' : 'var(--primary)', borderRadius: 99 }} />
                      </div>
                      <span style={{ fontSize: 12, color: 'var(--muted)', width: 34, fontFamily: MONO, textAlign: 'right' }}>{fmt3(sens)}</span>
                    </div>
                  </div>
                )
              }) : (
                <div style={{ padding: '28px 16px', borderTop: '1px solid var(--border)', textAlign: 'center', color: 'var(--muted)', fontSize: 13.5, lineHeight: 1.6 }}>
                  {bc == null
                    ? 'Loading the model behaviour card…'
                    : 'Per-pathology metrics are unavailable right now. We show real measured numbers here or nothing at all — never an invented figure.'}
                </div>
              )}
              {available && rows.length > topRows.length && (
                <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border)', fontSize: 12, color: 'var(--faint)' }}>
                  Showing the {topRows.length} strongest of {rows.length} evaluated labels — the full table, including weak spots, is on the evidence page.
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ===================== TESTIMONIALS (ILLUSTRATIVE) ===================== */}
      <section style={{ ...SECTION_WIDE, padding: '56px 28px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
          <div style={eyebrow('var(--primary)')}>How teams describe the fit</div>
          <span style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase', color: 'var(--warn)', background: 'var(--warn-tint)', border: '1px solid color-mix(in srgb, var(--warn) 34%, transparent)', padding: '4px 10px', borderRadius: 99 }}>Illustrative — not real endorsements</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 18 }}>
          {TESTIMONIALS.map((t) => (
            <figure key={t.quote} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: 26, boxShadow: 'var(--shadow-sm)', margin: 0, display: 'flex', flexDirection: 'column' }}>
              <div aria-hidden="true" style={{ color: 'var(--teal)', fontSize: 34, fontFamily: HEAD, lineHeight: .6 }}>&ldquo;</div>
              <blockquote style={{ fontSize: 15.5, color: 'var(--ink-2)', lineHeight: 1.6, margin: '6px 0 0', flex: 1 }}>{t.quote}</blockquote>
              <figcaption style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 20 }}>
                <div aria-hidden="true" style={{ width: 40, height: 40, borderRadius: 99, background: 'linear-gradient(135deg, var(--primary), var(--teal))', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 700, fontSize: 14 }}>{t.initials}</div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{t.name}</div>
                  <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>{t.role}</div>
                </div>
              </figcaption>
            </figure>
          ))}
        </div>
        <p style={{ color: 'var(--faint)', fontSize: 12, marginTop: 12 }}>These are illustrative scenarios of intended use. No real clinicians are quoted and no endorsement is implied.</p>
      </section>

      {/* ===================== WHAT IT IS / IS NOT ===================== */}
      <section style={{ ...SECTION_WIDE, padding: '32px 28px 24px' }}>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 18, padding: '28px 30px', boxShadow: 'var(--shadow-sm)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 24 }}>
          <div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 700, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--success)' }}>What it is</div>
            <ul style={{ margin: '12px 0 0', paddingLeft: 18, color: 'var(--muted)', fontSize: 14.5, lineHeight: 1.6 }}>
              <li>A research &amp; education decision-support prototype with measured, transparent behaviour.</li>
              <li>A second reader that highlights regions and drafts reports for a clinician to confirm, correct and sign.</li>
            </ul>
          </div>
          <div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 700, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--danger)' }}>What it is not</div>
            <ul style={{ margin: '12px 0 0', paddingLeft: 18, color: 'var(--muted)', fontSize: 14.5, lineHeight: 1.6 }}>
              <li>Not a diagnostic device. Not FDA-cleared or CE-marked. Outputs may be wrong and must be verified.</li>
              <li>CT/MRI AI is opt-in and off by default; candidate detection is explicitly unvalidated research.</li>
            </ul>
          </div>
        </div>
      </section>

      {/* ===================== SECURITY ===================== */}
      <section id="security" style={{ ...SECTION_WIDE, padding: '56px 28px 24px' }}>
        <div style={{ textAlign: 'center', maxWidth: 660, margin: '0 auto' }}>
          <div style={eyebrow('var(--primary)')}>Enterprise &amp; security</div>
          <h2 style={{ fontSize: 38, fontWeight: 700, margin: '12px 0 0', fontFamily: HEAD }}>Deploys the way your hospital needs</h2>
          <p style={{ fontSize: 15, color: 'var(--muted)', margin: '14px 0 0' }}>Built around DICOM/PACS with a HIPAA-aware architecture. SOC 2 and ISO 13485 are on the roadmap — not yet certified.</p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(290px,1fr))', gap: 18, marginTop: 36 }}>
          {SECURITY.map((s) => (
            <div key={s.title} className="hp-card" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: 22, boxShadow: 'var(--shadow-sm)', display: 'flex', gap: 15 }}>
              <div aria-hidden="true" style={{ width: 40, height: 40, flex: 'none', borderRadius: 11, display: 'grid', placeItems: 'center', background: 'var(--teal-tint)', color: 'var(--teal-2)', fontSize: 19 }}>{s.icon}</div>
              <div>
                <div style={{ fontFamily: HEAD, fontWeight: 600, fontSize: 15.5 }}>{s.title}</div>
                <div style={{ fontSize: 13.5, color: 'var(--muted)', marginTop: 5, lineHeight: 1.5 }}>{s.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ===================== FAQ ===================== */}
      <section style={{ maxWidth: 820, margin: '0 auto', padding: '56px 28px 24px' }}>
        <h2 style={{ fontSize: 34, fontWeight: 700, textAlign: 'center', fontFamily: HEAD }}>Frequently asked</h2>
        <div style={{ marginTop: 28, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {FAQS.map((q, i) => {
            const open = openFaq === i
            return (
              <div key={q.q} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, overflow: 'hidden', boxShadow: 'var(--shadow-sm)' }}>
                <button
                  onClick={() => setOpenFaq(open ? -1 : i)}
                  aria-expanded={open}
                  style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '18px 22px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
                >
                  <span style={{ fontWeight: 600, fontSize: 15.5, color: 'var(--ink)' }}>{q.q}</span>
                  <span aria-hidden="true" style={{ color: 'var(--primary)', fontSize: 20, transform: open ? 'rotate(45deg)' : 'rotate(0deg)', transition: 'transform .2s', flex: 'none' }}>+</span>
                </button>
                {open && (
                  <div style={{ padding: '0 22px 20px', fontSize: 14.5, color: 'var(--muted)', lineHeight: 1.6 }}>{q.a}</div>
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* ===================== CTA BAND ===================== */}
      <section style={{ ...SECTION_WIDE, padding: '40px 28px 72px' }}>
        <div style={{ borderRadius: 24, background: 'linear-gradient(135deg, var(--primary), var(--teal))', padding: '56px 48px', textAlign: 'center', position: 'relative', overflow: 'hidden', boxShadow: 'var(--shadow-lg)' }}>
          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(500px 300px at 80% 0%, rgba(255,255,255,.18), transparent 60%)' }} />
          <h2 className="hp-cta-h2" style={{ color: '#fff', fontSize: 40, fontWeight: 800, position: 'relative', fontFamily: HEAD }}>Bring explainable AI into your reading room</h2>
          <p style={{ color: 'rgba(255,255,255,.9)', fontSize: 17, margin: '16px auto 0', maxWidth: 520, position: 'relative' }}>Start with chest X-ray in minutes. No patient data required to explore the full workflow.</p>
          <div style={{ display: 'flex', gap: 13, justifyContent: 'center', marginTop: 30, position: 'relative', flexWrap: 'wrap' }}>
            <button className="hp-btn" onClick={onLaunch} style={{ padding: '14px 26px', borderRadius: 12, border: 'none', background: '#fff', color: 'var(--primary)', fontWeight: 700, fontSize: 15.5, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>Start AI analysis</button>
            <button className="hp-btn" onClick={() => onNav && onNav('help')} style={{ padding: '14px 24px', borderRadius: 12, border: '1px solid rgba(255,255,255,.5)', background: 'rgba(255,255,255,.12)', color: '#fff', fontWeight: 600, fontSize: 15.5, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>Read the docs</button>
          </div>
        </div>
      </section>
    </div>
  )
}
