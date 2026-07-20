import { useEffect, useRef } from 'react'
import * as THREE from 'three'

// Hero3D — CSP-safe React port of the design's <radassist-scan-3d> web component
// (originally hero3d.js over THREE r128 loaded from a CDN). Here THREE is bundled
// locally via `npm i three`, so there is no external network/font/script request.
//
// Scene (faithful to the original intent):
//   • a stack of translucent axial "slices" (a volume being read),
//   • a bright scan plane sweeping up and down through the stack,
//   • an orbiting neural-node field (points + a few link lines) around the volume.
// Interaction: drag to orbit, gentle auto-rotate when idle, transparent background,
// ResizeObserver-driven resize, and full THREE disposal on unmount.
//
// prefers-reduced-motion: no auto-rotate and the scan plane holds still (the scene
// renders one settled frame and only repaints on user drag / resize).
//
// This is purely decorative: aria-hidden, no data, no claims. It never asserts a
// finding — the floating chips over it (owned by HomePage) are illustrative.

export default function Hero3D({ style, className }) {
  const mountRef = useRef(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return undefined

    const prefersReduced = typeof window !== 'undefined' && window.matchMedia
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false

    // --- WebGL guard: if the context can't be created, bail quietly so the
    // parent's CSS gradient + chips remain a perfectly good hero. -------------
    let renderer
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' })
    } catch {
      return undefined
    }
    const initW = mount.clientWidth || 520
    const initH = mount.clientHeight || 520
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setSize(initW, initH, false)
    renderer.setClearColor(0x000000, 0) // transparent — parent supplies the navy
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    renderer.domElement.style.cursor = 'grab'
    renderer.domElement.setAttribute('aria-hidden', 'true')
    mount.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(42, initW / initH, 0.1, 100)
    camera.position.set(0, 0.6, 6.4)
    camera.lookAt(0, 0, 0)

    // Root group we orbit (keeps camera math trivial).
    const root = new THREE.Group()
    scene.add(root)

    // Track disposables for a clean teardown.
    const disposables = []
    const track = (obj) => { disposables.push(obj); return obj }

    const TEAL = 0x22d3c7
    const BLUE = 0x3b82f6

    // --- Stacked translucent slices ------------------------------------------
    const SLICES = 13
    const sliceW = 3.0
    const sliceH = 3.0
    const gap = 0.26
    const stackH = (SLICES - 1) * gap
    const sliceGeo = track(new THREE.PlaneGeometry(sliceW, sliceH))
    const edgeGeo = track(new THREE.EdgesGeometry(sliceGeo))
    const slices = []
    for (let i = 0; i < SLICES; i++) {
      const y = i * gap - stackH / 2
      const t = i / (SLICES - 1)
      // Face fill — very translucent, tint drifts teal→blue up the stack.
      const faceMat = track(new THREE.MeshBasicMaterial({
        color: new THREE.Color().lerpColors(new THREE.Color(TEAL), new THREE.Color(BLUE), t),
        transparent: true,
        opacity: 0.06,
        side: THREE.DoubleSide,
        depthWrite: false,
      }))
      const face = new THREE.Mesh(sliceGeo, faceMat)
      face.rotation.x = -Math.PI / 2
      face.position.y = y
      // Edge outline — the thing you actually read as a "slice".
      const edgeMat = track(new THREE.LineBasicMaterial({
        color: 0x8fb3e6, transparent: true, opacity: 0.22,
      }))
      const edges = new THREE.LineSegments(edgeGeo, edgeMat)
      edges.rotation.x = -Math.PI / 2
      edges.position.y = y
      root.add(face, edges)
      slices.push({ face, faceMat, edges, edgeMat, y })
    }

    // --- Sweeping scan plane --------------------------------------------------
    const scanGeo = track(new THREE.PlaneGeometry(sliceW * 1.08, sliceH * 1.08))
    const scanMat = track(new THREE.MeshBasicMaterial({
      color: TEAL, transparent: true, opacity: 0.5, side: THREE.DoubleSide, depthWrite: false,
    }))
    const scanPlane = new THREE.Mesh(scanGeo, scanMat)
    scanPlane.rotation.x = -Math.PI / 2
    root.add(scanPlane)
    // A crisp bright rim on the scan plane so the leading edge glows.
    const scanRim = new THREE.LineSegments(
      track(new THREE.EdgesGeometry(scanGeo)),
      track(new THREE.LineBasicMaterial({ color: 0x9af7ee, transparent: true, opacity: 0.9 })),
    )
    scanRim.rotation.x = -Math.PI / 2
    root.add(scanRim)

    // --- Orbiting neural-node field ------------------------------------------
    // Points on a spherical shell around the volume, plus a handful of link lines
    // between near neighbours — a "neural" motif, not a data structure.
    const NODES = 60
    const nodePos = []
    const nodeVec = []
    const R = 2.9
    for (let i = 0; i < NODES; i++) {
      // Fibonacci-ish sphere distribution for even coverage.
      const phi = Math.acos(1 - 2 * (i + 0.5) / NODES)
      const theta = Math.PI * (1 + Math.sqrt(5)) * i
      const r = R * (0.82 + Math.random() * 0.28)
      const v = new THREE.Vector3(
        r * Math.sin(phi) * Math.cos(theta),
        r * Math.cos(phi) * 0.72,
        r * Math.sin(phi) * Math.sin(theta),
      )
      nodeVec.push(v)
      nodePos.push(v.x, v.y, v.z)
    }
    const nodeGeo = track(new THREE.BufferGeometry())
    nodeGeo.setAttribute('position', new THREE.Float32BufferAttribute(nodePos, 3))
    const nodeMat = track(new THREE.PointsMaterial({
      color: 0xbfe0ff, size: 0.07, transparent: true, opacity: 0.9,
      sizeAttenuation: true, depthWrite: false,
    }))
    const nodes = new THREE.Points(nodeGeo, nodeMat)
    root.add(nodes)

    // Link lines between nearby nodes.
    const linkPts = []
    for (let i = 0; i < NODES; i++) {
      for (let j = i + 1; j < NODES; j++) {
        if (nodeVec[i].distanceTo(nodeVec[j]) < 1.15 && Math.random() < 0.5) {
          linkPts.push(nodeVec[i].x, nodeVec[i].y, nodeVec[i].z)
          linkPts.push(nodeVec[j].x, nodeVec[j].y, nodeVec[j].z)
        }
      }
    }
    const linkGeo = track(new THREE.BufferGeometry())
    linkGeo.setAttribute('position', new THREE.Float32BufferAttribute(linkPts, 3))
    const linkMat = track(new THREE.LineBasicMaterial({
      color: TEAL, transparent: true, opacity: 0.16,
    }))
    const links = new THREE.LineSegments(linkGeo, linkMat)
    root.add(links)

    // --- Interaction: drag-to-orbit + inertial auto-rotate -------------------
    let targetRotY = -0.5
    let targetRotX = 0.32
    let curRotY = targetRotY
    let curRotX = targetRotX
    let dragging = false
    let lastX = 0
    let lastY = 0
    let velY = 0
    const AUTO = prefersReduced ? 0 : 0.0016

    const onDown = (e) => {
      dragging = true
      velY = 0
      const p = e.touches ? e.touches[0] : e
      lastX = p.clientX
      lastY = p.clientY
      renderer.domElement.style.cursor = 'grabbing'
    }
    const onMove = (e) => {
      if (!dragging) return
      const p = e.touches ? e.touches[0] : e
      const dx = p.clientX - lastX
      const dy = p.clientY - lastY
      lastX = p.clientX
      lastY = p.clientY
      targetRotY += dx * 0.008
      targetRotX += dy * 0.006
      targetRotX = Math.max(-0.9, Math.min(0.9, targetRotX))
      velY = dx * 0.008
      if (e.cancelable && e.touches) e.preventDefault()
    }
    const onUp = () => {
      dragging = false
      renderer.domElement.style.cursor = 'grab'
    }
    renderer.domElement.addEventListener('pointerdown', onDown)
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    renderer.domElement.addEventListener('touchstart', onDown, { passive: true })
    renderer.domElement.addEventListener('touchmove', onMove, { passive: false })
    window.addEventListener('touchend', onUp)

    // --- Resize ---------------------------------------------------------------
    const resize = () => {
      const w = mount.clientWidth || initW
      const h = mount.clientHeight || initH
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      if (prefersReduced) renderer.render(scene, camera)
    }
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null
    if (ro) ro.observe(mount)

    // --- Animation loop -------------------------------------------------------
    let raf = 0
    let cleanupExtra = null // extra listener removed only in the reduced-motion branch
    const clock = new THREE.Clock()
    const animate = () => {
      raf = requestAnimationFrame(animate)
      const t = clock.getElapsedTime()

      if (!dragging) {
        velY *= 0.94
        targetRotY += velY + AUTO
      }
      // Ease current toward target.
      curRotY += (targetRotY - curRotY) * 0.08
      curRotX += (targetRotX - curRotX) * 0.08
      root.rotation.y = curRotY
      root.rotation.x = curRotX

      if (!prefersReduced) {
        // Scan plane sweeps up and down through the stack.
        const sweep = (Math.sin(t * 0.9) * 0.5 + 0.5) // 0..1
        const scanY = -stackH / 2 + sweep * stackH
        scanPlane.position.y = scanY
        scanRim.position.y = scanY
        // Slices brighten as the scan plane passes over them.
        for (const s of slices) {
          const d = Math.abs(s.y - scanY)
          const glow = Math.max(0, 1 - d / 0.5)
          s.faceMat.opacity = 0.05 + glow * 0.4
          s.edgeMat.opacity = 0.2 + glow * 0.7
        }
        // Node field breathes / counter-rotates slightly.
        nodes.rotation.y = -t * 0.06
        links.rotation.y = -t * 0.06
        nodeMat.opacity = 0.7 + Math.sin(t * 1.6) * 0.2
      }

      renderer.render(scene, camera)
    }

    if (prefersReduced) {
      // One settled frame; repaint only on drag/resize.
      scanPlane.position.y = 0
      scanRim.position.y = 0
      renderer.render(scene, camera)
      // Still allow drag to feel alive without continuous auto-motion:
      const drawOnDemand = () => { renderer.render(scene, camera) }
      window.addEventListener('pointermove', drawOnDemand)
      // Track for cleanup via closure below.
      cleanupExtra = () => window.removeEventListener('pointermove', drawOnDemand)
    } else {
      animate()
    }

    // --- Teardown -------------------------------------------------------------
    return () => {
      if (raf) cancelAnimationFrame(raf)
      if (ro) ro.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onDown)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      renderer.domElement.removeEventListener('touchstart', onDown)
      renderer.domElement.removeEventListener('touchmove', onMove)
      window.removeEventListener('touchend', onUp)
      if (cleanupExtra) cleanupExtra()
      for (const d of disposables) { try { d.dispose && d.dispose() } catch { /* noop */ } }
      renderer.dispose()
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
    }
  }, [])

  return (
    <div
      ref={mountRef}
      className={className}
      aria-hidden="true"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', ...style }}
    />
  )
}
