import { useState } from 'react'

// Fixed 248px console sidebar: brand, two nav groups (CLINICAL / ACCOUNT) and a
// bottom "Model behaviour card" promo linking to the Evidence/About page.
//
// Honesty rule: this component asserts NOTHING about the model. The promo card
// copy is an invitation to read where the AI is reliable AND where it fails —
// it makes no accuracy or compliance claim. Nav labels are pure navigation.
//
// Props:
//   route   : current page key (string) — marks the active nav item (fallback if
//             an item has no explicit `active`).
//   onNav   : (routeKey) => void — navigation callback used by the default items.
//   items   : CLINICAL group. Array of { icon, label, route?, active?, badge?, onClick? }.
//             `icon` is either a known key ('dashboard'|'workspace'|'upload'|
//             'profile'|'settings') or a ready React node. Defaults provided.
//   items2  : ACCOUNT group. Same item shape. Defaults provided.
//   promoRoute : page key the promo card opens (default 'about').

const WORDMARK_FONT = '"Segoe UI", system-ui, -apple-system, sans-serif'

// ---- inline SVG icon set (stroke = currentColor so it inherits item colour) ----
const svg = (children) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
)
const ICONS = {
  dashboard: svg(<><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>),
  workspace: svg(<><path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z" /><path d="M9 21h6" /></>),
  upload: svg(<><path d="M12 15V3m0 0 4 4m-4-4L8 7" /><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></>),
  profile: svg(<><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>),
  settings: svg(<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.14.63.63 1.12 1.26 1.26H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></>),
}
function renderIcon(icon) {
  if (icon == null) return null
  return typeof icon === 'string' ? (ICONS[icon] || null) : icon
}

// BrandMark — the gradient "compass" shared with the marketing shell.
function BrandMark() {
  return (
    <span style={{
      width: 34, height: 34, borderRadius: 10, display: 'grid', placeItems: 'center',
      background: 'linear-gradient(135deg,var(--primary),var(--teal))', flex: 'none',
    }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff"
        strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 3v18" /><path d="M3 12h18" /><circle cx="12" cy="12" r="9" />
      </svg>
    </span>
  )
}

const GROUP_LABEL = {
  fontSize: '10.5px', fontWeight: 700, letterSpacing: '.08em',
  color: 'var(--faint)', padding: '8px 12px 6px',
}

function NavButton({ item, activeFallback }) {
  const [hover, setHover] = useState(false)
  const active = item.active != null ? item.active : (item.route != null && item.route === activeFallback)
  return (
    <button
      type="button"
      onClick={item.onClick}
      aria-current={active ? 'page' : undefined}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 11, width: '100%',
        padding: '9px 12px', borderRadius: 10, border: 'none', cursor: 'pointer',
        fontFamily: 'inherit', fontSize: '13.5px', fontWeight: active ? 600 : 500,
        color: active ? 'var(--primary)' : 'var(--ink-2)',
        background: active ? 'var(--primary-tint)' : (hover ? 'var(--surface-3)' : 'transparent'),
        transition: 'background .12s ease, color .12s ease',
      }}>
      <span style={{ display: 'grid', placeItems: 'center', width: 18, height: 18, flex: 'none' }}>
        {renderIcon(item.icon)}
      </span>
      <span style={{ flex: 1, textAlign: 'left' }}>{item.label}</span>
      {item.badge != null && item.badge !== false && (
        <span style={{
          fontSize: 11, fontWeight: 700, padding: '1px 8px', borderRadius: 99,
          background: 'var(--primary-tint)', color: 'var(--primary)',
        }}>{item.badge}</span>
      )}
    </button>
  )
}

export default function Sidebar({ route, onNav, items, items2, promoRoute = 'about' }) {
  const go = (r) => () => { onNav && onNav(r) }

  const clinical = items || [
    { icon: 'dashboard', label: 'Dashboard', route: 'dashboard', onClick: go('dashboard') },
    { icon: 'workspace', label: 'New analysis', route: 'app', onClick: go('app') },
    { icon: 'upload', label: 'Upload', route: 'upload', onClick: go('upload') },
  ]
  const account = items2 || [
    { icon: 'profile', label: 'Profile', route: 'profile', onClick: go('profile') },
    { icon: 'settings', label: 'Settings', route: 'settings', onClick: go('settings') },
  ]

  const [promoHover, setPromoHover] = useState(false)

  return (
    <aside className="console-side" style={{
      width: 248, flex: 'none', background: 'var(--surface)',
      borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column',
      position: 'sticky', top: 0, height: '100vh',
    }}>
      {/* Brand */}
      <div style={{
        padding: '18px 18px 14px', display: 'flex', alignItems: 'center', gap: 11,
        borderBottom: '1px solid var(--border)',
      }}>
        <BrandMark />
        <span style={{
          fontFamily: WORDMARK_FONT, fontWeight: 700, fontSize: 17, letterSpacing: '-.02em',
          color: 'var(--ink)',
        }}>Rad<span style={{ color: 'var(--primary)' }}>Assist</span></span>
      </div>

      {/* Nav */}
      <nav aria-label="Console" style={{
        padding: '14px 12px', display: 'flex', flexDirection: 'column', gap: 3,
        flex: 1, overflow: 'auto',
      }}>
        <div style={GROUP_LABEL}>CLINICAL</div>
        {clinical.map((it) => <NavButton key={it.label} item={it} activeFallback={route} />)}
        <div style={{ ...GROUP_LABEL, paddingTop: 14 }}>ACCOUNT</div>
        {account.map((it) => <NavButton key={it.label} item={it} activeFallback={route} />)}
      </nav>

      {/* Model behaviour promo card */}
      <div style={{ padding: 14, borderTop: '1px solid var(--border)' }}>
        <div style={{
          background: 'linear-gradient(135deg,var(--primary-tint),var(--teal-tint))',
          borderRadius: 12, padding: 14,
        }}>
          <div style={{ fontFamily: WORDMARK_FONT, fontWeight: 600, fontSize: '13.5px', color: 'var(--ink)' }}>
            Model behaviour card
          </div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
            See where the AI is reliable — and where it fails.
          </div>
          <button
            type="button"
            onClick={go(promoRoute)}
            onMouseEnter={() => setPromoHover(true)}
            onMouseLeave={() => setPromoHover(false)}
            style={{
              marginTop: 10, fontSize: '12.5px', fontWeight: 600, color: 'var(--primary)',
              background: 'none', border: 'none', cursor: 'pointer', padding: 0,
              fontFamily: 'inherit', textDecoration: promoHover ? 'underline' : 'none',
            }}>Open →</button>
        </div>
      </div>
    </aside>
  )
}
