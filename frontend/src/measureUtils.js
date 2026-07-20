// Geometry for the measurement tools. Points are in ORIGINAL-raster pixels; spacing
// (rowMm/colMm) is the EFFECTIVE (rendered-pixel) spacing from the viewer, so distances
// are physical mm. Anisotropy (row != col) is handled by scaling each axis to mm first.
export function lengthMm(p0, p1, rowMm, colMm) {
  if (!rowMm || !colMm) return null
  return Math.hypot((p1[0] - p0[0]) * colMm, (p1[1] - p0[1]) * rowMm)
}

// Angle (degrees) at the MIDDLE point b of a-b-c, in mm space.
export function angleDeg(a, b, c, rowMm, colMm) {
  const rm = rowMm || 1, cm = colMm || 1
  const ba = [(a[0] - b[0]) * cm, (a[1] - b[1]) * rm]
  const bc = [(c[0] - b[0]) * cm, (c[1] - b[1]) * rm]
  const mag = Math.hypot(ba[0], ba[1]) * Math.hypot(bc[0], bc[1])
  if (mag === 0) return 0
  const dot = ba[0] * bc[0] + ba[1] * bc[1]
  return (Math.acos(Math.max(-1, Math.min(1, dot / mag))) * 180) / Math.PI
}

export function fmtValue(m) {
  if (m.type === 'length') return m.value != null ? `${m.value.toFixed(1)} mm` : `${m.px?.toFixed(0)} px`
  if (m.type === 'angle') return `${m.value.toFixed(1)}°`
  if (m.type === 'roi') {
    if (!m.roi) return '…'
    const a = m.roi.area_mm2 != null ? ` · ${m.roi.area_mm2} mm²` : ''
    return `${m.roi.mean} ${m.roi.unit} (±${m.roi.sd})${a}`
  }
  return ''
}
