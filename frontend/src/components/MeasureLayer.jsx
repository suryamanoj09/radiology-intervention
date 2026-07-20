import { useRef } from 'react'
import { fmtValue } from '../measureUtils.js'

// SVG measurement overlay over the viewer image. Renders the measurements on the
// current slice + the in-progress draft, and (when a tool is active) captures clicks,
// reporting them in ORIGINAL-raster pixel coords. pointer-events pass through when
// no tool is active so the image stays interactive.
const COLOR = '#ffe066'
const DRAFT = '#7fd7ff'

function Label({ x, y, text, fs, color = COLOR }) {
  return (
    <text x={x} y={y} fontSize={fs} fill={color} stroke="#000" strokeWidth={fs / 8}
      paintOrder="stroke" style={{ pointerEvents: 'none' }}>{text}</text>
  )
}

function Item({ m, fs }) {
  const p = m.points
  if (m.type === 'length' && p.length === 2) {
    const mx = (p[0][0] + p[1][0]) / 2, my = (p[0][1] + p[1][1]) / 2
    return (
      <g>
        <line x1={p[0][0]} y1={p[0][1]} x2={p[1][0]} y2={p[1][1]} stroke={COLOR} strokeWidth={fs / 7} />
        <circle cx={p[0][0]} cy={p[0][1]} r={fs / 4} fill={COLOR} />
        <circle cx={p[1][0]} cy={p[1][1]} r={fs / 4} fill={COLOR} />
        <Label x={mx + fs / 3} y={my - fs / 3} text={fmtValue(m)} fs={fs} />
      </g>
    )
  }
  if (m.type === 'angle' && p.length === 3) {
    return (
      <g>
        <polyline points={p.map((q) => q.join(',')).join(' ')} fill="none" stroke={COLOR} strokeWidth={fs / 7} />
        {p.map((q, i) => <circle key={i} cx={q[0]} cy={q[1]} r={fs / 4} fill={COLOR} />)}
        <Label x={p[1][0] + fs / 3} y={p[1][1] - fs / 3} text={fmtValue(m)} fs={fs} />
      </g>
    )
  }
  if (m.type === 'roi' && p.length === 2) {
    const x = Math.min(p[0][0], p[1][0]), y = Math.min(p[0][1], p[1][1])
    const w = Math.abs(p[1][0] - p[0][0]), h = Math.abs(p[1][1] - p[0][1])
    const common = { stroke: COLOR, strokeWidth: fs / 7, fill: 'rgba(255,224,102,.10)' }
    return (
      <g>
        {m.roiType === 'ellipse'
          ? <ellipse cx={x + w / 2} cy={y + h / 2} rx={w / 2} ry={h / 2} {...common} />
          : <rect x={x} y={y} width={w} height={h} {...common} />}
        <Label x={x} y={y - fs / 3} text={fmtValue(m)} fs={fs} />
      </g>
    )
  }
  return null
}

export default function MeasureLayer({ naturalW, naturalH, tool, measurements, draft, sliceIndex, onPoint }) {
  const ref = useRef(null)
  if (!naturalW || !naturalH) return null
  const active = tool !== 'none'
  const fs = Math.max(9, naturalW / 42)

  function click(e) {
    if (!active || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    if (!r.width || !r.height) return
    onPoint(((e.clientX - r.left) / r.width) * naturalW, ((e.clientY - r.top) / r.height) * naturalH)
  }

  const here = measurements.filter((m) => m.sliceIndex === sliceIndex)
  return (
    <svg ref={ref} viewBox={`0 0 ${naturalW} ${naturalH}`} preserveAspectRatio="none"
      onClick={click} aria-hidden="true"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%',
        pointerEvents: active ? 'auto' : 'none', cursor: active ? 'crosshair' : 'default' }}>
      {here.map((m) => <Item key={m.id} m={m} fs={fs} />)}
      {draft && draft.points.map((q, i) => <circle key={i} cx={q[0]} cy={q[1]} r={fs / 4} fill={DRAFT} />)}
      {draft && draft.points.length >= 2 && (
        <polyline points={draft.points.map((q) => q.join(',')).join(' ')} fill="none" stroke={DRAFT} strokeWidth={fs / 7} />
      )}
    </svg>
  )
}
