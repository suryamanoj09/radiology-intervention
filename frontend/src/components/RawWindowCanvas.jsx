import { useEffect, useRef, useState } from 'react'

// Volume-pivot demo: TRUE window/level on RAW int16 intensity, done client-side on
// a <canvas> LUT (the canvas+volume-pivot foundation). Unlike the 8-bit PNG path,
// clipped data is recoverable because the browser holds the real pixel values.
function decodeInt16(b64) {
  // Defensive: atob throws on invalid base64 and Int16Array throws on an odd byte
  // length. Return null on any bad input so a malformed server body degrades this
  // one panel instead of throwing up through React and blanking the whole SPA.
  try {
    if (typeof b64 !== 'string' || !b64) return null
    const bin = atob(b64)
    if (bin.length % 2 !== 0) return null
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    return new Int16Array(bytes.buffer)
  } catch {
    return null
  }
}

export default function RawWindowCanvas({ raw, invert = false }) {
  const canvasRef = useRef(null)
  const dataRef = useRef(null)
  const dragRef = useRef(null)
  const [wl, setWl] = useState({ c: raw.default_center, w: raw.default_width })
  const [cursor, setCursor] = useState(null)

  useEffect(() => { dataRef.current = decodeInt16(raw.data_b64) }, [raw])

  useEffect(() => {
    const data = dataRef.current
    const cv = canvasRef.current
    if (!data || !cv) return
    const { rows, cols } = raw
    cv.width = cols; cv.height = rows
    const ctx = cv.getContext('2d')
    const img = ctx.createImageData(cols, rows)
    const lo = wl.c - wl.w / 2
    const span = Math.max(wl.w, 1)
    for (let i = 0; i < data.length; i++) {
      let v = ((data[i] - lo) / span) * 255
      v = v < 0 ? 0 : v > 255 ? 255 : v
      if (invert) v = 255 - v
      const j = i * 4
      img.data[j] = img.data[j + 1] = img.data[j + 2] = v
      img.data[j + 3] = 255
    }
    ctx.putImageData(img, 0, 0)
  }, [wl, raw, invert])

  function onDown(e) { dragRef.current = { x: e.clientX, y: e.clientY, c: wl.c, w: wl.w } }
  function onMove(e) {
    const cv = canvasRef.current, data = dataRef.current
    if (cv && data) {
      const r = cv.getBoundingClientRect()
      const cx = Math.floor((e.clientX - r.left) / r.width * raw.cols)
      const cy = Math.floor((e.clientY - r.top) / r.height * raw.rows)
      if (cx >= 0 && cx < raw.cols && cy >= 0 && cy < raw.rows) setCursor({ v: data[cy * raw.cols + cx] })
    }
    const d = dragRef.current
    if (d) setWl({ w: Math.max(1, d.w + (e.clientX - d.x) * 2), c: d.c - (e.clientY - d.y) * 2 })
  }
  function onUp() { dragRef.current = null }

  return (
    <div className="raw-canvas">
      <canvas ref={canvasRef} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}
        style={{ width: '100%', imageRendering: 'pixelated', background: '#000', cursor: 'ns-resize', borderRadius: 8 }} />
      <p className="muted small">
        True window/level on <b>raw {raw.unit}</b> intensity — left-drag: ↔ width, ↕ level (no server round-trip).
        WL {Math.round(wl.c)} / WW {Math.round(wl.w)}
        {cursor ? ` · cursor ${cursor.v} ${raw.unit}` : ''}
      </p>
    </div>
  )
}
