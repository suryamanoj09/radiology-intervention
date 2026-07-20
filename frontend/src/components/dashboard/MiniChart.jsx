// Dependency-free, CSP-safe inline-SVG charts for the console dashboard.
// NO chart library — everything is hand-drawn SVG that references the theme CSS
// vars, so both charts recolour automatically in light/dark. Honesty note: these
// render REAL local-session counts passed in by the Dashboard; when there is no
// data the Dashboard shows an empty state instead of mounting these.
//
// Power-BI-style interactivity is hand-rolled: pointer hit-testing, a crosshair +
// floating tooltip on the area chart, and per-segment raise/brighten + tooltip on
// the donut. All motion is disabled under prefers-reduced-motion. Tooltips are
// decorative (aria-hidden) — the honest readout also lives in role="img" labels.
import { useEffect, useRef, useState } from 'react'

// Respect the OS "reduce motion" setting for every transition below.
function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false
  )
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const on = () => setReduced(mq.matches)
    mq.addEventListener ? mq.addEventListener('change', on) : mq.addListener(on)
    return () => (mq.removeEventListener ? mq.removeEventListener('change', on) : mq.removeListener(on))
  }, [])
  return reduced
}

const tooltipStyle = {
  position: 'absolute', zIndex: 3, pointerEvents: 'none', whiteSpace: 'nowrap',
  padding: '6px 9px', borderRadius: 8, fontSize: 12, lineHeight: 1.35,
  background: 'var(--surface)', color: 'var(--ink)',
  border: '1px solid var(--border-2)', boxShadow: 'var(--shadow-lg)',
  fontFamily: 'var(--font-sans)',
}

// ---- Area chart: studies read per day -------------------------------------
// `data` is [{ label, count }] (oldest→newest). Faithful to design lines 626-634
// (viewBox 0 0 320 130, dashed gridlines, gradient fill, marker on the last day).
// Now hit-tests the nearest day on pointer move and shows a crosshair + tooltip.
export default function AreaChart({ data = [], height = 180, gradientId = 'dashAreaG', ariaLabel }) {
  const W = 320, H = 130
  const padL = 12, padR = 20
  const top = 31, bot = 120
  const n = data.length
  const max = Math.max(1, ...data.map((d) => d.count || 0))
  const xAt = (i) => (n <= 1 ? padL : padL + (i * (W - padL - padR)) / (n - 1))
  const yAt = (v) => bot - ((v || 0) / max) * (bot - top)

  const pts = data.map((d, i) => [xAt(i), yAt(d.count)])
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const area = pts.length
    ? `${line} L${xAt(n - 1).toFixed(1)},${bot} L${padL},${bot} Z`
    : ''
  const last = pts[pts.length - 1]

  const reduced = usePrefersReducedMotion()
  const svgRef = useRef(null)
  const [hover, setHover] = useState(null) // index or null

  // Map the pointer's x to the nearest data point using the SVG's own box. The
  // viewBox stretches linearly (preserveAspectRatio="none"), so screen-fraction
  // maps 1:1 to viewBox-fraction, and each point sits at xAt(i)/W of the width.
  function onMove(e) {
    if (!n) return
    const rect = (svgRef.current || e.currentTarget).getBoundingClientRect()
    if (!rect.width) return
    const fx = (e.clientX - rect.left) / rect.width
    let best = 0, bestD = Infinity
    for (let i = 0; i < n; i++) {
      const d = Math.abs(fx - xAt(i) / W)
      if (d < bestD) { bestD = d; best = i }
    }
    setHover(best)
  }

  const hv = hover != null && data[hover] ? data[hover] : null
  const hx = hv ? xAt(hover) : 0
  const hy = hv ? yAt(hv.count) : 0
  const leftPct = hv ? (hx / W) * 100 : 0
  // Keep the tooltip on-screen at the edges.
  const tx = leftPct < 15 ? '0%' : leftPct > 85 ? '-100%' : '-50%'

  return (
    <div>
      <div style={{ position: 'relative', marginTop: 14 }}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          style={{ width: '100%', height, display: 'block', overflow: 'visible' }}
          preserveAspectRatio="none"
          role="img"
          aria-label={
            ariaLabel ||
            `Studies read per day, last ${n} days` +
              (hv ? `; ${hv.label}: ${hv.count} ${hv.count === 1 ? 'study' : 'studies'}` : '')
          }
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="var(--primary)" stopOpacity="0.28" />
              <stop offset="1" stopColor="var(--primary)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <line x1="0" y1="31" x2={W} y2="31" stroke="var(--border)" strokeWidth="1" strokeDasharray="3 4" />
          <line x1="0" y1="73" x2={W} y2="73" stroke="var(--border)" strokeWidth="1" strokeDasharray="3 4" />
          {area && <path d={area} fill={`url(#${gradientId})`} />}
          {line && (
            <path d={line} fill="none" stroke="var(--primary)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          )}
          {last && (
            <circle cx={last[0]} cy={last[1]} r="4.5" fill="var(--primary)" stroke="var(--surface)" strokeWidth="2.5" />
          )}
          {/* Crosshair + highlighted point for the hovered day */}
          {hv && (
            <g aria-hidden="true">
              <line
                x1={hx} y1={top - 6} x2={hx} y2={bot}
                stroke="var(--primary)" strokeWidth="1" strokeDasharray="2 3" strokeOpacity="0.7"
              />
              <circle cx={hx} cy={hy} r="7" fill="var(--primary)" fillOpacity="0.16" />
              <circle cx={hx} cy={hy} r="4.5" fill="var(--primary)" stroke="var(--surface)" strokeWidth="2.5" />
            </g>
          )}
        </svg>
        {hv && (
          <div
            aria-hidden="true"
            style={{
              ...tooltipStyle,
              left: `${leftPct}%`,
              top: (hy / H) * height,
              transform: `translate(${tx}, calc(-100% - 10px))`,
              transition: reduced ? 'none' : 'left 90ms ease, top 90ms ease',
            }}
          >
            <b style={{ fontFamily: 'var(--font-mono)' }}>{hv.label}</b>
            {' — '}
            {hv.count} {hv.count === 1 ? 'study' : 'studies'}
          </div>
        )}
      </div>
      <div
        style={{
          display: 'flex', justifyContent: 'space-between', fontSize: 11,
          color: 'var(--faint)', fontFamily: 'var(--font-mono)', marginTop: 4,
        }}
      >
        {data.map((d, i) => (
          <span
            key={i}
            style={{
              color: hover === i ? 'var(--primary)' : 'var(--faint)',
              fontWeight: hover === i ? 700 : 400,
              transition: reduced ? 'none' : 'color 90ms ease',
            }}
          >
            {d.label}
          </span>
        ))}
      </div>
    </div>
  )
}

// ---- Donut: modality mix ---------------------------------------------------
// `segments` is [{ label, value, color }]; `centerValue`/`centerLabel` fill the
// hub. Faithful to design lines 640-653 (r=15.9, 7px stroke, offset-25 start).
// Hovering a segment (or its legend row) raises + brightens it and shows a
// tooltip; a small legend sits alongside. Honest "this session" framing kept.
export function Donut({
  segments = [], centerValue, centerLabel = 'this session', size = 118,
  showLegend = true, note,
}) {
  const reduced = usePrefersReducedMotion()
  const [hover, setHover] = useState(null) // segment index or null
  const total = segments.reduce((a, s) => a + (s.value || 0), 0)
  let acc = 0
  const arcs = segments.map((s, i) => {
    const pct = total ? (s.value / total) * 100 : 0
    const offset = 25 - acc
    acc += pct
    return { key: i, label: s.label, value: s.value || 0, color: s.color, pct, offset }
  })
  const hv = hover != null && arcs[hover] ? arcs[hover] : null
  const pctLabel = (a) => `${Math.round(a.pct)}%`
  const countLabel = (a) => `${a.value} ${a.value === 1 ? 'study' : 'studies'}`

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
      <div style={{ position: 'relative', width: size, flex: 'none' }}>
        <svg
          width={size} height={size} viewBox="0 0 42 42" role="img"
          aria-label={`Modality mix this session: ${arcs.map((a) => `${a.label} ${pctLabel(a)} (${countLabel(a)})`).join(', ')}`}
        >
          <circle cx="21" cy="21" r="15.9" fill="none" stroke="var(--surface-3)" strokeWidth="7" />
          {arcs.map((a, i) => {
            const on = hover === i
            const dim = hover != null && !on
            return (
              <circle
                key={a.key} cx="21" cy="21" r="15.9" fill="none"
                stroke={a.color} strokeWidth={on ? 8.4 : 7}
                strokeDasharray={`${a.pct.toFixed(2)} ${(100 - a.pct).toFixed(2)}`}
                strokeDashoffset={a.offset.toFixed(2)} strokeLinecap="round"
                opacity={dim ? 0.75 : 1}
                style={{
                  filter: on ? 'brightness(1.12)' : 'none',
                  cursor: 'pointer',
                  transition: reduced ? 'none' : 'stroke-width 120ms ease, opacity 120ms ease',
                }}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover((h) => (h === i ? null : h))}
              />
            )
          })}
          <text x="21" y="20" textAnchor="middle" fontSize="7" fontWeight="700" fill="var(--ink)" fontFamily="var(--font-mono)">
            {centerValue != null ? centerValue : total}
          </text>
          <text x="21" y="26" textAnchor="middle" fontSize="3.2" fill="var(--muted)" fontFamily="var(--font-sans)">
            {centerLabel}
          </text>
        </svg>
        {hv && (
          <div
            aria-hidden="true"
            style={{
              ...tooltipStyle,
              left: '50%', top: -6,
              transform: 'translate(-50%, -100%)',
            }}
          >
            <b>{hv.label}</b> — {pctLabel(hv)} ({countLabel(hv)})
          </div>
        )}
      </div>

      {showLegend && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13, minWidth: 0 }}>
          {arcs.map((a, i) => (
            <div
              key={a.key}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover((h) => (h === i ? null : h))}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, cursor: 'default',
                color: hover != null && hover !== i ? 'var(--muted)' : 'var(--ink-2)',
                transition: reduced ? 'none' : 'color 120ms ease',
              }}
            >
              <span style={{
                width: 9, height: 9, borderRadius: 3, flex: 'none', background: a.color,
                outline: hover === i ? '2px solid color-mix(in srgb, var(--ink) 22%, transparent)' : 'none',
                outlineOffset: 1,
              }} />
              <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.label}</span>
              <b style={{ marginLeft: 'auto', paddingLeft: 10, fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
                {pctLabel(a)}
              </b>
            </div>
          ))}
          {note && (
            <div style={{ fontSize: 12, color: 'var(--faint)', maxWidth: 200, marginTop: 2 }}>
              {note}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
