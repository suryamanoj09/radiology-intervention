import { useEffect, useState } from 'react'

// System | Light | Dark. DEFAULT = system: with no stored choice we leave <html>
// without a data-theme attribute, so the CSS prefers-color-scheme media query
// decides. A manual choice stamps document.documentElement.dataset.theme (which
// wins over the media query in both directions) and persists to localStorage.
const KEY = 'radassist_theme'
const OPTIONS = ['system', 'light', 'dark']
const EVT = 'radassist-theme-change'   // broadcast so every mounted control stays in sync

// --- Accent + density (added; mirrors the design's applyTweaks accent block) ---
const ACCENT_KEY = 'radassist_accent'
const ACCENT_EVT = 'radassist-accent-change'
const DENSITY_KEY = 'radassist_density'
const DENSITY_EVT = 'radassist-density-change'

// Named accents. Each entry carries light/dark primary (p) + teal (t) pairs,
// matching design lines 1091-1096. Keyed by display name.
export const ACCENTS = {
  'Clinical blue': { pL: '#0B5CD5', p2L: '#0A4CAE', pD: '#3B82F6', p2D: '#2E6FE0', tL: '#00B8A9', t2L: '#00988B', tD: '#22D3C7', t2D: '#12B5A9' },
  'Emerald': { pL: '#0E9F6E', p2L: '#0B8259', pD: '#34D399', p2D: '#10B981', tL: '#0891B2', t2L: '#0E7490', tD: '#22D3EE', t2D: '#06B6D4' },
  'Violet': { pL: '#6D28D9', p2L: '#5B21B6', pD: '#A78BFA', p2D: '#8B5CF6', tL: '#0EA5E9', t2L: '#0284C7', tD: '#38BDF8', t2D: '#0EA5E9' },
  'Graphite': { pL: '#475569', p2L: '#334155', pD: '#94A3B8', p2D: '#64748B', tL: '#64748B', t2L: '#475569', tD: '#A3B2C6', t2D: '#7C8CA3' },
}
const ACCENT_DEFAULT = 'Clinical blue'
const DENSITY_OPTIONS = ['comfortable', 'compact']
const DENSITY_DEFAULT = 'comfortable'

function apply(mode) {
  const el = document.documentElement
  if (mode === 'system') delete el.dataset.theme
  else el.dataset.theme = mode
}

// True when the effective theme is dark: an explicit 'dark' choice, or 'system'
// resolving to dark via the OS preference. Accent values differ light vs dark.
function isDark() {
  const t = getTheme()
  if (t === 'dark') return true
  if (t === 'light') return false
  try { return !!window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches } catch { return false }
}

// Writes the accent CSS custom properties to <html> for the current theme.
// Mirrors applyTweaks (design lines 1097-1106).
function applyAccent(name) {
  const el = document.documentElement
  const a = ACCENTS[name] || ACCENTS[ACCENT_DEFAULT]
  const dark = isDark()
  const P = dark ? a.pD : a.pL
  const P2 = dark ? a.p2D : a.p2L
  const T = dark ? a.tD : a.tL
  const T2 = dark ? a.t2D : a.t2L
  el.style.setProperty('--primary', P)
  el.style.setProperty('--primary-2', P2)
  el.style.setProperty('--primary-tint', 'color-mix(in srgb, ' + P + ' ' + (dark ? '20%' : '12%') + ', transparent)')
  el.style.setProperty('--primary-tint2', 'color-mix(in srgb, ' + P + ' ' + (dark ? '32%' : '22%') + ', transparent)')
  el.style.setProperty('--teal', T)
  el.style.setProperty('--teal-2', T2)
  el.style.setProperty('--teal-tint', 'color-mix(in srgb, ' + T + ' ' + (dark ? '22%' : '16%') + ', transparent)')
  el.style.setProperty('--ring', '0 0 0 4px color-mix(in srgb, ' + P + ' 22%, transparent)')
}

function applyDensity(density) {
  document.documentElement.dataset.density = DENSITY_OPTIONS.includes(density) ? density : DENSITY_DEFAULT
}

export function getAccent() {
  try {
    const v = localStorage.getItem(ACCENT_KEY)
    return v && ACCENTS[v] ? v : ACCENT_DEFAULT
  } catch { return ACCENT_DEFAULT }
}

// Single source of truth for the accent. Applies to <html>, persists, and
// broadcasts so every mounted control stays in sync.
export function setAccent(name) {
  const n = ACCENTS[name] ? name : ACCENT_DEFAULT
  applyAccent(n)
  try { localStorage.setItem(ACCENT_KEY, n) } catch { /* ignore */ }
  try { window.dispatchEvent(new CustomEvent(ACCENT_EVT, { detail: n })) } catch { /* ignore */ }
}

export function getDensity() {
  try {
    const v = localStorage.getItem(DENSITY_KEY)
    return DENSITY_OPTIONS.includes(v) ? v : DENSITY_DEFAULT
  } catch { return DENSITY_DEFAULT }
}

export function setDensity(density) {
  const d = DENSITY_OPTIONS.includes(density) ? density : DENSITY_DEFAULT
  applyDensity(d)
  try { localStorage.setItem(DENSITY_KEY, d) } catch { /* ignore */ }
  try { window.dispatchEvent(new CustomEvent(DENSITY_EVT, { detail: d })) } catch { /* ignore */ }
}

export function getTheme() {
  try { return localStorage.getItem(KEY) || 'system' } catch { return 'system' }
}

// The single source of truth for changing the theme. Applies to <html>, persists,
// and notifies all ThemeToggle instances (header + Settings) via a custom event so
// no control can go stale — this is what "Reset theme" in Settings routes through.
export function setTheme(mode) {
  const m = OPTIONS.includes(mode) ? mode : 'system'
  apply(m)
  // Accent colours differ between light and dark, so re-apply the saved accent
  // whenever the theme changes to keep the CSS custom properties correct.
  applyAccent(getAccent())
  try { localStorage.setItem(KEY, m) } catch { /* ignore */ }
  try { window.dispatchEvent(new CustomEvent(EVT, { detail: m })) } catch { /* ignore */ }
}

export function initTheme() {
  apply(OPTIONS.includes(getTheme()) ? getTheme() : 'system')
  applyAccent(getAccent())
  applyDensity(getDensity())
}

export default function ThemeToggle() {
  const [mode, setMode] = useState(getTheme)
  useEffect(() => {
    // Re-read on any theme change (this control or another instance, or another tab).
    const sync = () => setMode(getTheme())
    window.addEventListener(EVT, sync)
    window.addEventListener('storage', sync)
    return () => { window.removeEventListener(EVT, sync); window.removeEventListener('storage', sync) }
  }, [])

  return (
    <div className="seg theme-seg" role="group" aria-label="Colour theme">
      {OPTIONS.map((o) => (
        <button key={o} className={mode === o ? 'active' : ''} aria-pressed={mode === o}
          title={`${o[0].toUpperCase() + o.slice(1)} theme`} onClick={() => setTheme(o)}>
          {o === 'system' ? '🖥' : o === 'light' ? '☀' : '🌙'}
        </button>
      ))}
    </div>
  )
}
