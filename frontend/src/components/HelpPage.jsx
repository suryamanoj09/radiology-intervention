import { useMemo, useRef, useState } from 'react'

/**
 * HelpPage — the public "How can we help?" docs hub (marketing-shell route 'help').
 *
 * Matches the design's help center (RadAssist.dc.html lines 453-526): centered
 * hero + search, a topic-card grid, a keyboard-shortcuts panel, and a support
 * card. But it is a *genuinely useful* hub, not a brochure — it folds in the
 * app's existing honesty/education surfaces rather than re-asserting claims:
 *
 *   • "Full user guide"   → onOpenInfo()        (InfoPage modal)
 *   • "Known limitations" → onOpenLimitations() (KnownLimitations modal)
 *   • "Where it fails"    → onOpenFailures()     (FailureGallery modal)
 *
 * Topics that don't have a modal are answered inline (Getting started, How AI
 * analysis works, Reading confidence/calibration, Privacy & data, Contact) with
 * honest, measured copy. The confidence section sources its numbers LIVE from
 * the behavior card when provided, falling back to the true measured values.
 *
 * HONESTY: no compliance claims, no invented metrics, no fake testimonials. All
 * styling is inline against WF2's CSS vars (theme-aware light/dark). Callbacks
 * are optional — a topic whose callback is missing degrades to its inline copy.
 *
 * Props:
 *   onNav            : (route) => void   — shell router ('dashboard' | 'privacy' | ...)
 *   onOpenInfo       : () => void        — opens the InfoPage modal (full user guide)
 *   onOpenLimitations: () => void        — opens the KnownLimitations modal
 *   onOpenFailures   : () => void        — opens the FailureGallery modal
 *   behaviorCard     : object | null     — GET /api/behavior-card payload (App holds it)
 */

// ---- Icons (inline SVG, currentColor) --------------------------------------
const ic = (d) => (p) => (
  <svg width={p.size || 22} height={p.size || 22} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
    aria-hidden="true">{d}</svg>
)
const IconRocket = ic(<><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91 0z" /><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" /><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" /><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" /></>)
const IconBrain = ic(<><path d="M12 5a3 3 0 1 0-5.997.142 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" /><path d="M12 5a3 3 0 1 1 5.997.142 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" /><path d="M12 5v13" /></>)
const IconGauge = ic(<><path d="M12 14 8.5 9.5" /><circle cx="12" cy="14" r="1.2" fill="currentColor" /><path d="M4 18a8 8 0 1 1 16 0" /></>)
const IconWarn = ic(<><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><path d="M12 9v4" /><path d="M12 17h.01" /></>)
const IconFlask = ic(<><path d="M9 3h6" /><path d="M10 3v6.5L4.6 18a2 2 0 0 0 1.7 3h11.4a2 2 0 0 0 1.7-3L14 9.5V3" /><path d="M6.5 14h11" /></>)
const IconLock = ic(<><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></>)
const IconChat = ic(<><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></>)
const IconSearch = ic(<><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></>)

// ---- Small style helpers ---------------------------------------------------
const card = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 16, boxShadow: 'var(--shadow-sm)',
}
const H = { fontFamily: 'var(--font-head)', fontWeight: 600 }
const kbd = {
  fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--muted)',
  border: '1px solid var(--border)', borderRadius: 6, padding: '2px 8px',
  whiteSpace: 'nowrap',
}

// A topic card with hover lift (inline styles can't do :hover, so track it).
function TopicCard({ icon: Icon, title, desc, cue, onClick }) {
  const [hover, setHover] = useState(false)
  const [focus, setFocus] = useState(false)
  const lift = hover || focus
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setFocus(true)}
      onBlur={() => setFocus(false)}
      className="hp-topic"
      style={{
        ...card, textAlign: 'left', padding: 22, cursor: 'pointer',
        display: 'flex', gap: 15, alignItems: 'flex-start', font: 'inherit',
        color: 'var(--ink)', width: '100%',
        borderColor: lift ? 'var(--primary-tint2)' : 'var(--border)',
        boxShadow: lift ? 'var(--shadow)' : 'var(--shadow-sm)',
        transform: lift ? 'translateY(-3px)' : 'none',
        transition: 'transform .16s, box-shadow .16s, border-color .16s',
      }}
    >
      <span style={{
        width: 44, height: 44, flex: 'none', borderRadius: 12, display: 'grid',
        placeItems: 'center', background: 'var(--primary-tint)', color: 'var(--primary)',
      }}><Icon /></span>
      <span style={{ minWidth: 0 }}>
        <span style={{ ...H, fontSize: 16, display: 'block' }}>{title}</span>
        <span style={{ fontSize: 13.5, color: 'var(--muted)', marginTop: 5, lineHeight: 1.5, display: 'block' }}>{desc}</span>
        <span style={{ fontSize: 12, color: 'var(--primary)', fontWeight: 600, marginTop: 10, display: 'block' }}>{cue} →</span>
      </span>
    </button>
  )
}

// An inline answer section (anchor target for topic cards without a modal).
function Section({ id, eyebrow, title, children, tone }) {
  const border = tone === 'warn' ? 'var(--warn)' : tone === 'ok' ? 'var(--success)' : 'var(--border)'
  return (
    <section id={id} style={{ ...card, padding: 24, borderTopWidth: 3, borderTopColor: border, scrollMarginTop: 90 }}>
      {eyebrow && <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.08em', color: 'var(--faint)', textTransform: 'uppercase', marginBottom: 8 }}>{eyebrow}</div>}
      <h2 style={{ ...H, fontSize: 19, margin: '0 0 12px' }}>{title}</h2>
      {children}
    </section>
  )
}

const p = { color: 'var(--ink-2)', fontSize: 14.5, lineHeight: 1.6, margin: '0 0 10px' }
const muted = { color: 'var(--muted)', fontSize: 13.5, lineHeight: 1.6 }

export default function HelpPage({ onNav, onOpenInfo, onOpenLimitations, onOpenFailures, behaviorCard }) {
  const [q, setQ] = useState('')
  const searchRef = useRef(null)

  // Metrics are read live from the behavior card — never hardcoded. When the card
  // is unavailable we render "—"/"unavailable" (like HomePage/EvidencePage) rather
  // than baked-in constants that would masquerade as measured.
  const bc = behaviorCard || null
  const live = !!(bc && bc.available === true && Array.isArray(bc.detection) && bc.detection.length)
  const ece = live ? (bc?.calibration?.overall?.ece ?? null) : null
  const pa = live ? (bc?.subgroup?.groups?.PA?.micro_auroc ?? null) : null
  const ap = live ? (bc?.subgroup?.groups?.AP?.micro_auroc ?? null) : null

  // Best/worst measurable pathology by AUROC + weak-spot rows — all data-driven.
  const det = live ? bc.detection : []
  const measurable = det.filter((x) => x.auroc != null).sort((a, b) => b.auroc - a.auroc)
  const best = measurable[0] || null
  const worst = measurable[measurable.length - 1] || null
  const zeroSens = det.filter((x) => x.sensitivity === 0)
  const noPositives = det.filter((x) => x.positives === 0)

  // Assemble the plainly-stated weak-spot phrases from the card (not literals).
  const weakPhrases = []
  const zs = zeroSens[0]
  if (zs) weakPhrases.push(`${prettyName(zs.pathology)} sensitivity is ${fmt3(zs.sensitivity)} (only ${zs.positives} positive${zs.positives === 1 ? '' : 's'})`)
  if (worst && (!zs || worst.pathology !== zs.pathology)) weakPhrases.push(`${prettyName(worst.pathology)} AUROC ≈ ${fmt3(worst.auroc)}`)
  const noPos = noPositives[0]
  if (noPos) weakPhrases.push(`${prettyName(noPos.pathology)} has no positives to score`)

  const nav = (r) => () => onNav && onNav(r)
  const goto = (id) => () => {
    const el = document.getElementById(id)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  // Topic cards. Each either opens a modal, scrolls to an inline answer, or navs.
  const topics = useMemo(() => [
    {
      key: 'start', icon: IconRocket, title: 'Getting started',
      desc: 'Upload a chest X-ray, review AI suggestions, confirm findings, and sign off a report.',
      cue: 'Read the walkthrough', tags: 'upload dicom png jpg workflow report sign off launch',
      onClick: goto('start'),
    },
    {
      key: 'how', icon: IconBrain, title: 'How AI analysis works',
      desc: 'The model, the abstain gate, the attention overlay, and why nothing auto-confirms.',
      cue: 'How it works', tags: 'model densenet grad-cam attention abstain gate ood heatmap',
      onClick: goto('how'),
    },
    {
      key: 'conf', icon: IconGauge, title: 'Reading confidence & calibration',
      desc: 'Why the % is a ranking score, not a probability of disease — and what the numbers mean.',
      cue: 'Understand the score', tags: 'confidence calibration ece auroc probability score threshold',
      onClick: goto('conf'),
    },
    {
      key: 'limits', icon: IconWarn, title: 'Known limitations',
      desc: 'The honest, design-time boundaries you must understand before trusting any output.',
      cue: onOpenLimitations ? 'Open the full list' : 'Read the summary',
      tags: 'limitations boundaries frontal lateral hipaa privacy weak',
      onClick: onOpenLimitations || goto('limits'),
    },
    {
      key: 'fails', icon: IconFlask, title: 'Where it fails (gallery)',
      desc: 'Real, measured failure cases — shortcut learning, weak localization, miscalibration.',
      cue: onOpenFailures ? 'Open the gallery' : 'Read the summary',
      tags: 'failure gallery shortcut localization pointing game miscalibration evidence',
      onClick: onOpenFailures || goto('limits'),
    },
    {
      key: 'privacy', icon: IconLock, title: 'Privacy & data',
      desc: 'What leaves your browser, DICOM de-identification, and why this is a prototype.',
      cue: 'Privacy & data', tags: 'privacy data phi dicom deidentification security prototype',
      onClick: goto('privacy'),
    },
    {
      key: 'contact', icon: IconChat, title: 'Contact & support',
      desc: 'Report a bug, request a feature, or ask a question about the project.',
      cue: 'Get in touch', tags: 'contact support bug feature email help ticket',
      onClick: goto('contact'),
    },
  ], [onOpenLimitations, onOpenFailures]) // eslint-disable-line react-hooks/exhaustive-deps

  const query = q.trim().toLowerCase()
  const shown = query
    ? topics.filter((t) => (t.title + ' ' + t.desc + ' ' + t.tags).toLowerCase().includes(query))
    : topics

  return (
    <div style={{ color: 'var(--ink)' }}>
      {/* Scoped, CSP-safe responsive + a11y rules (kept off styles.css). */}
      <style>{`
        .hp-topic:focus-visible, .hp-link:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
        .hp-search:focus-within { border-color: var(--primary) !important; box-shadow: 0 0 0 3px var(--ring); }
        .hp-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }
        .hp-mid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 18px; }
        @media (max-width: 860px) { .hp-mid { grid-template-columns: 1fr; } }
        @media (prefers-reduced-motion: reduce) { .hp-topic { transition: none !important; } }
      `}</style>

      {/* ---- Hero + search ---- */}
      <section style={{ maxWidth: 760, margin: '0 auto', padding: '64px 28px 8px', textAlign: 'center' }}>
        <h1 style={{ fontSize: 42, fontWeight: 800, letterSpacing: '-.03em', margin: 0 }}>How can we help?</h1>
        <p style={{ color: 'var(--muted)', fontSize: 17, margin: '14px 0 0' }}>
          Search the docs, or browse the topics below. Every answer here reflects what the
          model actually does — no more.
        </p>
        <div className="hp-search" style={{
          display: 'flex', alignItems: 'center', gap: 10, margin: '26px auto 0',
          maxWidth: 560, background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 14, padding: '0 16px', height: 54, boxShadow: 'var(--shadow)',
        }}>
          <span style={{ color: 'var(--faint)', display: 'grid' }}><IconSearch size={19} /></span>
          <input
            ref={searchRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search help topics"
            placeholder="Search topics — calibration, DICOM, privacy, failures…"
            style={{
              flex: 1, border: 'none', background: 'none', outline: 'none',
              font: 'inherit', fontSize: 15, color: 'var(--ink)',
            }}
          />
          {q
            ? <button className="hp-link" onClick={() => { setQ(''); searchRef.current?.focus() }} aria-label="Clear search"
                style={{ ...kbd, background: 'none', cursor: 'pointer', color: 'var(--muted)' }}>Clear ✕</button>
            : <span style={kbd}>{shown.length} topics</span>}
        </div>
      </section>

      {/* ---- Topic grid ---- */}
      <section style={{ maxWidth: 1140, margin: '0 auto', padding: '44px 28px 24px' }}>
        {shown.length > 0 ? (
          <div className="hp-grid">
            {shown.map((t) => <TopicCard key={t.key} {...t} />)}
          </div>
        ) : (
          <p style={{ ...muted, textAlign: 'center', padding: '24px 0' }}>
            No topics match “{q}”. Try “calibration”, “DICOM”, “privacy”, or clear the search.
          </p>
        )}
      </section>

      {/* ---- Inline answers ---- */}
      <div style={{ maxWidth: 1140, margin: '0 auto', padding: '0 28px', display: 'grid', gap: 18 }}>

        <Section id="start" eyebrow="Getting started" title="From upload to a signed report">
          <ol style={{ ...p, paddingLeft: 20, margin: 0 }}>
            <li style={{ marginBottom: 8 }}><strong>Upload</strong> a frontal chest X-ray (PNG, JPG, or DICOM). Optionally add a <em>prior</em> study to compare.</li>
            <li style={{ marginBottom: 8 }}><strong>The self-audit runs first.</strong> RadAssist checks the image is a plausible chest radiograph before it scores anything — and abstains if it is not.</li>
            <li style={{ marginBottom: 8 }}><strong>Review the suggestions.</strong> Each flagged finding is unchecked by default, shown with a confidence band and a highlighted region of attention.</li>
            <li style={{ marginBottom: 8 }}><strong>Confirm, edit, or dismiss</strong> each finding. Only what you check enters the report — the AI never auto-confirms.</li>
            <li style={{ marginBottom: 8 }}><strong>Sign off</strong> with your name and role to unlock report generation, then <strong>export</strong> the clinical report and patient summary as a PDF.</li>
          </ol>
          <div style={{ display: 'flex', gap: 9, marginTop: 16, flexWrap: 'wrap' }}>
            <button className="hp-link" onClick={nav('dashboard')} style={btnPrimary}>Launch the analyzer</button>
            {onOpenInfo && <button className="hp-link" onClick={onOpenInfo} style={btnGhost}>Open the full user guide</button>}
          </div>
        </Section>

        <Section id="how" eyebrow="How AI analysis works" title="What the model does — and what it refuses to do">
          <p style={p}>
            Chest X-rays are scored by a <strong>TorchXRayVision DenseNet-121 ensemble</strong>. For the
            top finding it produces a <strong>Grad-CAM attention overlay</strong> — a coarse map of
            <em> where the model looked</em>, not a lesion boundary. Before any of that, an
            <strong> abstain gate</strong> checks the input: a photo, a CT slice, a non-chest or
            out-of-distribution image is <em>declined, not guessed</em>.
          </p>
          <ul style={{ ...muted, paddingLeft: 20, margin: '0 0 4px' }}>
            <li style={{ marginBottom: 6 }}><strong>Read / down-weight / abstain</strong> — the self-audit decides whether to show results normally, with reduced competence, or not at all.</li>
            <li style={{ marginBottom: 6 }}><strong>Human-in-the-loop, always</strong> — no AI output populates a signed report until a clinician confirms it.</li>
            <li style={{ marginBottom: 6 }}><strong>A blank finding is explained</strong> — every finding carries an explicit map state (localized / diffuse / suppressed / none / not-computed / error).</li>
          </ul>
          {onOpenInfo && (
            <button className="hp-link" onClick={onOpenInfo} style={{ ...btnGhost, marginTop: 14 }}>
              Full workflow, formats & measurements →
            </button>
          )}
        </Section>

        <Section id="conf" eyebrow="Reading the confidence" title="The % is a ranking score, not a probability of disease" tone="warn">
          <p style={p}>
            The percentage on a finding is a <strong>raw ranking score</strong> used to rank and flag
            (flagged at or above the 50% operating point). It is <strong>not</strong> a calibrated
            probability and tends to be over-confident. Where a per-label calibration exists the
            viewer shows a separate <em>P≈</em>; otherwise a “not calibrated” chip. Read the
            disposition, not the bare number.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, margin: '14px 0 4px' }}>
            <Metric value={fmt(ece)} label="Expected Calibration Error (0 = perfect) — the score is not a probability" />
            <Metric value={pa != null || ap != null ? `PA ${fmt3(pa)} / AP ${fmt3(ap)}` : '—'} label="Micro-AUROC by view — performance shifts on portable films" />
            <Metric
              value={best && worst ? `${fmt3(best.auroc)} → ${fmt3(worst.auroc)}` : '—'}
              label={best && worst
                ? `Per-pathology AUROC, best (${prettyName(best.pathology)}) to worst (${prettyName(worst.pathology)})`
                : 'Per-pathology AUROC (unavailable)'}
            />
          </div>
          <p style={muted}>
            {live
              ? <>These numbers are sourced live from this deployment’s behavior card.{weakPhrases.length > 0 && <> Weak spots are stated plainly: {weakPhrases.join(', ')}.</>} High confidence on a finding the model is weak at still warrants your own read.</>
              : 'Measured metrics are unavailable right now — the live behavior card was not reachable. We show real measured numbers here or nothing at all, never an invented figure.'}
          </p>
        </Section>

        {/* Limits / failures: prefer the rich modals; degrade to a summary + nav. */}
        <Section id="limits" eyebrow="Boundaries & failures" title="Know the limits before you trust the output" tone="warn">
          <p style={p}>
            RadAssist is a <strong>research-grade prototype — not FDA-cleared and not a medical device</strong>.
            Real-world performance is lower than any benchmark. The heatmap is model attention, not a
            lesion boundary. The chest model is validated on <strong>frontal</strong> views only; the
            CT/MRI AI channels are opt-in, off by default, and the candidate detector is explicitly
            unvalidated (it may miss real disease and flag normal anatomy).
          </p>
          <div style={{ display: 'flex', gap: 9, marginTop: 6, flexWrap: 'wrap' }}>
            {onOpenLimitations && <button className="hp-link" onClick={onOpenLimitations} style={btnGhost}>⚠ Full known-limitations list</button>}
            {onOpenFailures && <button className="hp-link" onClick={onOpenFailures} style={btnGhost}>🔬 Where it fails (measured cases)</button>}
            <button className="hp-link" onClick={nav('about')} style={btnGhost}>About the project</button>
          </div>
        </Section>

        <Section id="privacy" eyebrow="Privacy & data" title="What stays in your browser, and what this prototype is not">
          <ul style={{ ...muted, paddingLeft: 20, margin: 0 }}>
            <li style={{ marginBottom: 6 }}><strong>Patient identifiers stay in your browser.</strong> Anything you type for the PDF is never sent to the server and is not persisted.</li>
            <li style={{ marginBottom: 6 }}><strong>DICOM files are de-identified on upload</strong>, secondary captures are quarantined, and uploaded images are swept on a timer. Burned-in pixel text is <em>not</em> removed.</li>
            <li style={{ marginBottom: 6 }}><strong>Not a HIPAA-grade system.</strong> Authentication, a PHI-free audit log, and rate limiting are architecture-ready, but this is a prototype — use public or de-identified images only.</li>
          </ul>
          <button className="hp-link" onClick={nav('privacy')} style={{ ...btnGhost, marginTop: 14 }}>Read the full privacy policy →</button>
        </Section>

        {/* ---- Shortcuts + support (mirrors design 476-497) ---- */}
        <div className="hp-mid">
          <div style={{ ...card, padding: 24 }}>
            <div style={{ ...H, fontSize: 17, marginBottom: 14 }}>Keyboard shortcuts</div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {[
                ['Accept highlighted finding', 'A'],
                ['Reject finding', 'R'],
                ['Toggle Grad-CAM overlay', 'H'],
                ['Sign & finalise report', '⌘ ⏎'],
                ['Next study in worklist', 'J'],
              ].map(([label, key]) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 0', borderTop: '1px solid var(--border)' }}>
                  <span style={{ fontSize: 13.5, color: 'var(--ink-2)' }}>{label}</span>
                  <span style={kbd}>{key}</span>
                </div>
              ))}
            </div>
          </div>

          <div id="contact" style={{
            border: '1px solid var(--border)', borderRadius: 16, padding: 24,
            boxShadow: 'var(--shadow-sm)', display: 'flex', flexDirection: 'column',
            background: 'linear-gradient(135deg,var(--primary-tint),var(--teal-tint))',
            scrollMarginTop: 90,
          }}>
            <span style={{ width: 44, height: 44, borderRadius: 12, display: 'grid', placeItems: 'center', background: 'var(--surface)', color: 'var(--primary)', boxShadow: 'var(--shadow-sm)' }}><IconChat /></span>
            <div style={{ ...H, fontSize: 17, marginTop: 14 }}>Still need a hand?</div>
            <div style={{ fontSize: 13.5, color: 'var(--ink-2)', marginTop: 6, lineHeight: 1.55, flex: 1 }}>
              This is a project prototype, not a staffed support desk — so we won’t promise a
              response time. Report a bug, request a feature, or ask a question and we’ll follow up.
            </div>
            <div style={{ display: 'flex', gap: 9, marginTop: 16, flexWrap: 'wrap' }}>
              <a className="hp-link" href="mailto:theegalasurya@gmail.com?subject=RadAssist%20support" style={btnPrimary}>Contact support</a>
              <a className="hp-link" href="mailto:theegalasurya@gmail.com?subject=RadAssist%20bug%20report" style={{ ...btnGhost, background: 'var(--surface)' }}>Report a bug</a>
            </div>
          </div>
        </div>
      </div>

      <div style={{ height: 40 }} />
    </div>
  )
}

// ---- Buttons & metric tile -------------------------------------------------
const btnPrimary = {
  padding: '10px 16px', borderRadius: 10, border: 'none', background: 'var(--primary)',
  color: 'var(--on-primary, #fff)', fontWeight: 600, fontSize: 13, cursor: 'pointer',
  fontFamily: 'inherit', textDecoration: 'none', display: 'inline-block',
}
const btnGhost = {
  padding: '10px 16px', borderRadius: 10, border: '1px solid var(--border-2)',
  background: 'var(--surface)', color: 'var(--ink)', fontWeight: 600, fontSize: 13,
  cursor: 'pointer', fontFamily: 'inherit', textDecoration: 'none', display: 'inline-block',
}

function Metric({ value, label }) {
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 12, padding: '12px 14px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 17, color: 'var(--ink)' }}>{value}</div>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4, lineHeight: 1.4 }}>{label}</div>
    </div>
  )
}

// Format helpers — keep measured precision, never fabricate digits. Null/NaN
// (unmeasured) renders as an em-dash, never a made-up number.
const prettyName = (s) => String(s || '').replace(/_/g, ' ')
function fmt(n) { return typeof n === 'number' && !Number.isNaN(n) ? n.toFixed(4).replace(/0+$/, '').replace(/\.$/, '') : '—' }
function fmt3(n) { return typeof n === 'number' && !Number.isNaN(n) ? n.toFixed(3) : '—' }
