import { startAnatomySegment, pollAnatomySegment, assertNoDiagnosisFields } from '../api.js'
import StructureLegend from './StructureLegend.jsx'

// A single, opt-in anatomy-labeling overlay panel. This is NOT disease detection:
// it computes approximate organ/tissue regions and labels anatomy only. Default
// OFF — a clean image is always one toggle away. No accept/adopt-to-report
// affordance, and no finding/score/probability language anywhere.

const OVERLAY_TOGGLE_LABEL = 'Anatomy overlay (AI) — approximate, verify'
const OVERLAY_HOVER_FIRSTUSE = 'This does not look for disease.'

// Verbatim from the pinned config contract — persistent, non-dismissible.
const CT_OVERLAY_DISCLAIMER = 'AI anatomy overlay — computed organ regions, not a diagnosis. These outlines label anatomy only; they do not detect, characterize, or exclude any disease, injury, or abnormality. Approximate and frequently wrong at boundaries — a qualified reader must verify every region before any use. Research/education prototype; not FDA-cleared, not CE-marked, not a medical device.'
const MR_OVERLAY_DISCLAIMER = 'AI anatomy overlay (MR) — computed anatomical regions, not a diagnosis. These outlines label anatomy only; they do not detect, characterize, or exclude any disease, injury, or abnormality. MR signal is arbitrary (a.u.) and not quantitative — no intensity shown is tissue-specific, and any region volume is a geometric estimate from voxel spacing, not a measure of disease. Approximate and frequently wrong at boundaries — a qualified reader must verify every region before any use. Research/education prototype; not FDA-cleared, not CE-marked, not a medical device.'

export default function AnatomyOverlayPanel({ modality, files, seriesId, ao, setAo }) {
  const seg = ao.seg
  const disclaimer = modality === 'CT' ? CT_OVERLAY_DISCLAIMER : MR_OVERLAY_DISCLAIMER

  function toggleOverlay(e) {
    const on = e.target.checked
    setAo((prev) => ({ ...prev, overlayOn: on }))
  }

  function setOpacity(e) {
    const v = parseFloat(e.target.value)
    setAo((prev) => ({ ...prev, opacity: v }))
  }

  function toggleHidden(id) {
    setAo((prev) => {
      const hidden = new Set(prev.hidden)
      if (hidden.has(id)) hidden.delete(id)
      else hidden.add(id)
      return { ...prev, hidden }
    })
  }

  async function run() {
    if (!files) return
    setAo((prev) => ({ ...prev, busy: true, error: null }))
    try {
      let res = await startAnatomySegment(Array.from(files), modality, { seriesId })
      // Poll until the job settles. Fixed 1600ms cadence via setTimeout loop.
      while (res && res.status !== 'done' && res.status !== 'error') {
        await new Promise((r) => setTimeout(r, 1600))
        res = await pollAnatomySegment(res.job_id)
      }
      if (!res || res.status === 'error') {
        const msg = (res && res.detail) || 'Anatomical analysis failed'
        setAo((prev) => ({ ...prev, busy: false, error: msg }))
        return
      }
      assertNoDiagnosisFields(res)
      setAo((prev) => ({ ...prev, seg: res, busy: false, error: null }))
    } catch (err) {
      setAo((prev) => ({ ...prev, busy: false, error: err.message || String(err) }))
    }
  }

  return (
    <div className="card ao-panel">
      <label className="ao-toggle" title={OVERLAY_HOVER_FIRSTUSE}>
        <input type="checkbox" checked={ao.overlayOn} onChange={toggleOverlay} />
        <span>{OVERLAY_TOGGLE_LABEL}</span>
      </label>

      {ao.overlayOn && (
        <>
          <div className="ao-disclaimer" role="note">{disclaimer}</div>

          <div className="ao-controls">
            <button className="btn btn-small" onClick={run} disabled={ao.busy || !files}>
              Run anatomical analysis (opt-in)
            </button>
            {ao.busy && <span className="muted small">Analyzing…</span>}
            <label className="ao-opacity">
              <span className="muted small">Opacity</span>
              <input
                type="range" min="0" max="1" step="0.05"
                value={ao.opacity}
                onChange={setOpacity}
                aria-label="Overlay opacity"
              />
            </label>
          </div>

          {ao.error && <div className="error-bar" role="alert">{ao.error}</div>}

          {seg && (
            <div className="ao-prov">
              {seg.model + ' · ' + seg.license + ' · Computed region · not a finding'}
            </div>
          )}

          <StructureLegend
            regions={seg?.regions || []}
            hidden={ao.hidden}
            onToggle={toggleHidden}
          />
        </>
      )}
    </div>
  )
}
