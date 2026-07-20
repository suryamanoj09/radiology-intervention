import { useEffect, useRef, useState } from 'react'

function metricsFor(behaviorCard, label) {
  if (!behaviorCard?.available || !behaviorCard.detection) return null
  const row = behaviorCard.detection.find((d) => d.pathology === label)
  if (!row || row.auroc == null) return null
  return row
}

// Per-label ECE (calibration error) from the behavior card, if measured.
function eceFor(behaviorCard, label) {
  const p = behaviorCard?.calibration?.per_class?.[label]
  return p?.ece != null ? p.ece : null
}

// Interpolate measured sens/spec at an arbitrary threshold from the per-label
// curve, so the slider shows the real trade-off at the value the clinician picks.
function sensSpecAt(behaviorCard, label, threshold) {
  const row = behaviorCard?.detection?.find((d) => d.pathology === label)
  if (!row?.curve?.length) return null
  let best = row.curve[0]
  for (const pt of row.curve) if (Math.abs(pt.t - threshold) < Math.abs(best.t - threshold)) best = pt
  return best.sens == null ? null : best
}

function band(p) {
  if (p >= 0.7) return 'high'
  if (p >= 0.5) return 'mid'
  return 'low'
}

const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x))
const MAX_ZOOM = 6

// Settings pref: 'Auto-show Grad-CAM'. When on, a freshly opened study reveals the
// attention overlay immediately instead of starting Off. Read directly from
// localStorage (no import coupling); defaults false to match SettingsPage.
function autoHeatmapPref() {
  try {
    const v = localStorage.getItem('radassist_pref_auto_heatmap')
    return v === '1' || v === 'true'
  } catch {
    return false
  }
}

// Per-finding contour colors (also used for the readout swatch).
const REGION_COLORS = ['#4da3ff', '#ffb454', '#57c98b', '#c98bff', '#ff8fb0', '#5ad1d1']

// Heatmap-state display so a blank/soft map is NEVER ambiguous. Every flagged
// finding shows exactly which of these it is (see backend Finding.heatmap_state).
const STATE_INFO = {
  localized: { label: 'focal region', tone: 'ok' },
  diffuse: { label: 'diffuse / non-localizing', tone: 'warn' },
  suppressed: { label: 'suppressed — off expected anatomy', tone: 'warn' },
  none: { label: 'no map (attention was empty)', tone: 'muted' },
  not_localized: { label: 'map not computed', tone: 'muted' },
  abstained: { label: 'not scored (out-of-distribution)', tone: 'muted' },
  error: { label: 'map unavailable (error)', tone: 'warn' },
  unknown: { label: '—', tone: 'muted' },
}

const EST_TOOLTIP =
  'Estimated from the region of model attention, not a lesion boundary — confirm with the caliper.'

// attention_contour may arrive as [[x,y],...] or [{x,y},...]; normalize to an
// SVG points string in natural-image coordinates. Returns null if unusable.
function contourPoints(contour) {
  if (!Array.isArray(contour) || contour.length < 3) return null
  const pts = contour
    .map((pt) => (Array.isArray(pt) ? pt : pt && typeof pt === 'object' ? [pt.x, pt.y] : null))
    .filter((p) => p && p[0] != null && p[1] != null)
  if (pts.length < 3) return null
  return pts.map((p) => `${p[0]},${p[1]}`).join(' ')
}

// Size estimate string for a region, each figure explicitly labeled an estimate.
function estFor(f, spacing) {
  if (f && f.est_max_2d_mm != null) {
    let t = `≈ ${Number(f.est_max_2d_mm).toFixed(1)} mm (est.)`
    if (f.est_area_mm2 != null) t += ` · area ≈ ${Number(f.est_area_mm2).toFixed(0)} mm² (est.)`
    return t
  }
  return spacing ? 'size needs caliper' : 'size needs DICOM or caliper'
}

export default function Viewer({ analysis, behaviorCard, focusedFinding, onFocusFinding }) {
  const flagged = analysis.findings.filter((f) => f.flagged)
  const regions = flagged.filter((f) => f.heatmap_url) // per-finding attention overlays
  // Map-status covers every finding that carries a localization state — flagged
  // findings AND those the anatomy/background gate SUPPRESSED (flagged is now false
  // on those, but the reader must still see they were suppressed and why).
  const mapStatus = analysis.findings.filter((f) => f.heatmap_state)

  const hasHeat = !!(analysis.heatmap_url || regions.some((r) => r.heatmap_url))
  const hasContours = regions.some((r) => contourPoints(r.attention_contour))

  const [threshold, setThreshold] = useState(0.5)
  // Overlay starts Off unless the 'Auto-show Grad-CAM' pref is on, in which case a
  // new study opens with the attention overlay revealed (heatmap preferred, contour
  // as fallback). The user can still switch it Off — this only sets the initial mode.
  const [overlayMode, setOverlayMode] = useState(() =>
    autoHeatmapPref() ? (hasHeat ? 'heatmap' : hasContours ? 'contour' : 'off') : 'off',
  )
  const [opacity, setOpacity] = useState(0.7) // applied to the overlay layer (0..1)
  const [selected, setSelected] = useState(
    () => regions.find((r) => r.label === analysis.top_finding)?.label || regions[0]?.label || null,
  )
  const [hovered, setHovered] = useState(null) // label of hovered row/region
  const [measuring, setMeasuring] = useState(false)
  const [points, setPoints] = useState([]) // natural-image coords only
  const [dims, setDims] = useState({ w: 0, h: 0 })
  const [view, setView] = useState({ scale: 1, tx: 0, ty: 0 }) // zoom/pan transform
  // Window/level approximation (brightness/contrast/invert on the rendered 8-bit
  // image). True HU-based WW/WL needs raw DICOM pixels (roadmap); this gives the
  // contrast control radiologists rely on for the demo.
  const [wl, setWl] = useState({ b: 1, c: 1, invert: false })
  // Caliper display unit. Defaults to mm when DICOM pixel spacing is known, else px.
  const [unit, setUnit] = useState(() => (analysis.pixel_spacing_mm ? 'mm' : 'px'))

  const imgRef = useRef(null)
  const stageRef = useRef(null)
  const dragRef = useRef(null)
  const cardRef = useRef(null)
  const [isFull, setIsFull] = useState(false)

  // Fullscreen the VIEWER CARD (which contains the stage + a pinned disclaimer +
  // model badge), never just the canvas — so the regulatory framing can't be
  // stripped at the moment the clinician is looking hardest. Modals/toasts must
  // render inside this subtree or they vanish in fullscreen.
  function toggleFullscreen() {
    const el = cardRef.current
    if (!el) return
    if (!document.fullscreenElement) {
      const p = el.requestFullscreen?.()
      if (p && p.catch) p.catch(() => setIsFull(false))  // can be silently rejected
    } else {
      document.exitFullscreen?.()
    }
  }
  useEffect(() => {
    const onFs = () => setIsFull(document.fullscreenElement === cardRef.current)
    document.addEventListener('fullscreenchange', onFs)
    const onKey = (e) => {
      if (e.key === 'f' || e.key === 'F') {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
        toggleFullscreen()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('fullscreenchange', onFs); document.removeEventListener('keydown', onKey) }
  }, [])

  // Grounded hover: when another panel (e.g. a report explanation card) focuses a
  // finding, highlight its region here.
  useEffect(() => {
    if (focusedFinding && regions.some((r) => r.label === focusedFinding)) {
      setHovered(focusedFinding)
      setSelected(focusedFinding)
    } else if (!focusedFinding) {
      setHovered(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedFinding])

  const spacing = analysis.pixel_spacing_mm            // row spacing (mm/px)
  const spacingCol = analysis.pixel_spacing_col_mm || spacing // col spacing; square-pixel fallback
  const active = regions.find((r) => r.label === selected) || regions[0] || null
  // Progressive enhancement (T7): a background res512 job may replace a finding's
  // 224 map with a sharper 16x16 one. Prefer the hi-res URL when it has arrived.
  const [hires, setHires] = useState({})
  const [sharpening, setSharpening] = useState(false)
  useEffect(() => {
    if (!analysis?.hires_pending || !analysis.image_id) return
    setSharpening(true)
    let alive = true
    const poll = async () => {
      try {
        const j = await (await fetch(`/api/localize-hires/${analysis.image_id}`)).json()
        if (!alive) return
        if (j.status === 'done') {
          const m = {}
          for (const f of j.findings || []) m[f.label] = f.heatmap_url
          setHires(m); setSharpening(false)
        } else if (j.status === 'pending' || j.status === 'unknown') {
          setTimeout(poll, 2500)
        } else { setSharpening(false) }
      } catch { setSharpening(false) }
    }
    const t = setTimeout(poll, 2000)
    return () => { alive = false; clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis?.image_id, analysis?.hires_pending])
  const overlayUrl = (active && hires[active.label]) || active?.heatmap_url || analysis.heatmap_url
  const displayRegion = regions.find((r) => r.label === hovered) || active
  const colorFor = (label) => REGION_COLORS[regions.findIndex((r) => r.label === label) % REGION_COLORS.length]

  // Wheel-zoom (non-passive so we can preventDefault the page scroll) about the cursor.
  useEffect(() => {
    const stage = stageRef.current
    if (!stage) return
    const onWheel = (e) => {
      e.preventDefault()
      const rect = stage.getBoundingClientRect()
      const cx = e.clientX - rect.left
      const cy = e.clientY - rect.top
      const W = stage.clientWidth
      const H = stage.clientHeight
      setView((v) => {
        const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
        const s2 = clamp(v.scale * factor, 1, MAX_ZOOM)
        if (s2 === 1) return { scale: 1, tx: 0, ty: 0 }
        // Keep the point under the cursor fixed (transform-origin 0 0).
        let tx = cx - (s2 / v.scale) * (cx - v.tx)
        let ty = cy - (s2 / v.scale) * (cy - v.ty)
        return {
          scale: s2,
          tx: clamp(tx, W * (1 - s2), 0),
          ty: clamp(ty, H * (1 - s2), 0),
        }
      })
    }
    stage.addEventListener('wheel', onWheel, { passive: false })
    return () => stage.removeEventListener('wheel', onWheel)
    // Re-bind across the fullscreen transition so wheel-zoom is never left bound to
    // a stale element / passive routing inside the fullscreened subtree (T5).
  }, [isFull])

  function onStageMouseDown(e) {
    if (measuring || view.scale <= 1) return // caliper clicks / no pan at 1x
    dragRef.current = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty }
  }
  function onStageMouseMove(e) {
    const d = dragRef.current
    if (!d) return
    const stage = stageRef.current
    const W = stage.clientWidth
    const H = stage.clientHeight
    const s = view.scale
    setView((v) => ({
      ...v,
      tx: clamp(d.tx + (e.clientX - d.x), W * (1 - s), 0),
      ty: clamp(d.ty + (e.clientY - d.y), H * (1 - s), 0),
    }))
  }
  function endDrag() {
    dragRef.current = null
  }
  function resetView() {
    setView({ scale: 1, tx: 0, ty: 0 })
  }

  // Caliper: map screen click to natural-image coords. getBoundingClientRect on the
  // image already reflects the zoom/pan transform, so this stays correct under zoom.
  function handleClick(e) {
    if (!measuring || !imgRef.current) return
    const img = imgRef.current
    if (!img.naturalWidth) return
    const rect = img.getBoundingClientRect()
    const p = {
      nx: ((e.clientX - rect.left) / rect.width) * img.naturalWidth,
      ny: ((e.clientY - rect.top) / rect.height) * img.naturalHeight,
    }
    setPoints((prev) => (prev.length >= 2 ? [p] : [...prev, p]))
  }

  let measureText = null
  if (points.length === 2) {
    const dxPx = points[1].nx - points[0].nx
    const dyPx = points[1].ny - points[0].ny
    const distPx = Math.hypot(dxPx, dyPx)
    // Scale each axis by its OWN spacing so a diagonal on anisotropic pixels
    // (row ≠ col spacing — common on CT) is correct, not row-spacing-times-hypot.
    const distMm = Math.hypot(dxPx * spacingCol, dyPx * spacing)
    measureText = (unit === 'mm' && spacing)
      ? `${distMm.toFixed(1)} mm`
      : `${distPx.toFixed(0)} px${spacing ? '' : ' — mm needs DICOM'}`
  }

  const WL_PRESETS = {
    Default: { b: 1, c: 1 }, Lung: { b: 1.15, c: 1.5 },
    Bone: { b: 0.9, c: 1.7 }, 'Soft tissue': { b: 1.1, c: 1.2 },
  }
  const imgFilter =
    `brightness(${wl.b}) contrast(${wl.c})${wl.invert ? ' invert(1)' : ''}`

  const stageClass =
    'viewer-stage' +
    (measuring ? ' crosshair' : view.scale > 1 ? ' pannable' : '')

  return (
    <div className={`card viewer-card ${isFull ? 'viewer-full' : ''}`} ref={cardRef}>
      {/* Pinned safety framing — INSIDE the fullscreen subtree so it never vanishes
          when the viewer is fullscreened. */}
      <div className="viewer-pinned" aria-hidden="false">
        <span className="vp-badge">AI-generated · region of model attention — not a diagnosis</span>
        <span className="vp-model muted small">
          {behaviorCard?.model || 'TorchXRayVision DenseNet-121'} · human sign-off required
        </span>
      </div>
      <div className="viewer-toolbar">
        <h3>Viewer</h3>
        <div className="toolbar-actions">
          <button className="btn btn-small" onClick={toggleFullscreen}
            title="Fullscreen the viewer (F). The disclaimer + model badge stay pinned.">
            {isFull ? '⤢ Exit fullscreen' : '⤢ Fullscreen'}
          </button>
          <div className="seg" role="group" aria-label="Overlay mode">
            <button
              className={overlayMode === 'off' ? 'active' : ''}
              aria-pressed={overlayMode === 'off'}
              onClick={() => setOverlayMode('off')}
            >
              Off
            </button>
            <button
              className={overlayMode === 'heatmap' ? 'active' : ''}
              aria-pressed={overlayMode === 'heatmap'}
              disabled={!hasHeat}
              title={hasHeat ? 'Region of model attention (heatmap)' : 'No heatmap for this study'}
              onClick={() => setOverlayMode('heatmap')}
            >
              Heatmap
            </button>
            <button
              className={overlayMode === 'contour' ? 'active' : ''}
              aria-pressed={overlayMode === 'contour'}
              disabled={!hasContours}
              title={hasContours ? 'Attention contour outline'
                : 'Crisp contours need the high-resolution 16×16 localizer (off by default); '
                  + 'at the 7×7 default a crisp outline would overclaim, so only a soft heatmap is shown'}
              onClick={() => setOverlayMode('contour')}
            >
              Contour
            </button>
          </div>
          {overlayMode !== 'off' && (
            <label className="opacity-slider">
              Opacity {Math.round(opacity * 100)}%
              <input
                type="range" min="0" max="1" step="0.05" value={opacity}
                onChange={(e) => setOpacity(parseFloat(e.target.value))}
                aria-label="Overlay opacity"
              />
            </label>
          )}
          <button
            className={measuring ? 'btn btn-small active' : 'btn btn-small'}
            aria-pressed={measuring}
            onClick={() => { setMeasuring(!measuring); setPoints([]) }}
          >
            📏 Caliper {measuring ? 'on' : 'off'}
          </button>
          <div className="seg unit-seg" role="group" aria-label="Caliper units">
            <button className={unit === 'mm' ? 'active' : ''} disabled={!spacing}
              title={spacing ? 'Millimetres (from DICOM pixel spacing)' : 'mm needs a DICOM with pixel spacing'}
              onClick={() => setUnit('mm')}>mm</button>
            <button className={unit === 'px' ? 'active' : ''} onClick={() => setUnit('px')}>px</button>
          </div>
        </div>
      </div>

      {/* Display presets on the 8-bit rendered image. These are brightness/contrast
          filters, NOT true window/level: clipped data can't be recovered from an
          8-bit PNG, so we do not call them "windowing" (that clinical term implies
          re-windowing the raw pixels, which needs the DICOM data). */}
      <div className="wl-bar" role="group" aria-label="Display brightness / contrast presets">
        <span className="muted small" title="Brightness/contrast on the 8-bit image — not true HU windowing, which needs raw DICOM pixels.">Display (8-bit aid):</span>
        <div className="seg">
          {Object.keys(WL_PRESETS).map((name) => (
            <button key={name}
              className={wl.b === WL_PRESETS[name].b && wl.c === WL_PRESETS[name].c ? 'active' : ''}
              onClick={() => setWl((w) => ({ ...w, ...WL_PRESETS[name] }))}
            >{name}</button>
          ))}
        </div>
        <label className="wl-slider">B<input type="range" min="0.4" max="2" step="0.05"
          value={wl.b} onChange={(e) => setWl((w) => ({ ...w, b: parseFloat(e.target.value) }))} /></label>
        <label className="wl-slider">C<input type="range" min="0.4" max="2.2" step="0.05"
          value={wl.c} onChange={(e) => setWl((w) => ({ ...w, c: parseFloat(e.target.value) }))} /></label>
        <button className={wl.invert ? 'btn btn-small active' : 'btn btn-small'}
          aria-pressed={wl.invert} onClick={() => setWl((w) => ({ ...w, invert: !w.invert }))}>
          Invert
        </button>
      </div>

      {overlayMode !== 'off' && regions.length > 1 && (
        <div className="region-picker" role="group" aria-label="Choose which finding's region to view">
          <span className="muted small">Region for:</span>
          {regions.map((r) => (
            <button
              key={r.label}
              className={selected === r.label ? 'chip region active' : 'chip region'}
              aria-pressed={selected === r.label}
              onMouseEnter={() => setHovered(r.label)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => { setSelected(r.label); onFocusFinding?.(r.label) }}
            >
              {r.label}
              {r.calibration_state === 'calibrated' || r.calibrated_probability != null
                ? ` · ${Math.round((r.calibrated_probability ?? r.probability) * 100)}%`
                : ''}
            </button>
          ))}
        </div>
      )}

      <div
        ref={stageRef}
        className={stageClass}
        // In fullscreen, cap the stage WIDTH to the film's aspect ratio so the whole
        // film fits the viewport height. All overlay layers are % of the stage, so
        // they stay aligned. (Alignment is why we don't object-fit the img directly.)
        style={isFull && dims.w ? { maxWidth: `calc(80vh * ${dims.w / dims.h})`, margin: '0 auto' } : undefined}
        onClick={handleClick}
        onMouseDown={onStageMouseDown}
        onMouseMove={onStageMouseMove}
        onMouseUp={endDrag}
        onMouseLeave={endDrag}
      >
        <div
          className="stage-inner"
          style={{ transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})` }}
        >
          <img
            ref={imgRef}
            className="base"
            src={analysis.image_url}
            alt={`Chest radiograph${active ? `, model-flagged ${active.label}` : ''}`}
            draggable={false}
            style={{ filter: imgFilter }}
            onLoad={(e) => setDims({ w: e.target.naturalWidth, h: e.target.naturalHeight })}
          />
          {overlayMode === 'heatmap' && overlayUrl && (
            <img className="heat-layer" src={overlayUrl} alt="" draggable={false} style={{ opacity }} />
          )}
          {/* viewBox in natural-image units => markers & contours scale with the image */}
          <svg
            className="measure-overlay"
            viewBox={dims.w ? `0 0 ${dims.w} ${dims.h}` : undefined}
            preserveAspectRatio="none"
          >
            {overlayMode === 'contour' &&
              regions.map((r) => {
                const pts = contourPoints(r.attention_contour)
                if (!pts) return null
                const emphasized = displayRegion?.label === r.label
                const c = colorFor(r.label)
                return (
                  <polygon
                    key={r.label}
                    className="contour-poly"
                    points={pts}
                    stroke={c}
                    fill={c}
                    strokeWidth={Math.max(2, dims.w / 300) * (emphasized ? 2.6 : 0.8)}
                    strokeOpacity={emphasized ? Math.min(1, opacity + 0.25) : opacity * 0.4}
                    fillOpacity={emphasized ? Math.min(0.5, opacity * 0.45) : opacity * 0.05}
                    onMouseEnter={() => { setHovered(r.label); setSelected(r.label) }}
                    onMouseLeave={() => setHovered(null)}
                  />
                )
              })}
            {points.map((p, i) => (
              <circle key={i} cx={p.nx} cy={p.ny} r={Math.max(3, dims.w / 120)} />
            ))}
            {points.length === 2 && (
              <line x1={points[0].nx} y1={points[0].ny} x2={points[1].nx} y2={points[1].ny}
                strokeWidth={Math.max(2, dims.w / 250)} />
            )}
          </svg>
        </div>

        {measureText && <div className="measure-label">{measureText}</div>}
        <div className="stage-controls">
          <span className="stage-zoom">{view.scale.toFixed(1)}×</span>
          {view.scale > 1 && (
            <button className="stage-reset" onClick={resetView}>Reset view</button>
          )}
        </div>
      </div>

      {measuring ? (
        <p className="muted small">
          Click two points to measure ({unit}).{spacing ? '' : ' mm needs a DICOM with pixel spacing.'}
        </p>
      ) : (
        <p className="muted small">Scroll to zoom (up to {MAX_ZOOM}×); drag to pan when zoomed.</p>
      )}

      {sharpening && (
        <p className="muted small sharpening-chip">✨ Sharpening the attention map (16×16 localizer)…</p>
      )}

      {overlayMode === 'heatmap' && overlayUrl && (
        <div className="heat-legend" aria-hidden="true">
          <span className="muted small">Model attention:</span>
          <span className="legend-label">low</span>
          <span className="legend-gradient" />
          <span className="legend-label">high</span>
          <span className="muted small">· not a lesion boundary</span>
        </div>
      )}

      {overlayMode !== 'off' && displayRegion && (
        <div className="region-readout">
          <span className="rr-swatch" style={{ background: colorFor(displayRegion.label) }} />
          <span className="rr-label">{displayRegion.label}</span>
          <span className="rr-size" title={EST_TOOLTIP}>{estFor(displayRegion, spacing)}</span>
          <span className="rr-hint">
            {displayRegion.heatmap_caption || displayRegion.size_note || 'Region of model attention — not a lesion boundary. Confirm any size with the caliper.'}
          </span>
        </div>
      )}

      {/* Attention-map status for EVERY flagged/suppressed finding, so the reader
          can always tell a focal map from diffuse from suppressed from empty from
          not-computed — never a silent blank. */}
      {mapStatus.length > 0 && (
        <div className="map-status">
          <span className="muted small">Attention map per finding:</span>
          <ul className="map-status-list">
            {mapStatus.map((f) => {
              const s = STATE_INFO[f.heatmap_state] || STATE_INFO.unknown
              const hasMap = !!f.heatmap_url
              return (
                <li
                  key={f.label}
                  className={`ms-item ms-${s.tone} ${hasMap ? 'ms-clickable' : ''} ${hovered === f.label ? 'ms-hovered' : ''}`}
                  title={f.heatmap_caption || ''}
                  onMouseEnter={() => { if (hasMap) { setHovered(f.label); setSelected(f.label); onFocusFinding?.(f.label) } }}
                  onMouseLeave={() => { if (hasMap) { setHovered(null); onFocusFinding?.(null) } }}
                  onClick={() => { if (hasMap) { setOverlayMode(hasHeat ? 'heatmap' : 'contour'); setSelected(f.label) } }}
                >
                  <span className="ms-dot" aria-hidden="true" />
                  <span className="ms-label">{f.label}</span>
                  {f.calibration_state === 'calibrated' || f.calibrated_probability != null ? (
                    <span className="ms-pct">{Math.round((f.calibrated_probability ?? f.probability) * 100)}%</span>
                  ) : (
                    <span className="ms-pct uncal" title="Not calibrated — score is not a probability.">n/c</span>
                  )}
                  <span className="ms-state">{s.label}</span>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      <div className="conf-head">
        <h4>Model confidence per pathology</h4>
        <label className="conf-slider">
          Show ≥ {Math.round(threshold * 100)}%
          <input
            type="range" min="0" max="0.95" step="0.05" value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
          />
        </label>
      </div>
      {(() => {
        // Live sens/spec of the TOP finding at the chosen threshold — so the knob's
        // consequences are visible, not invisible (and on a miscalibrated scale).
        const top = analysis.findings[0]
        const ss = top && threshold > 0 ? sensSpecAt(behaviorCard, top.label, threshold) : null
        return ss ? (
          <p className="muted small ss-live">
            At {Math.round(threshold * 100)}% for {top.label} (measured on NIH):
            sensitivity {ss.sens ?? '—'} · specificity {ss.spec ?? '—'}.
            <span className="muted"> Higher threshold → fewer false alarms, more misses.</span>
          </p>
        ) : null
      })()}
      <div className="findings-bars">
        {analysis.findings
          .filter((f) => f.probability >= threshold)
          .slice(0, 10)
          .map((f) => {
            const m = metricsFor(behaviorCard, f.label)
            const isRegion = regions.some((r) => r.label === f.label)
            return (
              <div
                key={f.label}
                className={`bar-row ${isRegion ? 'linked' : ''} ${hovered === f.label ? 'hovered' : ''}`}
                onMouseEnter={() => { setHovered(f.label); if (isRegion) { setSelected(f.label); onFocusFinding?.(f.label) } }}
                onMouseLeave={() => { setHovered(null); if (isRegion) onFocusFinding?.(null) }}
                title={isRegion ? estFor(f, spacing) + ' — ' + EST_TOOLTIP : undefined}
              >
                <span className="bar-label">{f.label}</span>
                <div className="bar-track">
                  <div
                    className={`bar-fill band-${band(f.probability)} ${f.urgent ? 'urgent' : ''}`}
                    style={{ width: `${Math.round(f.probability * 100)}%` }}
                  />
                </div>
                <div className="bar-meta">
                {f.calibration_state === 'calibrated' || f.calibrated_probability != null ? (
                  <>
                    <span className="bar-val" title="Raw ranking score (drives the flag). Not a probability.">{Math.round(f.probability * 100)}%</span>
                    {f.calibrated_probability != null && (
                      <span className="cal-val" title="Calibrated P(disease) from the isotonic map — the honest number; the raw score is overconfident.">
                        P≈{Math.round(f.calibrated_probability * 100)}%
                      </span>
                    )}
                  </>
                ) : (
                  <span className="uncal-chip"
                    title="No calibration for this label on our validation set — the score is NOT interpretable as a probability. Read the image independently.">
                    not calibrated
                  </span>
                )}
                {m && (
                  <span
                    className={`acc-chip ${m.reliable ? '' : 'acc-weak'}`}
                    title={`Measured on ${m.n} NIH images (${m.positives} positive).`
                      + (m.reliable ? '' : ' Too few positives — indicative only.')}
                  >
                    NIH AUROC {m.auroc}{m.reliable ? '' : ' ⚠'}
                  </span>
                )}
                {(() => {
                  const ece = eceFor(behaviorCard, f.label)
                  if (ece == null) return null
                  const poor = ece >= 0.15
                  return (
                    <span className={`ece-chip ${poor ? 'ece-poor' : ''}`}
                      title={poor
                        ? `Poorly calibrated (ECE ${ece}) — the raw % is NOT a trustworthy probability for this label; lean on the calibrated P and disposition.`
                        : `Per-label calibration error ${ece} (0 = perfect).`}>
                      {poor ? '⚠ ' : ''}ECE {ece}
                    </span>
                  )
                })()}
                {f.flagged && f.disposition && (
                  <span
                    className={`disp-chip ${/urgent/i.test(f.disposition) ? 'disp-urgent'
                      : /correlation/i.test(f.disposition) ? 'disp-priority'
                      : /borderline/i.test(f.disposition) ? 'disp-borderline' : ''}`}
                    title="Suggested disposition — the confidence→action bridge, not a diagnosis"
                  >
                    {f.disposition}
                  </span>
                )}
                {f.reliability_state === 'not_reliably_measured' && (
                  <span
                    className="reliab-chip"
                    title="This label is NOT reliably measured on our validation set (too few positives and/or near-chance AUROC). Its score is advisory — it cannot exclude disease and does not drive urgent triage. Read the image independently."
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                      fontSize: 11,
                      fontWeight: 600,
                      lineHeight: 1.3,
                      padding: '2px 7px',
                      borderRadius: 99,
                      color: 'var(--warn)',
                      background: 'color-mix(in srgb, var(--warn) 12%, transparent)',
                      border: '1px solid color-mix(in srgb, var(--warn) 34%, transparent)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    cannot exclude · not reliably measured
                  </span>
                )}
                </div>
              </div>
            )
          })}
      </div>
      <p className="muted small">
        {flagged.length
          ? `${flagged.length} finding(s) above the flag threshold — signals for review, not diagnoses.`
          : 'No finding exceeded the flag threshold.'}
        {behaviorCard?.available
          ? ' AUROC chips are measured on held-out NIH images (in-distribution / optimistic).'
          : ''}
      </p>
      {behaviorCard?.calibration?.overall?.ece != null && (
        <p className="muted small calib-note">
          ⓘ Confidence is a ranking score at the operating point, <strong>not</strong> a
          calibrated probability of disease (measured ECE {behaviorCard.calibration.overall.ece} —
          the model is overconfident; e.g. the 50–60% band was positive only ~8% of the time).
          Use the disposition, not the raw %.
        </p>
      )}
    </div>
  )
}
