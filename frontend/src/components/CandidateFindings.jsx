import { useEffect, useRef, useState } from 'react'
import { startDetect, pollDetect, submitFeedback } from '../api.js'

// RESEARCH CADe panel (CT + MR). Surfaces UNVALIDATED disease CANDIDATES for a
// radiologist to confirm/dismiss. This intentionally names candidate diseases, so it
// is wrapped in a hard RESEARCH disclaimer, an abstain gate, and human sign-off +
// feedback. It is NOT the anatomy overlay and NOT a diagnosis.

const TOGGLE_LABEL = 'Candidate findings (AI) — RESEARCH, unvalidated'
const CADE_RED = '#d23c3c'   // disease-candidate framing is RED (amber = anatomy overlay)

// One candidate's slice with its bounding box drawn (mask-native space; the rendered
// review slice is the same space, so the box aligns directly). Box + label are RED and
// carry a pinned "RESEARCH candidate" tag so a disease box can never read as validated.
function CandidateView({ sliceUrl, bbox }) {
  const ref = useRef(null)
  useEffect(() => {
    const cv = ref.current
    if (!cv || !sliceUrl) return
    const ctx = cv.getContext('2d')
    let cancelled = false
    const img = new Image()
    img.onload = () => {
      if (cancelled) return
      cv.width = img.naturalWidth
      cv.height = img.naturalHeight
      ctx.drawImage(img, 0, 0)
      // pinned research tag (top-left)
      ctx.fillStyle = CADE_RED
      ctx.font = `${Math.max(9, Math.round(img.naturalWidth / 22))}px sans-serif`
      ctx.fillText('RESEARCH candidate', 4, Math.max(11, Math.round(img.naturalWidth / 20)))
      if (bbox && bbox.length === 4) {
        ctx.lineWidth = Math.max(1, Math.round(img.naturalWidth / 128))
        ctx.strokeStyle = CADE_RED
        ctx.strokeRect(bbox[0], bbox[1], bbox[2], bbox[3])
      }
    }
    img.onerror = () => { /* leave the (blank) canvas; the list still shows the candidate */ }
    img.src = sliceUrl
    return () => { cancelled = true }
  }, [sliceUrl, bbox])
  return <canvas ref={ref} role="img" aria-label="Candidate region on the review slice (research, unvalidated)"
    style={{ width: '100%', maxWidth: 360, imageRendering: 'pixelated', background: '#000', borderRadius: 8 }} />
}

export default function CandidateFindings({ files, seriesId, modality = 'CT', onConfirmedChange }) {
  const [on, setOn] = useState(false)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [error, setError] = useState(null)
  const [sel, setSel] = useState(0)
  const [fb, setFb] = useState({})   // candidate index -> 'confirmed' | 'dismissed' | 'error'

  async function run() {
    if (!files) return
    setBusy(true); setError(null); setRes(null); setFb({})
    try {
      let r = await startDetect(Array.from(files), modality, seriesId)
      while (r && r.status !== 'done' && r.status !== 'error') {
        await new Promise((z) => setTimeout(z, 1600))
        r = await pollDetect(r.job_id, modality)
      }
      if (!r || r.status === 'error') { setError((r && r.detail) || 'Detection failed'); setBusy(false); return }
      setRes(r); setSel(0); setBusy(false)
    } catch (e) { setError(e.message || String(e)); setBusy(false) }
  }

  // Record confirm/dismiss ONLY after the POST succeeds — a dropped submission must
  // not read as "recorded" (it is the training signal). Mirrors FeedbackThumbs.
  async function sendFeedback(i, event) {
    const c = res?.candidates?.[i]
    if (!c) return
    setFb((p) => ({ ...p, [i]: 'sending' }))
    try {
      await submitFeedback({
        event, target: 'finding', rating: event === 'confirmed' ? 'up' : 'down',
        image_sha256: res.content_sha256, image_source: modality === 'MR' ? 'mr-detect' : 'ct-detect',
        raw_label: c.label, display_label: c.label, raw_score: c.salience,
        calibration_state: 'uncalibrated',
      })
      setFb((p) => ({ ...p, [i]: event }))
    } catch {
      setFb((p) => ({ ...p, [i]: 'error' }))
    }
  }

  const cands = res?.candidates || []
  const cur = cands[sel]

  // Lift the clinician-CONFIRMED candidates to the parent so they can flow into the
  // CT/MRI report draft. ONLY confirmed candidates ever leave this panel — raw
  // detector output must never reach the report (mirrors the backend contract, which
  // accepts confirmed candidates only). Re-running detection resets `fb`, so a stale
  // confirmation can never carry over to a new volume.
  useEffect(() => {
    if (!onConfirmedChange) return
    onConfirmedChange(cands.filter((_, i) => fb[i] === 'confirmed'))
  }, [fb, res]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="card ao-panel">
      <label className="ao-toggle" title="Unvalidated AI candidate detection — research only.">
        <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} />
        <span>{TOGGLE_LABEL}</span>
      </label>

      {on && (
        <>
          <div className="cade-disclaimer" role="alert">
            {res?.disclaimer ||
              'RESEARCH USE ONLY — UNVALIDATED. AI-generated CANDIDATE regions, NOT a diagnosis. '
              + 'May miss real disease and flag normal anatomy. A licensed radiologist must confirm '
              + 'every candidate. Not FDA-cleared, not CE-marked, not a medical device.'}
          </div>

          <div className="ao-controls">
            <button className="btn btn-small" onClick={run} disabled={busy || !files}>
              Run candidate detection (research)
            </button>
            {busy && <span className="muted small">Analyzing…</span>}
          </div>
          {error && <div className="error-bar" role="alert">{error}</div>}

          {res && res.competence !== 'read' && (
            <p className="muted small">
              Detector {res.competence === 'abstain' ? 'ABSTAINED' : 'is cautious'} on this volume
              {res.reasons?.length ? `: ${res.reasons.join('; ')}.` : '.'}
            </p>
          )}

          {res && res.status === 'done' && (
            <>
              <p className="muted small">
                {cands.length
                  ? `${cands.length} candidate region(s) — unvalidated, for review. Salience is a research signal, NOT a disease probability.`
                  : (res.not_a_normal_result_message
                     || 'No candidate regions above threshold. This is NOT a "normal" result — the detector is unvalidated and may miss disease.')}
              </p>

              {cur && (
                <div className="cade-review">
                  <CandidateView sliceUrl={res.slice_urls?.[cur.region?.slice_index]} bbox={cur.region?.bbox} />
                </div>
              )}

              <ul className="cade-list">
                {cands.map((c, i) => (
                  <li key={i} className={`cade-item ${sel === i ? 'active' : ''}`}>
                    <button className="cade-pick" onClick={() => setSel(i)}>
                      <span className="cade-label">{c.label}</span>
                      <span className="cade-meta">
                        candidate detected · salience {c.salience_band || 'low'} (research signal, not a probability)
                        {c.est_max_mm != null ? ` · ≈${c.est_max_mm} mm (est.)` : ''}
                        {c.mean_hu != null ? ` · ${c.mean_hu} HU (est.)` : ''}
                        {` · slice ${(c.region?.slice_index ?? 0) + 1}`}
                      </span>
                      <span className="cade-disp">Unvalidated candidate — confirm; not triage</span>
                    </button>
                    <div className="cade-fb">
                      {fb[i] === 'confirmed' || fb[i] === 'dismissed'
                        ? <span className="muted small">Recorded ({fb[i]}) — thank you.</span>
                        : fb[i] === 'sending'
                          ? <span className="muted small">Saving…</span>
                          : <>
                              {fb[i] === 'error' && <span className="error-bar small" role="alert">Not saved — retry.</span>}
                              <button className="btn btn-small" onClick={() => sendFeedback(i, 'confirmed')}>✓ Confirm</button>
                              <button className="btn btn-small" onClick={() => sendFeedback(i, 'dismissed')}>✗ Dismiss</button>
                            </>}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  )
}
