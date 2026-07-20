import { useEffect, useRef } from 'react'
import { colorForStructure } from '../overlayPalette'

// Absolutely-positioned ANATOMY overlay drawn on a <canvas> over the slice image.
// It reads an indexed label PNG (seg.mask_urls[sliceIndex], grayscale where each
// pixel's R value == that voxel's structure_id) and repaints each labeled pixel with
// its region's IDENTITY color at a uniform translucent alpha. Color/alpha carry no
// magnitude — this labels anatomy, it does not detect or grade disease. Opt-in and
// pixelated (nearest-neighbor) so the mask stays crisp when scaled to the image.
//
// Same-origin PNGs, so no crossOrigin is needed and getImageData won't taint.
function hexToRgb(hex) {
  const h = String(hex || '').replace('#', '')
  return [
    parseInt(h.slice(0, 2), 16) || 0,
    parseInt(h.slice(2, 4), 16) || 0,
    parseInt(h.slice(4, 6), 16) || 0,
  ]
}

// Choose which mask slice to paint under the viewer's current slice. Alignment is BY
// GEOMETRIC POSITION (the viewer and the segmenter cap/downscale differently, so array
// offsets do not correspond). Returns the mask index, or -1 when it cannot be aligned
// safely (then no overlay is drawn — better a clean image than a misregistered one).
function pickMaskIndex(seg, sliceIndex, viewPositions) {
  const pos = seg?.slice_positions
  const vp = Array.isArray(viewPositions) ? viewPositions[sliceIndex] : undefined
  if (Array.isArray(pos) && pos.length && vp != null && Number.isFinite(vp)) {
    // nearest seg position to this viewer slice's position, within a tolerance of
    // ~0.75 of the seg's median slice spacing (i.e. it must be essentially the same slice).
    let best = -1, bestD = Infinity
    for (let i = 0; i < pos.length; i++) {
      const d = Math.abs(pos[i] - vp)
      if (d < bestD) { bestD = d; best = i }
    }
    const spacings = []
    for (let i = 1; i < pos.length; i++) spacings.push(Math.abs(pos[i] - pos[i - 1]))
    spacings.sort((a, b) => a - b)
    const med = spacings.length ? spacings[Math.floor(spacings.length / 2)] : 0
    const tol = med > 0 ? med * 0.75 : 1e-6
    return bestD <= tol ? best : -1
  }
  // No positions to align with: fall back to the array index ONLY when the slice
  // counts match exactly (single-series, uncapped); otherwise decline.
  const urls = seg?.mask_urls
  if (Array.isArray(urls) && Array.isArray(viewPositions) && urls.length === viewPositions.length) {
    return sliceIndex
  }
  if (Array.isArray(urls) && viewPositions == null && sliceIndex < urls.length) {
    return sliceIndex  // no viewer positions available at all — best effort
  }
  return -1
}

export default function OverlayLayer({ seg, sliceIndex, hidden, opacity = 0.5,
                                       viewSeriesId, viewPositions }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    const clear = () => ctx.clearRect(0, 0, cv.width, cv.height)

    const urls = seg?.mask_urls
    // Series gate: never paint a mask onto a DIFFERENT series than it was computed on.
    if (seg?.series_id && viewSeriesId && seg.series_id !== viewSeriesId) {
      clear()
      return
    }
    const maskIdx = pickMaskIndex(seg, sliceIndex, viewPositions)
    if (!Array.isArray(urls) || maskIdx < 0 || maskIdx >= urls.length || !urls[maskIdx]) {
      clear()
      return
    }

    // structure_id -> [r,g,b] identity color, resolved once per render.
    const colorMap = new Map()
    ;(seg.regions || []).forEach((region, i) => {
      if (region && region.structure_id > 0) {
        colorMap.set(region.structure_id, hexToRgb(colorForStructure(region, i)))
      }
    })
    const alpha = Math.max(0, Math.min(255, Math.round(opacity * 255)))

    let cancelled = false
    const img = new Image()
    img.onload = () => {
      if (cancelled) return
      const w = img.naturalWidth, h = img.naturalHeight
      if (!w || !h) { clear(); return }
      try {
        // Read the indexed label PNG off-screen at its native resolution.
        const tmp = document.createElement('canvas')
        tmp.width = w; tmp.height = h
        const tctx = tmp.getContext('2d')
        tctx.drawImage(img, 0, 0)
        const src = tctx.getImageData(0, 0, w, h).data

        cv.width = w; cv.height = h
        const out = ctx.createImageData(w, h)
        const dst = out.data
        for (let p = 0; p < w * h; p++) {
          const v = src[p * 4] // R channel == structure_id
          if (v > 0 && !(hidden && hidden.has(v))) {
            const rgb = colorMap.get(v)
            if (rgb) {
              const j = p * 4
              dst[j] = rgb[0]; dst[j + 1] = rgb[1]; dst[j + 2] = rgb[2]; dst[j + 3] = alpha
            }
          }
          // else: leave transparent (createImageData is zero-initialized)
        }
        ctx.putImageData(out, 0, 0)
      } catch {
        // Tainted/unreadable canvas or decode issue — fail quietly, no overlay.
        clear()
      }
    }
    img.onerror = () => { if (!cancelled) clear() }
    img.src = urls[maskIdx]

    return () => { cancelled = true }
  }, [seg, sliceIndex, hidden, opacity, viewSeriesId, viewPositions])

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: 'auto',
        pointerEvents: 'none',
        imageRendering: 'pixelated',
      }}
    />
  )
}
