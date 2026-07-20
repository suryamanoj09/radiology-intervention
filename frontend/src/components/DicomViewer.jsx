import { useEffect, useMemo, useRef, useState } from 'react'
import { dicomView, dicomViewSeries, dicomRaw, dicomRoi } from '../api.js'
import RawWindowCanvas from './RawWindowCanvas.jsx'
import AnatomyOverlayPanel from './AnatomyOverlayPanel.jsx'
import OverlayLayer from './OverlayLayer.jsx'
import CandidateFindings from './CandidateFindings.jsx'
import CtReportPanel from './CtReportPanel.jsx'
import MeasureLayer from './MeasureLayer.jsx'
import { lengthMm, angleDeg, fmtValue } from '../measureUtils.js'

let _mid = 0
const _newId = () => `m${++_mid}`

// Map one series (from the series endpoint) into the flat `view` shape the stage renders.
function viewFromSeries(sd, i) {
  const s = sd.series[i]
  return {
    slice_urls: s.slice_urls, n_slices_shown: s.n_slices, n_slices_total: s.n_slices_total,
    truncated: s.truncated, is_ct: s.modality === 'CT', is_mr: s.is_mr,
    modality: s.modality, sequence_label: s.inferred_label, presets: [],
    window: s.window, spacing_mm: s.spacing_mm, spacing_col_mm: s.spacing_col_mm,
    slice_thickness_mm: null, body_part: '', plane: s.plane,
    // For anatomy-overlay alignment: which series this view is + its slice positions.
    series_id: s.series_id, slice_positions: s.slice_positions,
    identifiers_removed: sd.identifiers_removed, burned_in: sd.burned_in, disclaimer: sd.disclaimer,
  }
}

// Honest CT/MRI DICOM viewer. NO AI runs by default — the base viewer is model-free
// by construction (windowing + slice navigation + manual caliper) and never requests
// or renders a finding, probability, or diagnosis. It also offers an OPT-IN, default-
// OFF "Anatomy overlay (AI)" that labels/segments anatomy and measures regions ONLY;
// that overlay never detects, characterizes, or excludes disease, and a clean image
// is always one toggle away.

const PRESET_LABEL = {
  brain: 'Brain', stroke: 'Stroke', subdural: 'Subdural', bone: 'Bone (temporal)',
  skeletal: 'Bone (skeletal)', lung: 'Lung', mediastinum: 'Mediastinum',
  abdomen: 'Abdomen', liver: 'Liver', angio: 'Angio',
}

export default function DicomViewer({ modality }) {
  const isCt = modality === 'ct'
  const [files, setFiles] = useState(null)
  const [view, setView] = useState(null)
  const [preset, setPreset] = useState(isCt ? 'brain' : null)
  const [idx, setIdx] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [wl, setWl] = useState({ b: 1, c: 1 }) // display brightness/contrast aid
  // Measurement system: persisted list + undo/redo + in-progress draft.
  const [tool, setTool] = useState('none')     // none|length|angle|roi-rect|roi-ellipse
  const [measurements, setMeasurements] = useState([])
  const [redo, setRedo] = useState([])
  const [draft, setDraft] = useState(null)     // {type, points:[[x,y]...]}
  const [roiBusy, setRoiBusy] = useState(false)
  const [nat, setNat] = useState({ w: 0, h: 0 })
  const [cine, setCine] = useState(false)
  const [fps, setFps] = useState(8)
  const [compare, setCompare] = useState(false)   // 2-up compare
  const [cmpSeries, setCmpSeries] = useState(0)
  const [cmpIdx, setCmpIdx] = useState(0)
  const [linkScroll, setLinkScroll] = useState(true)
  const [seriesData, setSeriesData] = useState(null)  // MRI: the series[] response
  const [selSeries, setSelSeries] = useState(0)
  const [rawData, setRawData] = useState(null)        // volume-pivot: raw intensity for canvas WL
  const [rawBusy, setRawBusy] = useState(false)
  // Opt-in anatomy-overlay (AI) state. Default OFF — a clean image is one toggle away.
  const [ao, setAo] = useState({ overlayOn: false, seg: null, hidden: new Set(), opacity: 0.4, busy: false, error: null })
  const [aiTab, setAiTab] = useState('anatomy')   // unified AI rail: anatomy | candidates
  const [hotkeysOpen, setHotkeysOpen] = useState(false)
  // Findings -> Report parity: top-level Viewer/Report switch + the clinician-CONFIRMED
  // candidates lifted from CandidateFindings (only confirmed candidates reach the report).
  const [viewMode, setViewMode] = useState('workspace')   // 'workspace' | 'report'
  const [confirmedCands, setConfirmedCands] = useState([])
  const [drag, setDrag] = useState(false)   // dropzone drag-over highlight
  const imgRef = useRef(null)

  async function toggleRaw() {
    if (rawData) { setRawData(null); return }
    if (!files) return
    setRawBusy(true)
    try { setRawData(await dicomRaw(Array.from(files))) } catch { /* ignore */ }
    finally { setRawBusy(false) }
  }

  async function load(fileList, presetName) {
    if (!fileList || !fileList.length) return
    setBusy(true); setError(null)
    try {
      if (isCt) {
        const res = await dicomView(Array.from(fileList), presetName)
        setSeriesData(null); setView(res)
        setIdx((i) => Math.min(i, Math.max(0, res.n_slices_shown - 1)))
      } else {
        // MRI: series-grouped (T1/T2/FLAIR/DWI/ADC each their own series).
        const sd = await dicomViewSeries(Array.from(fileList), presetName)
        setSeriesData(sd); setSelSeries(0)
        setView(viewFromSeries(sd, 0)); setIdx(0)
      }
      // A new study invalidates EVERYTHING tied to the previous one: measurements,
      // overlay (incl. hidden-structure set), raw-window canvas, and 2-up compare
      // state (a stale cmpSeries index would otherwise crash on a smaller study).
      setMeasurements([]); setRedo([]); setDraft(null); setTool('none')
      setCompare(false); setCmpSeries(0); setCmpIdx(0)
      setRawData(null); setRawBusy(false)
      setConfirmedCands([]); setViewMode('workspace')
      setAo((a) => ({ overlayOn: false, seg: null, hidden: new Set(), opacity: a.opacity, busy: false, error: null }))
    } catch (e) {
      setError(e.message); setView(null); setSeriesData(null)
    } finally {
      setBusy(false)
    }
  }

  function selectSeries(i) {
    if (!seriesData) return
    setSelSeries(i); setView(viewFromSeries(seriesData, i)); setIdx(0)
    // A different series has different slices — reset measurements + draft, drop the
    // stale overlay + raw-window (both are tied to the previous series).
    setMeasurements([]); setRedo([]); setDraft(null); setRawData(null)
    setConfirmedCands([])
    setAo((a) => ({ ...a, seg: null, error: null }))
  }

  // Shared load path for the file picker AND drag-and-drop — identical behavior.
  function loadPicked(fl) {
    if (!fl || !fl.length) return
    setFiles(fl)
    setIdx(0)
    load(fl, preset)
  }

  function onPick(e) {
    loadPicked(e.target.files)
  }

  function onDrop(e) {
    e.preventDefault()
    setDrag(false)
    loadPicked(e.dataTransfer?.files)
  }

  function changePreset(name) {
    setPreset(name)
    if (files) load(files, name) // re-render server-side at the new HU window
  }

  // Keyboard: slice nav + measurement tools + cine + undo/redo. (Ignored while typing.)
  useEffect(() => {
    if (!view) return
    const onKey = (e) => {
      const tag = e.target.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return
      const mod = e.ctrlKey || e.metaKey
      if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); undoMeasure(); return }
      if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); redoMeasure(); return }
      if (mod) return
      const n = view.n_slices_shown
      const k = e.key.toLowerCase()
      if (e.key === 'ArrowUp' || e.key === 'ArrowRight') setIdx((i) => Math.min(i + 1, n - 1))
      else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') setIdx((i) => Math.max(i - 1, 0))
      else if (e.key === 'Home') setIdx(0)
      else if (e.key === 'End') setIdx(n - 1)
      else if (e.key === 'Escape') { setDraft(null); setTool('none') }
      else if (k === 'c') setCine((c) => !c)
      else if (k === 'l') { setTool((t) => (t === 'length' ? 'none' : 'length')); setDraft(null) }
      else if (k === 'a') { setTool((t) => (t === 'angle' ? 'none' : 'angle')); setDraft(null) }
      else if (k === 'o') { setTool((t) => (t.startsWith('roi') ? 'none' : 'roi-rect')); setDraft(null) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [view])

  // Cine playback: advance slices at fps, looping. Stops on unmount / view change.
  useEffect(() => {
    if (!cine || !view || view.n_slices_shown < 2) return
    const iv = setInterval(() => setIdx((i) => (i + 1) % view.n_slices_shown), Math.max(30, 1000 / fps))
    return () => clearInterval(iv)
  }, [cine, fps, view])

  const spacing = view?.spacing_mm
  const spacingCol = view?.spacing_col_mm || spacing

  function addMeasurement(m) { setMeasurements((ms) => [...ms, { ...m, id: _newId() }]); setRedo([]) }
  function undoMeasure() {
    setMeasurements((ms) => {
      if (!ms.length) return ms
      setRedo((r) => [...r, ms[ms.length - 1]])
      return ms.slice(0, -1)
    })
  }
  function redoMeasure() {
    setRedo((r) => {
      if (!r.length) return r
      setMeasurements((ms) => [...ms, r[r.length - 1]])
      return r.slice(0, -1)
    })
  }
  function deleteMeasure(id) { setMeasurements((ms) => ms.filter((m) => m.id !== id)) }
  function cancelTool() { setDraft(null); setTool('none') }

  async function onMeasurePoint(x, y) {
    if (tool === 'length') {
      const p = draft?.points || []
      if (p.length === 0) { setDraft({ type: 'length', points: [[x, y]] }); return }
      addMeasurement({ type: 'length', sliceIndex: idx, points: [p[0], [x, y]],
        value: lengthMm(p[0], [x, y], spacing, spacingCol), px: Math.hypot(x - p[0][0], y - p[0][1]) })
      setDraft(null)
    } else if (tool === 'angle') {
      const p = draft?.points || []
      if (p.length < 2) { setDraft({ type: 'angle', points: [...p, [x, y]] }); return }
      addMeasurement({ type: 'angle', sliceIndex: idx, points: [p[0], p[1], [x, y]],
        value: angleDeg(p[0], p[1], [x, y], spacing, spacingCol) })
      setDraft(null)
    } else if (tool === 'roi-rect' || tool === 'roi-ellipse') {
      const p = draft?.points || []
      if (p.length === 0) { setDraft({ type: tool, points: [[x, y]] }); return }
      const p0 = p[0], W = nat.w || 1, H = nat.h || 1
      const roiType = tool === 'roi-ellipse' ? 'ellipse' : 'rect'
      const shape = { type: roiType, nx: Math.min(p0[0], x) / W, ny: Math.min(p0[1], y) / H,
        nw: Math.abs(x - p0[0]) / W, nh: Math.abs(y - p0[1]) / H }
      setDraft(null); setRoiBusy(true)
      try {
        const stats = await dicomRoi(Array.from(files), shape,
          { seriesId: view.series_id, slicePosition: view.slice_positions?.[idx] })
        addMeasurement({ type: 'roi', roiType, sliceIndex: idx, points: [p0, [x, y]], roi: stats })
      } catch (e) { setError(e.message) } finally { setRoiBusy(false) }
    }
  }

  const win = view?.window
  const winText = useMemo(() => {
    if (!win) return ''
    if (win.unit === 'HU') return `W ${win.width} / L ${win.center} HU${win.preset ? ` · ${win.preset}` : ''}`
    return `auto window · a.u.`
  }, [win])

  // 2-up compare: a second pane (another MRI series, or the same CT series at another slice).
  // Clamp cmpSeries so a stale index (from a prior, larger study) can never index past the
  // current series[] and crash render.
  const safeCmpSeries = seriesData ? Math.min(cmpSeries, seriesData.series.length - 1) : 0
  const cmpView = isCt ? view : (seriesData ? viewFromSeries(seriesData, safeCmpSeries) : view)
  const cmpMax = (cmpView?.n_slices_shown || 1) - 1
  const effCmpIdx = Math.min(linkScroll ? idx : cmpIdx, cmpMax)
  function toggleCompare() {
    setCompare((c) => {
      const nc = !c
      if (nc && seriesData && seriesData.series.length > 1 && cmpSeries === selSeries) {
        setCmpSeries((selSeries + 1) % seriesData.series.length)
      }
      return nc
    })
  }

  // Clear the loaded study so a fresh DICOM series can be uploaded. Resets EVERYTHING
  // tied to the current study: the image/series, measurements, overlay, raw window,
  // 2-up compare, confirmed candidates, and the report draft.
  function clearStudy() {
    setFiles(null); setView(null); setSeriesData(null); setSelSeries(0)
    setError(null); setBusy(false); setIdx(0)
    setMeasurements([]); setRedo([]); setDraft(null); setTool('none')
    setCine(false)
    setCompare(false); setCmpSeries(0); setCmpIdx(0)
    setRawData(null); setRawBusy(false)
    setConfirmedCands([]); setViewMode('workspace')
    setPreset(isCt ? 'brain' : null)
    setAo((a) => ({ overlayOn: false, seg: null, hidden: new Set(), opacity: a.opacity, busy: false, error: null }))
  }

  return (
    <div className="card dicom-viewer">
      <div className="dv-head">
        <h3>{isCt ? 'CT' : 'MRI'} viewer</h3>
        <span className="dv-noai">Viewer + two opt-in AI channels · off by default</span>
      </div>

      <div className="dv-banner" role="note">
        <strong>No AI runs by default on {isCt ? 'CT' : 'MRI'}.</strong> This is a DICOM image
        viewer — windowing, slice navigation, cine, and a full measurement suite. Two AI channels
        are available below and <strong>off by default</strong>: an <strong>anatomy overlay</strong>
        that labels organs and tissue (never disease), and a <strong>research candidate detector</strong>
        that surfaces <strong>unvalidated</strong> disease candidates for a clinician to confirm. The
        candidate detector is research-grade and not validated — it may miss real disease or flag normal
        anatomy — and is not a medical device or a diagnosis.
      </div>

      <label
        className={`dv-upload${drag ? ' drag' : ''}${view ? ' done' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        <input type="file" accept=".dcm,.dicom,application/dicom" multiple onChange={onPick} />
        <span className="dv-dz-icon" aria-hidden="true">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 15V3m0 0 4 4m-4-4L8 7" />
            <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
          </svg>
        </span>
        <span className="dv-dz-label">
          {view
            ? `${isCt ? 'CT' : 'MR'} series loaded — drop another to replace`
            : `Drop a ${isCt ? 'CT' : 'MR'} DICOM series here, or click to browse`}
        </span>
        <span className="dv-dz-sub">.dcm — select all slices; de-identified in memory</span>
      </label>

      {view && (
        <div style={{ marginTop: 8 }}>
          <button type="button" className="btn btn-small" onClick={clearStudy}
            title="Clear this study (image, measurements, overlays, report) and upload a fresh series">
            ✕ Clear &amp; upload fresh
          </button>
        </div>
      )}

      {busy && <p className="muted">Rendering…</p>}
      {error && <div className="error-bar" role="alert">{error}</div>}

      {view && (
        <>
          {/* Top-level Viewer / Report switch — parity with the X-ray AI rail's
              findings/report tabs. Both panes stay MOUNTED (display toggle) so a
              running detection job, the overlay, and confirmed candidates survive a
              tab switch. */}
          <div className="dv-viewmode seg" role="tablist" aria-label="Workspace mode">
            <button role="tab" aria-selected={viewMode === 'workspace'}
              className={viewMode === 'workspace' ? 'active' : ''}
              onClick={() => setViewMode('workspace')}>Viewer &amp; findings</button>
            <button role="tab" aria-selected={viewMode === 'report'}
              className={viewMode === 'report' ? 'active' : ''}
              onClick={() => setViewMode('report')}>
              Report{confirmedCands.length ? ` · ${confirmedCands.length}` : ''}
            </button>
          </div>

          <div style={{ display: viewMode === 'workspace' ? 'block' : 'none' }}>
          {view.burned_in !== 'NO' && (
            <div className="dv-warn" role="alert">
              ⚠ Burned-in annotation is <b>{view.burned_in === 'YES' ? 'present' : 'unknown'}</b> —
              text in the image pixels is <b>not</b> removed and may contain identifiers.
            </div>
          )}

          {/* MRI series rail: one entry per SERIES (T1/T2/FLAIR/DWI/ADC), each with
              a coded-tag "auto — verify" sequence label + plane. DWI/ADC pairs noted. */}
          {seriesData && seriesData.series.length > 0 && (
            <div className="dv-series-rail" role="group" aria-label="Series">
              {seriesData.series.map((s, i) => {
                const paired = seriesData.pairs.some(
                  (p) => p.dwi_series_id === s.series_id || p.adc_series_id === s.series_id)
                return (
                  <button key={s.series_id}
                    className={`dv-series ${selSeries === i ? 'active' : ''}`}
                    onClick={() => selectSeries(i)}
                    title={`${s.inferred_label} · ${s.plane} · ${s.n_slices} slices · auto-detected, verify`}>
                    <span className="dv-series-label">{s.inferred_label}
                      {s.label_confidence < 0.5 ? ' ?' : ''}</span>
                    <span className="dv-series-meta">{s.plane} · {s.n_slices}{paired ? ' · DWI/ADC' : ''}</span>
                    <span className="dv-series-verify">auto — verify</span>
                  </button>
                )
              })}
            </div>
          )}
          {seriesData && (
            <p className="muted small">
              MRI sequence labels are auto-detected from coded tags only (not the scrubbed
              free-text description) — <b>verify</b> before relying on them.
              {seriesData.n_quarantined ? ` ${seriesData.n_quarantined} secondary-capture/report file(s) hidden.` : ''}
            </p>
          )}

          {isCt && view.presets?.length > 0 && (
            <div className="dv-presets seg" role="group" aria-label="CT window presets">
              {view.presets.map((p) => (
                <button key={p} className={preset === p ? 'active' : ''} onClick={() => changePreset(p)}>
                  {PRESET_LABEL[p] || p}
                </button>
              ))}
            </div>
          )}

          <div className={`dv-stage ${compare ? 'dv-stage-2up' : ''}`}>
            {/* Primary pane (interactive: measurements, overlay, tools). */}
            <div className="dv-pane" onWheel={(e) => {
              e.preventDefault()
              setIdx((i) => Math.max(0, Math.min(view.n_slices_shown - 1, i + (e.deltaY > 0 ? 1 : -1))))
            }}>
              {/* shrink-wraps the image so the absolute overlay tracks the image box. */}
              <div className="dv-imgwrap">
                <img
                  ref={imgRef}
                  className="dv-img"
                  src={view.slice_urls[idx]}
                  alt={`${view.modality} slice ${idx + 1} of ${view.n_slices_shown}`}
                  draggable={false}
                  onLoad={(e) => setNat({ w: e.target.naturalWidth, h: e.target.naturalHeight })}
                  style={{ filter: `brightness(${wl.b}) contrast(${wl.c})` }}
                />
                {ao.overlayOn && ao.seg && (
                  <OverlayLayer seg={ao.seg} sliceIndex={idx} hidden={ao.hidden} opacity={ao.opacity}
                    viewSeriesId={view.series_id} viewPositions={view.slice_positions} />
                )}
                <MeasureLayer naturalW={nat.w} naturalH={nat.h} tool={tool} measurements={measurements}
                  draft={draft} sliceIndex={idx} onPoint={onMeasurePoint} />
              </div>
              <div className="dv-hud dv-hud-bl">{winText}</div>
              <div className="dv-hud dv-hud-br">{idx + 1} / {view.n_slices_shown}{cine ? ' ▶' : ''}</div>
            </div>

            {/* Compare pane (read-only image; measurements/AI stay on the primary). */}
            {compare && cmpView && (
              <div className="dv-pane" onWheel={(e) => {
                e.preventDefault()
                if (!linkScroll) setCmpIdx((i) => Math.max(0, Math.min(cmpMax, i + (e.deltaY > 0 ? 1 : -1))))
              }}>
                <div className="dv-imgwrap">
                  <img className="dv-img" src={cmpView.slice_urls[effCmpIdx]} draggable={false}
                    alt={`compare slice ${effCmpIdx + 1}`}
                    style={{ filter: `brightness(${wl.b}) contrast(${wl.c})` }} />
                </div>
                <div className="dv-hud dv-hud-bl">
                  {isCt ? 'same series' : (seriesData?.series[safeCmpSeries]?.inferred_label || 'series')}
                </div>
                <div className="dv-hud dv-hud-br">{effCmpIdx + 1} / {cmpView.n_slices_shown}</div>
              </div>
            )}
            {roiBusy && <div className="measure-label">computing ROI…</div>}
          </div>

          {compare && (
            <div className="dv-cmp-ctrl">
              <span className="muted small">Compare:</span>
              {!isCt && seriesData && seriesData.series.length > 1 && (
                <select value={cmpSeries} onChange={(e) => setCmpSeries(parseInt(e.target.value))}
                  aria-label="Compare series">
                  {seriesData.series.map((s, i) => (
                    <option key={s.series_id} value={i}>{s.inferred_label} ({s.plane})</option>
                  ))}
                </select>
              )}
              <label className="dv-cmp-link"><input type="checkbox" checked={linkScroll}
                onChange={(e) => setLinkScroll(e.target.checked)} /> link scroll</label>
              {!linkScroll && cmpView && cmpView.n_slices_shown > 1 && (
                <input type="range" min="0" max={cmpMax} value={effCmpIdx}
                  onChange={(e) => setCmpIdx(parseInt(e.target.value))} aria-label="Compare slice" />
              )}
            </div>
          )}

          {view.n_slices_shown > 1 && (
            <div className="dv-slice">
              <button className="btn btn-small" onClick={() => setIdx((i) => Math.max(0, i - 1))}>‹</button>
              <input type="range" min="0" max={view.n_slices_shown - 1} value={idx}
                onChange={(e) => setIdx(parseInt(e.target.value))} aria-label="Slice" />
              <button className="btn btn-small" onClick={() => setIdx((i) => Math.min(view.n_slices_shown - 1, i + 1))}>›</button>
              <span className="muted small">slice {idx + 1} / {view.n_slices_shown}
                {view.truncated ? ` (of ${view.n_slices_total} — capped)` : ''}</span>
            </div>
          )}

          <div className="dv-tools">
            <div className="dv-toolrail seg" role="group" aria-label="Measurement tools">
              {[['length', '📏 Length'], ['angle', '∠ Angle'], ['roi-rect', '▭ ROI'], ['roi-ellipse', '⬭ ROI●']].map(([t, lbl]) => (
                <button key={t} className={tool === t ? 'active' : ''}
                  onClick={() => { setTool(tool === t ? 'none' : t); setDraft(null) }}>{lbl}</button>
              ))}
              <button onClick={undoMeasure} disabled={!measurements.length} title="Undo (Ctrl+Z)" aria-label="Undo measurement">↶</button>
              <button onClick={redoMeasure} disabled={!redo.length} title="Redo (Ctrl+Y)" aria-label="Redo measurement">↷</button>
            </div>
            {tool !== 'none' && <span className="muted small">click the image · Esc cancels</span>}
            <button className={cine ? 'btn btn-small active' : 'btn btn-small'} onClick={() => setCine((c) => !c)}
              disabled={view.n_slices_shown < 2} title="Cine play/pause (C)">{cine ? '⏸ Cine' : '▶ Cine'}</button>
            <label className="wl-slider" title="Cine frames per second">fps
              <input type="range" min="2" max="24" step="1" value={fps} onChange={(e) => setFps(parseInt(e.target.value))} /></label>
            <label className="wl-slider">B<input type="range" min="0.4" max="2" step="0.05"
              value={wl.b} onChange={(e) => setWl((w) => ({ ...w, b: parseFloat(e.target.value) }))} /></label>
            <label className="wl-slider">C<input type="range" min="0.4" max="2.2" step="0.05"
              value={wl.c} onChange={(e) => setWl((w) => ({ ...w, c: parseFloat(e.target.value) }))} /></label>
            <button className={rawData ? 'btn btn-small active' : 'btn btn-small'} onClick={toggleRaw}
              disabled={rawBusy} title="True HU/a.u. window/level on RAW intensity via canvas (volume-pivot)">
              🎚 {rawBusy ? 'loading…' : rawData ? 'Raw WL on' : 'Raw window (canvas)'}
            </button>
            <button className={compare ? 'btn btn-small active' : 'btn btn-small'} onClick={toggleCompare}
              disabled={!isCt && !(seriesData && seriesData.series.length > 1) && view.n_slices_shown < 2}
              title="2-up compare">▥ Compare</button>
            <button className="btn btn-small" onClick={() => setHotkeysOpen((h) => !h)} title="Keyboard shortcuts">⌨ Keys</button>
            {!spacing && <span className="muted small">· mm needs pixel spacing</span>}
          </div>

          {hotkeysOpen && (
            <div className="dv-hotkeys" role="note">
              <b>Keyboard:</b> ← → / ↑ ↓ slice · Home/End first/last · <b>C</b> cine ·
              <b> L</b> length · <b>A</b> angle · <b>O</b> ROI · <b>Esc</b> cancel tool ·
              <b> Ctrl+Z</b>/<b>Ctrl+Y</b> undo/redo · mouse wheel scrolls slices.
            </div>
          )}

          {measurements.length > 0 && (
            <div className="dv-measurements">
              <div className="dv-meas-head">
                <span>Measurements ({measurements.length})</span>
                <button className="btn btn-small" onClick={() => { setMeasurements([]); setRedo([]) }}>Clear all</button>
              </div>
              <ul className="dv-meas-list">
                {measurements.map((m) => (
                  <li key={m.id} className={m.sliceIndex === idx ? 'active' : ''}>
                    <button className="dv-meas-jump" onClick={() => setIdx(m.sliceIndex)}>
                      <span className="dv-meas-type">
                        {m.type === 'roi' ? (m.roiType === 'ellipse' ? '⬭' : '▭') : m.type === 'angle' ? '∠' : '📏'}
                      </span>
                      <span className="dv-meas-val">{fmtValue(m)}</span>
                      <span className="muted small">slice {m.sliceIndex + 1}</span>
                    </button>
                    <button className="btn btn-small" onClick={() => deleteMeasure(m.id)} aria-label="Delete measurement">✕</button>
                  </li>
                ))}
              </ul>
              <p className="muted small">
                Distances/angles use pixel spacing; ROI stats are on 16-bit intensity ({view.is_ct ? 'HU' : 'a.u.'}).
                Approximate — verify. Not a diagnosis.
              </p>
            </div>
          )}

          {rawData && (
            <div className="dv-raw">
              <RawWindowCanvas raw={rawData} />
            </div>
          )}

          <div className="dv-ai-rail">
            <div className="dv-ai-tabs seg" role="tablist" aria-label="AI channels">
              <button role="tab" aria-selected={aiTab === 'anatomy'} className={aiTab === 'anatomy' ? 'active' : ''}
                onClick={() => setAiTab('anatomy')}>Anatomy overlay</button>
              <button role="tab" aria-selected={aiTab === 'candidates'} className={aiTab === 'candidates' ? 'active' : ''}
                onClick={() => setAiTab('candidates')}>Candidate findings · research</button>
            </div>
            <p className="muted small">
              Two separate opt-in AI channels — both OFF by default. <b>Anatomy</b> labels organs/tissue only
              (no disease); <b>Candidates</b> are unvalidated research disease flags for confirmation.
            </p>
            {/* display:none (not unmount) so a running job/overlay survives a tab switch */}
            <div style={{ display: aiTab === 'anatomy' ? 'block' : 'none' }}>
              <AnatomyOverlayPanel modality={isCt ? 'CT' : 'MR'} files={files}
                seriesId={view?.series_id} ao={ao} setAo={setAo} />
            </div>
            <div style={{ display: aiTab === 'candidates' ? 'block' : 'none' }}>
              <CandidateFindings files={files} seriesId={view?.series_id} modality={isCt ? 'CT' : 'MR'}
                onConfirmedChange={setConfirmedCands} />
            </div>
          </div>

          <div className="dv-meta">
            <span><b>Modality</b> {view.modality}</span>
            <span><b>Window</b> {winText}</span>
            {view.sequence_label && <span><b>Sequence</b> {view.sequence_label} <em>(auto — verify)</em></span>}
            {spacing && <span><b>Pixel</b> {spacing}×{spacingCol} mm</span>}
            {view.slice_thickness_mm && <span><b>Thickness</b> {view.slice_thickness_mm} mm</span>}
            {view.body_part && <span><b>Body part</b> {view.body_part}</span>}
            <span><b>De-ID</b> {view.identifiers_removed} identifier{view.identifiers_removed === 1 ? '' : 's'} removed</span>
          </div>

          <p className="muted small dv-disclaimer">{view.disclaimer}</p>
          </div>

          <div style={{ display: viewMode === 'report' ? 'block' : 'none' }}>
            <CtReportPanel
              modality={isCt ? 'CT' : 'MR'}
              technique={[view.modality, view.sequence_label].filter(Boolean).join(' · ')}
              seriesId={view.series_id}
              measurements={measurements}
              confirmedCandidates={confirmedCands}
            />
          </div>
        </>
      )}
    </div>
  )
}
