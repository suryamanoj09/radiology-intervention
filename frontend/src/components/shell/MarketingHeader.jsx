import { Children, useEffect, useRef } from 'react'
import ThemeToggle from '../ThemeToggle.jsx'

// Sticky glass marketing header for the public site shell.
//
// Honesty rule: this component makes NO product/compliance claims — it only
// renders navigation and CTAs. Nav labels mirror the design's on-page sections
// (Platform / Modalities / Evidence / Security) plus routed pages (About).
//
// Props:
//   route     : current page key (string) — used to mark the active nav item.
//   onNav     : (route) => void — called with 'login' | 'dashboard' | 'about'
//               | 'evidence' | 'home'. In-page anchors (#platform, #modalities,
//               #security) scroll to the section on Home; from any other route
//               they first onNav('home') and then scroll once Home has mounted.
//   children  : optional theme-toggle node. If omitted, <ThemeToggle/> is used.

const WORDMARK_FONT = '"Segoe UI", system-ui, -apple-system, sans-serif'

// The gradient "compass" mark shared by header + footer.
function BrandMark({ size = 34, radius = 10, icon = 19 }) {
  return (
    <span style={{
      width: size, height: size, borderRadius: radius, display: 'grid',
      placeItems: 'center', background: 'linear-gradient(135deg,var(--primary),var(--teal))',
      boxShadow: 'var(--shadow-sm)', flex: 'none',
    }}>
      <svg width={icon} height={icon} viewBox="0 0 24 24" fill="none" stroke="#fff"
        strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 3v18" /><path d="M3 12h18" /><circle cx="12" cy="12" r="9" />
      </svg>
    </span>
  )
}

// On-page section links (anchor scroll) + routed nav.
const ANCHOR_LINKS = [
  { label: 'Platform', href: '#platform' },
  { label: 'Modalities', href: '#modalities' },
  { label: 'Evidence', href: '#performance', route: 'evidence' },
  { label: 'Security', href: '#security' },
]

const navLinkStyle = {
  padding: '8px 13px', borderRadius: 9, color: 'var(--ink-2)',
  fontWeight: 500, fontSize: '14.5px', textDecoration: 'none',
  background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit',
  lineHeight: 1.2, whiteSpace: 'nowrap',
}

// Scroll a same-page section (#platform/#modalities/#security) into view.
function scrollToHash(hash) {
  const id = String(hash || '').replace(/^#/, '')
  if (!id) return false
  const el = typeof document !== 'undefined' && document.getElementById(id)
  if (!el) return false
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return true
}

export default function MarketingHeader({ route, onNav, children }) {
  const nav = (r) => (e) => { if (e) e.preventDefault(); onNav && onNav(r) }
  const hasCustomToggle = Children.count(children) > 0

  // Remember a section the user asked for while off Home, so we can scroll to it
  // once Home mounts. On Home we scroll immediately.
  const pendingHash = useRef(null)
  const anchorNav = (hash) => (e) => {
    if (e) e.preventDefault()
    if (route === 'home') {
      scrollToHash(hash)
    } else {
      pendingHash.current = hash
      onNav && onNav('home')
    }
  }
  useEffect(() => {
    if (route === 'home' && pendingHash.current) {
      const hash = pendingHash.current
      pendingHash.current = null
      // Defer one tick so the freshly-mounted Home sections exist in the DOM.
      const t = setTimeout(() => scrollToHash(hash), 0)
      return () => clearTimeout(t)
    }
  }, [route])

  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 60,
      backdropFilter: 'blur(16px) saturate(140%)',
      WebkitBackdropFilter: 'blur(16px) saturate(140%)',
      background: 'var(--glass)', borderBottom: '1px solid var(--border)',
    }}>
      {/* Scoped, self-contained responsive rules — not added to styles.css, CSP-safe. */}
      <style>{`
        @media (max-width: 1024px) { .mk-site-links { display: none !important; } }
      `}</style>
      <div style={{
        maxWidth: 1240, margin: '0 auto', padding: '0 28px', minHeight: 68,
        display: 'flex', alignItems: 'center', gap: 26, flexWrap: 'wrap',
      }}>
        {/* Logo → home */}
        <button onClick={nav('home')} aria-label="RadAssist home" style={{
          display: 'flex', alignItems: 'center', gap: 11,
          background: 'none', border: 'none', cursor: 'pointer', padding: '13px 0',
        }}>
          <BrandMark />
          <span style={{
            fontFamily: WORDMARK_FONT, fontWeight: 700, fontSize: 19,
            letterSpacing: '-.02em', color: 'var(--ink)',
          }}>Rad<span style={{ color: 'var(--primary)' }}>Assist</span></span>
        </button>

        {/* Primary nav */}
        <nav aria-label="Primary" className="site-links mk-site-links" style={{
          display: 'flex', gap: 6, marginLeft: 8, flexWrap: 'wrap',
        }}>
          {ANCHOR_LINKS.map((l) => {
            const active = l.route && route === l.route
            return l.route ? (
              <button key={l.label} onClick={nav(l.route)}
                aria-current={active ? 'page' : undefined}
                style={{ ...navLinkStyle, color: active ? 'var(--primary)' : 'var(--ink-2)' }}>
                {l.label}
              </button>
            ) : (
              <a key={l.label} href={l.href} onClick={anchorNav(l.href)} style={navLinkStyle}>{l.label}</a>
            )
          })}
          <button onClick={nav('about')}
            aria-current={route === 'about' ? 'page' : undefined}
            style={{ ...navLinkStyle, color: route === 'about' ? 'var(--primary)' : 'var(--ink-2)' }}>
            About
          </button>
        </nav>

        {/* Actions */}
        <div style={{
          marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10,
          flexWrap: 'wrap',
        }}>
          {hasCustomToggle ? children : <ThemeToggle />}
          <button onClick={nav('login')} style={{
            padding: '9px 16px', borderRadius: 10, border: '1px solid var(--border)',
            background: 'var(--surface)', color: 'var(--ink)', fontWeight: 600,
            fontSize: 14, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
          }}>Sign in</button>
          <button onClick={nav('dashboard')} style={{
            padding: '9px 18px', borderRadius: 10, border: 'none',
            background: 'var(--primary)', color: 'var(--on-primary)', fontWeight: 600,
            fontSize: 14, cursor: 'pointer', fontFamily: 'inherit',
            boxShadow: 'var(--shadow-sm)', whiteSpace: 'nowrap',
          }}>Launch console</button>
        </div>
      </div>
    </header>
  )
}
