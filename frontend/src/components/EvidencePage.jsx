import { useEffect, useMemo, useState } from 'react'
import { getBehaviorCard } from '../api.js'

// ---------------------------------------------------------------------------
// EvidencePage — the honest "Measured, not claimed" trust surface.
//
// HONESTY CONTRACT: this page fabricates NOTHING. Every number is read live
// from the model behaviour card (GET /api/behavior-card, surfaced as the
// `behaviorCard` prop and re-fetchable via getBehaviorCard()). When the card is
// missing/unreadable it shows an explicit "metrics unavailable" state — it
// never invents accuracy figures, testimonials, or compliance claims. Weak
// spots (low-AUROC pathologies, zero-sensitivity classes, unmeasurable labels
// with 0 positives, weak Grad-CAM localization) are surfaced, not hidden.
//
// Props:
//   behaviorCard : object | null — the behaviour card (App already holds it).
//                  Shape: { available, model, flag_threshold, images_scored,
//                  caveat, detection:[{pathology,n,positives,reliable,auroc,
//                  sensitivity,specificity,curve}], localization:{available,
//                  per_class:{[name]:{n,hit_rate,mean_iou}}},
//                  calibration:{available,overall:{ece,n,reliability[]}},
//                  subgroup:{available,groups:{[view]:{images,micro_auroc,
//                  label_instances}}} }. If null/undefined, the page fetches it.
//   onNav        : (route:string) => void — marketing-shell navigation. Called
//                  with 'about' and 'dashboard'.
// ---------------------------------------------------------------------------

const SECTION = { maxWidth: 1240, margin: '0 auto', padding: '40px 28px' }
const EYEBROW = {
  color: 'var(--teal-2)', fontWeight: 600, fontSize: 13, letterSpacing: '.08em',
  textTransform: 'uppercase',
}
const CARD = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 14, padding: 18, boxShadow: 'var(--shadow-sm)',
}
const MONO = 'var(--font-mono, ui-monospace, monospace)'

// Pretty-print a pathology label ("Pleural_Thickening" -> "Pleural thickening").
const prettyName = (s) => String(s || '').replace(/_/g, ' ')

// Format a metric that may legitimately be null (unmeasurable) as "—".
const fmt3 = (v) => (v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(3))

// AUROC → semantic colour. Nulls (unmeasurable) render faint, never green.
function aurocColor(v) {
  if (v == null) return 'var(--faint)'
  if (v >= 0.85) return 'var(--success)'
  if (v >= 0.78) return 'var(--teal-2)'
  if (v >= 0.68) return 'var(--warn)'
  return 'var(--danger)'
}

export default function EvidencePage({ behaviorCard, onNav }) {
  // Prefer the prop the App already fetched; fall back to a live fetch so the
  // route works if navigated to directly. Never fabricate on failure.
  const [fetched, setFetched] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let alive = true
    if (behaviorCard == null) {
      setLoading(true)
      getBehaviorCard()
        .then((c) => { if (alive) setFetched(c) })
        .catch(() => { if (alive) setFetched({ available: false }) })
        .finally(() => { if (alive) setLoading(false) })
    }
    return () => { alive = false }
  }, [behaviorCard])

  const card = behaviorCard != null ? behaviorCard : fetched
  const available = !!(card && card.available !== false && Array.isArray(card.detection) && card.detection.length)

  // Derived, honesty-preserving views of the card.
  const derived = useMemo(() => {
    if (!available) return null
    const rows = [...card.detection].sort((a, b) => {
      // Measurable AUROC first (desc); unmeasurable (null) sink to the bottom.
      if (a.auroc == null && b.auroc == null) return 0
      if (a.auroc == null) return 1
      if (b.auroc == null) return -1
      return b.auroc - a.auroc
    })

    const ece = card?.calibration?.overall?.ece ?? null
    const eceN = card?.calibration?.overall?.n ?? null
    const studies = card?.images_scored ?? null
    const groups = card?.subgroup?.groups || {}
    const pa = groups.PA || null
    const ap = groups.AP || null

    // Localization: weighted mean Grad-CAM hit-rate across classes with boxes.
    let locHit = null, locN = 0
    const lp = card?.localization?.per_class
    if (card?.localization?.available && lp) {
      let num = 0, den = 0
      for (const k of Object.keys(lp)) {
        const c = lp[k]
        if (c && typeof c.hit_rate === 'number' && c.n) { num += c.hit_rate * c.n; den += c.n }
      }
      if (den) { locHit = num / den; locN = den }
    }

    // Weak-spot extraction (data-driven, not hardcoded):
    //  - worst measurable pathology by AUROC
    //  - any measured class whose sensitivity is 0 at the flag threshold
    //  - classes that could not be measured (0 positives)
    const measurable = rows.filter((r) => r.auroc != null)
    const worst = measurable.length ? measurable[measurable.length - 1] : null
    const zeroSens = rows.filter((r) => r.sensitivity === 0)
    const unmeasured = rows.filter((r) => r.auroc == null || r.positives === 0)

    return { rows, ece, eceN, studies, pa, ap, locHit, locN, worst, zeroSens, unmeasured }
  }, [available, card])

  // ---- Unavailable / loading states -------------------------------------
  if (!available) {
    return (
      <main>
        <section style={{ ...SECTION, paddingTop: 64, textAlign: 'center', maxWidth: 720 }}>
          <div style={EYEBROW}>Measured, not claimed</div>
          <h1 style={{ fontSize: 40, fontWeight: 800, margin: '16px 0 0', letterSpacing: '-.02em', color: 'var(--ink)' }}>
            Performance metrics unavailable
          </h1>
          <p style={{ fontSize: 16, color: 'var(--muted)', margin: '18px auto 0', maxWidth: 560, lineHeight: 1.6 }}>
            {loading
              ? 'Loading the model behaviour card…'
              : 'The model behaviour card has not been generated yet, so we have no measured numbers to show. '
                + 'Rather than invent figures, this page stays blank until a validation run produces real results.'}
          </p>
          <div style={{ ...CARD, marginTop: 28, textAlign: 'left', display: 'inline-block', maxWidth: 560 }}>
            <div style={{ fontSize: 13.5, color: 'var(--ink-2)', lineHeight: 1.6 }}>
              We never display an accuracy number we have not measured on labelled data.
              When a behaviour card exists, this page renders it verbatim — including where the model fails.
            </div>
          </div>
          <div style={{ marginTop: 26 }}>
            <button onClick={() => onNav && onNav('about')} style={ghostBtn}>How the AI works</button>
          </div>
        </section>
      </main>
    )
  }

  const d = derived
  const model = card.model || 'TorchXRayVision DenseNet-121 ensemble'
  const threshold = card.flag_threshold

  // Negative predictive value of a no-flag read — REAL, in-distribution numbers
  // straight from the behaviour card. Absent => the section renders nothing
  // (never fabricate an NPV). Per-label rows are sorted worst-NPV first (the most
  // disease the model lets through unflagged) and capped to a few.
  const npv = card?.no_flag_npv
  const npvSL = npv?.available !== false ? npv?.study_level : null
  const npvPer = Array.isArray(npv?.per_label)
    ? [...npv.per_label].filter((r) => r && r.npv != null).sort((a, b) => a.npv - b.npv).slice(0, 4)
    : []
  const npvMissPct = npvSL && npvSL.no_flag_images
    ? Math.round((npvSL.missed_disease / npvSL.no_flag_images) * 100)
    : null

  return (
    <main>
      <style>{`
        @media (max-width: 900px) {
          .ev-hero-grid { grid-template-columns: 1fr !important; }
          .ev-limits-grid { grid-template-columns: 1fr !important; }
          .ev-limits-metrics { grid-template-columns: 1fr 1fr !important; }
        }
        @media (prefers-reduced-motion: reduce) { .ev-anim { transition: none !important; } }
      `}</style>

      {/* ---- HERO + HEADLINE METRICS ------------------------------------ */}
      <section style={{ ...SECTION, paddingTop: 56 }}>
        <div className="ev-hero-grid" style={{ display: 'grid', gridTemplateColumns: '.95fr 1.05fr', gap: 36, alignItems: 'start' }}>
          <div>
            <div style={EYEBROW}>Measured, not claimed</div>
            <h1 style={{ fontSize: 40, fontWeight: 800, margin: '12px 0 0', letterSpacing: '-.02em', color: 'var(--ink)', lineHeight: 1.1 }}>
              Radical transparency about performance
            </h1>
            <p style={{ fontSize: 16.5, color: 'var(--muted)', margin: '16px 0 0', lineHeight: 1.6 }}>
              These are the model's real numbers on {d.studies != null ? <b>{d.studies} public studies</b> : 'public studies'} —
              including the pathologies where it does badly. The percentage RadAssist shows is a
              <b> ranking score, never a calibrated probability of disease</b>.
            </p>
            <p style={{ fontSize: 13, color: 'var(--faint)', margin: '14px 0 0', lineHeight: 1.55, fontFamily: MONO }}>
              {model}{threshold != null ? ` · flag threshold ${threshold}` : ''}
            </p>
            <div style={{ marginTop: 22, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <button onClick={() => onNav && onNav('dashboard')} style={primaryBtn}>Try the analyzer</button>
              <button onClick={() => onNav && onNav('about')} style={ghostBtn}>How the AI works</button>
            </div>
          </div>

          {/* Headline metric tiles — ECE, studies scored, PA vs AP AUROC */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <MetricTile
              value={fmt3(d.ece)}
              label="Expected calibration error"
              sub={d.eceN != null ? `over ${d.eceN.toLocaleString()} label-instances — the % is a score, not a probability` : 'the % is a score, not a probability'}
              tone="ink"
            />
            <MetricTile
              value={d.studies != null ? String(d.studies) : '—'}
              label="Public studies scored"
              sub="engineering sanity check, not clinical validation"
              tone="ink"
            />
            <MetricTile
              value={d.pa?.micro_auroc != null ? fmt3(d.pa.micro_auroc) : '—'}
              label={`Micro-AUROC · PA views${d.pa?.images != null ? ` (${d.pa.images} img)` : ''}`}
              sub="frontal, non-portable radiographs"
              tone="ink"
            />
            <MetricTile
              value={d.ap?.micro_auroc != null ? fmt3(d.ap.micro_auroc) : '—'}
              label={`Micro-AUROC · AP views${d.ap?.images != null ? ` (${d.ap.images} img)` : ''}`}
              sub="portable films — performance shifts down"
              tone={d.ap?.micro_auroc != null && d.pa?.micro_auroc != null && d.ap.micro_auroc < d.pa.micro_auroc ? 'warn' : 'ink'}
            />
          </div>
        </div>
      </section>

      {/* ---- PER-PATHOLOGY TABLE ---------------------------------------- */}
      <section style={{ ...SECTION, paddingTop: 20 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
          <div>
            <div style={EYEBROW}>Per-pathology behaviour</div>
            <h2 style={{ fontSize: 28, fontWeight: 700, margin: '10px 0 0', color: 'var(--ink)' }}>Every label, best to worst</h2>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12.5, color: 'var(--muted)', flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
              <span style={{ width: 7, height: 7, borderRadius: 99, background: 'var(--success)' }} />
              reliable sample (≥20 positives)
            </span>
            <span>AUROC coloured by strength; sensitivity at threshold {threshold ?? '—'}</span>
          </div>
        </div>

        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 18, padding: 8, boxShadow: 'var(--shadow)', overflowX: 'auto' }}>
          <div style={{ minWidth: 560 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1.7fr .6fr 1.15fr .55fr', gap: 8, padding: '12px 16px 8px', fontSize: 11, fontWeight: 700, letterSpacing: '.05em', color: 'var(--faint)', textTransform: 'uppercase' }}>
              <span>Pathology</span>
              <span style={{ textAlign: 'right' }}>AUROC</span>
              <span>Sensitivity</span>
              <span style={{ textAlign: 'right' }}>n+</span>
            </div>
            {d.rows.map((r) => {
              const sens = r.sensitivity
              const sensPct = sens == null ? 0 : Math.max(0, Math.min(1, sens)) * 100
              return (
                <div key={r.pathology} style={{ display: 'grid', gridTemplateColumns: '1.7fr .6fr 1.15fr .55fr', gap: 8, alignItems: 'center', padding: '9px 16px', borderTop: '1px solid var(--border)' }}>
                  <span style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: 8 }}>
                    {prettyName(r.pathology)}
                    {r.reliable
                      ? <span title="reliable sample size (≥20 positives)" style={{ width: 6, height: 6, borderRadius: 99, background: 'var(--success)', flex: 'none' }} />
                      : <span title={r.positives === 0 ? 'not measurable — 0 positives in sample' : `indicative only — ${r.positives} positives`} style={{ width: 6, height: 6, borderRadius: 99, background: 'var(--faint)', opacity: .6, flex: 'none' }} />}
                  </span>
                  <span style={{ textAlign: 'right', fontSize: 13.5, fontWeight: 600, color: aurocColor(r.auroc), fontFamily: MONO }}>
                    {fmt3(r.auroc)}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ flex: 1, height: 6, borderRadius: 99, background: 'var(--surface-3)', overflow: 'hidden' }}>
                      <div className="ev-anim" style={{ height: '100%', width: `${sensPct}%`, background: sens === 0 ? 'var(--danger)' : 'var(--primary)', borderRadius: 99, transition: 'width .4s ease' }} />
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--muted)', width: 34, fontFamily: MONO, textAlign: 'right' }}>{fmt3(sens).replace(/^—$/, '—')}</span>
                  </div>
                  <span style={{ textAlign: 'right', fontSize: 12.5, color: 'var(--muted)', fontFamily: MONO }}>{r.positives ?? '—'}</span>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* ---- EXPLICIT WEAK SPOTS ---------------------------------------- */}
      <section style={{ ...SECTION, paddingTop: 20 }}>
        <div style={EYEBROW}>Where it fails</div>
        <h2 style={{ fontSize: 28, fontWeight: 700, margin: '10px 0 20px', color: 'var(--ink)' }}>The parts we most want you to see</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 16 }}>
          {d.worst && (
            <WeakCard
              tag="Worst measured label"
              title={`${prettyName(d.worst.pathology)} · AUROC ${fmt3(d.worst.auroc)}`}
              body={
                d.worst.sensitivity === 0
                  ? `Sensitivity ${fmt3(d.worst.sensitivity)} at the flag threshold with only ${d.worst.positives} positive${d.worst.positives === 1 ? '' : 's'} in the sample — effectively a coin-flip that misses real cases. Treat any flag here as unproven.`
                  : `Only ${d.worst.positives} positive${d.worst.positives === 1 ? '' : 's'} in the sample; below-random discrimination. Treat flags here as unproven.`
              }
            />
          )}

          {d.zeroSens.filter((z) => !d.worst || z.pathology !== d.worst.pathology).slice(0, 1).map((z) => (
            <WeakCard
              key={z.pathology}
              tag="Zero sensitivity"
              title={`${prettyName(z.pathology)} · misses every positive`}
              body={`At the ${threshold ?? 'flag'} threshold this label catches none of its ${z.positives} positive${z.positives === 1 ? '' : 's'}. It contributes no reliable detection.`}
            />
          ))}

          <WeakCard
            tag="Grad-CAM localization"
            title={d.locHit != null ? `Weak — ~${Math.round(d.locHit * 100)}% attention hit-rate` : 'Weak — region of attention only'}
            body={
              (d.locHit != null
                ? `Across ${d.locN} boxed findings, Grad-CAM overlaps the ground-truth region only about ${Math.round(d.locHit * 100)}% of the time. `
                : '')
              + 'The heat map shows where the model looked, not a lesion boundary — it can be diffuse or land on normal anatomy.'
            }
          />

          {d.unmeasured.length > 0 && (
            <WeakCard
              tag="Not measurable"
              title={`${d.unmeasured.map((u) => prettyName(u.pathology)).slice(0, 3).join(', ')}${d.unmeasured.length > 3 ? ` +${d.unmeasured.length - 3}` : ''}`}
              body={`These labels had too few (or zero) positives in the sample to produce a trustworthy AUROC. We show them as unmeasured rather than reporting a misleading number.`}
            />
          )}
        </div>
      </section>

      {/* ---- CALIBRATION EXPLAINER -------------------------------------- */}
      <section style={{ ...SECTION, paddingTop: 20 }}>
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 18, padding: '28px 30px', boxShadow: 'var(--shadow-sm)' }}>
          <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <div style={{ ...CARD, background: 'var(--surface)', minWidth: 150, textAlign: 'center', flex: 'none' }}>
              <div style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, color: 'var(--warn)' }}>{fmt3(d.ece)}</div>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>calibration error</div>
            </div>
            <div style={{ flex: 1, minWidth: 260 }}>
              <div style={{ ...EYEBROW, color: 'var(--warn)' }}>Read the number honestly</div>
              <h3 style={{ fontSize: 20, fontWeight: 700, margin: '8px 0 0', color: 'var(--ink)' }}>The % is a score, not a probability of disease</h3>
              <p style={{ fontSize: 14.5, color: 'var(--muted)', margin: '10px 0 0', lineHeight: 1.6 }}>
                An expected calibration error of <b style={{ color: 'var(--ink)' }}>{fmt3(d.ece)}</b> means the displayed confidence is
                systematically off from the true positive rate — a "70%" does not mean a 7-in-10 chance of the finding being present.
                Use the number to <b>rank and prioritise</b>, never to quote a probability to a patient. A licensed radiologist confirms every flag.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ---- NPV OF A NO-FLAG READ (measured, in-distribution) ----------- */}
      {npvSL && npvSL.npv != null && (
        <section style={{ ...SECTION, paddingTop: 20 }}>
          <div style={EYEBROW}>Negative predictive value of a no-flag read</div>
          <h2 style={{ fontSize: 28, fontWeight: 700, margin: '10px 0 6px', color: 'var(--ink)' }}>
            A no-flag result is not a normal read
          </h2>
          <p style={{ fontSize: 15, color: 'var(--muted)', margin: '0 0 20px', lineHeight: 1.6, maxWidth: 760 }}>
            When the model flags nothing, how often is the study truly negative? These are the measured
            numbers at the production flag thresholds — <b>in-distribution</b> on the validation sample
            (disease prevalence {npvSL.test_set_prevalence != null ? `~${Math.round(npvSL.test_set_prevalence * 100)}%` : 'far above a screening population'}),
            so they are optimistic. Recompute at your target-population prevalence.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 12 }}>
            <MetricTile
              value={fmt3(npvSL.npv)}
              label="Study-level NPV"
              sub="P(truly negative | model flagged nothing) — TN / (TN + FN)"
              tone={npvSL.npv < 0.9 ? 'warn' : 'ink'}
            />
            <MetricTile
              value={npvMissPct != null ? `~${npvMissPct}%` : '—'}
              label="No-flag studies that still had disease"
              sub={npvSL.missed_disease != null && npvSL.no_flag_images != null
                ? `${npvSL.missed_disease} of ${npvSL.no_flag_images} no-flag studies were missed`
                : 'measured on the validation sample'}
              tone="warn"
            />
            <MetricTile
              value={npvSL.no_flag_images != null ? String(npvSL.no_flag_images) : '—'}
              label="No-flag studies in sample"
              sub={npvSL.n_images != null ? `of ${npvSL.n_images} scored` : 'validation sample'}
              tone="ink"
            />
          </div>

          {npvPer.length > 0 && (
            <div style={{ ...CARD, marginTop: 16, padding: 8 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.7fr .8fr 1fr', gap: 8, padding: '10px 16px 8px', fontSize: 11, fontWeight: 700, letterSpacing: '.05em', color: 'var(--faint)', textTransform: 'uppercase' }}>
                <span>Per-label no-flag NPV (lowest first)</span>
                <span style={{ textAlign: 'right' }}>NPV</span>
                <span style={{ textAlign: 'right' }}>Missed / no-flag</span>
              </div>
              {npvPer.map((r) => (
                <div key={r.pathology} style={{ display: 'grid', gridTemplateColumns: '1.7fr .8fr 1fr', gap: 8, alignItems: 'center', padding: '9px 16px', borderTop: '1px solid var(--border)' }}>
                  <span style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--ink)' }}>{prettyName(r.pathology)}</span>
                  <span style={{ textAlign: 'right', fontSize: 13.5, fontWeight: 600, color: r.npv < 0.95 ? 'var(--warn)' : 'var(--ink)', fontFamily: MONO }}>
                    {fmt3(r.npv)}
                  </span>
                  <span style={{ textAlign: 'right', fontSize: 12.5, color: 'var(--muted)', fontFamily: MONO }}>
                    {r.false_negative != null && r.no_flag_n != null ? `${r.false_negative} / ${r.no_flag_n}` : '—'}
                  </span>
                </div>
              ))}
            </div>
          )}

          {npv?.note && (
            <p style={{ fontSize: 12.5, color: 'var(--faint)', margin: '14px 0 0', lineHeight: 1.55, maxWidth: 860 }}>
              {npv.note}
            </p>
          )}
        </section>
      )}

      {/* ---- INTENDED USE & LIMITS (always-dark panel, About parity) ----- */}
      <section style={{ ...SECTION, paddingTop: 20, paddingBottom: 64 }}>
        <div className="ev-limits-grid" style={{
          background: 'linear-gradient(150deg, color-mix(in srgb, var(--navy) 94%, #000), #0b1728)',
          borderRadius: 22, padding: '40px 38px', boxShadow: 'var(--shadow-lg)',
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32, alignItems: 'center',
        }}>
          <div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '5px 12px', borderRadius: 99, background: 'rgba(255,120,120,.14)', border: '1px solid rgba(255,120,120,.3)', color: '#ffb3b3', fontWeight: 600, fontSize: 12.5 }}>
              Intended use &amp; limits
            </div>
            <h2 style={{ color: '#f0f6ff', fontSize: 26, fontWeight: 700, margin: '18px 0 0' }}>Decision support — not a diagnosis</h2>
            <p style={{ color: '#a9c0e0', fontSize: 15, margin: '14px 0 0', lineHeight: 1.6 }}>
              All outputs are AI-generated and may be incorrect. They must be reviewed, corrected and approved by a licensed
              radiologist before any clinical use. RadAssist is not FDA-cleared and is not a medical device; the numbers on this
              page are an engineering sanity check on public data, not a clinical performance guarantee.
            </p>
            {card.caveat && (
              <p style={{ color: '#7f9cc4', fontSize: 12.5, margin: '14px 0 0', lineHeight: 1.55 }}>{card.caveat}</p>
            )}
          </div>
          <div className="ev-limits-metrics" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <DarkTile value={fmt3(d.ece)} label="Calibration error (ECE)" tone="#fff" />
            <DarkTile value={d.studies != null ? String(d.studies) : '—'} label="Public studies scored" tone="#fff" />
            <DarkTile value={d.pa?.micro_auroc != null ? fmt3(d.pa.micro_auroc) : '—'} label="Micro-AUROC · PA views" tone="#fff" />
            <DarkTile
              value={d.worst ? fmt3(d.worst.auroc) : '—'}
              label={d.worst ? `${prettyName(d.worst.pathology)} AUROC — a known weak spot` : 'known weak spot'}
              tone="#ff9b9b"
            />
          </div>
        </div>
      </section>
    </main>
  )
}

// ---- small presentational helpers -----------------------------------------

function MetricTile({ value, label, sub, tone }) {
  const color = tone === 'warn' ? 'var(--warn)' : 'var(--ink)'
  return (
    <div style={CARD}>
      <div style={{ fontFamily: MONO, fontSize: 26, fontWeight: 600, color }}>{value}</div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-2)', marginTop: 6 }}>{label}</div>
      {sub && <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3, lineHeight: 1.45 }}>{sub}</div>}
    </div>
  )
}

function WeakCard({ tag, title, body }) {
  return (
    <div style={{ ...CARD, borderColor: 'var(--border-2)', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span style={{ alignSelf: 'flex-start', fontSize: 11, fontWeight: 700, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--danger)', background: 'var(--danger-tint)', padding: '3px 9px', borderRadius: 99 }}>{tag}</span>
      <div style={{ fontSize: 15.5, fontWeight: 700, color: 'var(--ink)' }}>{title}</div>
      <p style={{ fontSize: 13.5, color: 'var(--muted)', margin: 0, lineHeight: 1.55 }}>{body}</p>
    </div>
  )
}

function DarkTile({ value, label, tone }) {
  return (
    <div style={{ background: 'rgba(255,255,255,.05)', border: '1px solid rgba(120,160,220,.16)', borderRadius: 14, padding: 16 }}>
      <div style={{ fontFamily: MONO, fontSize: 24, fontWeight: 600, color: tone }}>{value}</div>
      <div style={{ color: '#9db4d6', fontSize: 12, marginTop: 3, lineHeight: 1.4 }}>{label}</div>
    </div>
  )
}

const primaryBtn = {
  padding: '11px 20px', borderRadius: 11, border: 'none', background: 'var(--primary)',
  color: 'var(--on-primary)', fontWeight: 600, fontSize: 14, cursor: 'pointer',
  fontFamily: 'inherit', boxShadow: 'var(--shadow-sm)', whiteSpace: 'nowrap',
}
const ghostBtn = {
  padding: '11px 18px', borderRadius: 11, border: '1px solid var(--border-2)',
  background: 'var(--surface)', color: 'var(--ink)', fontWeight: 600, fontSize: 14,
  cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
}
