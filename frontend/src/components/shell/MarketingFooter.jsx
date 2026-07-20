// Marketing site footer for the public shell.
//
// Honesty rule: NO fabricated compliance/certification claims. The only status
// statement is the honest "research prototype / not a medical device" line,
// which mirrors the app's standing disclaimer.
//
// Props:
//   onNav : (route) => void — called with a route key for routed links
//           ('home' | 'about' | 'help' | 'evidence' | 'privacy').

const WORDMARK_FONT = '"Segoe UI", system-ui, -apple-system, sans-serif'
const YEAR = new Date().getFullYear()

// Link columns. Each link resolves to a route passed to onNav.
const COLUMNS = [
  {
    title: 'Product',
    links: [
      { label: 'Overview', route: 'home' },
      { label: 'Evidence', route: 'evidence' },
      { label: 'Help & docs', route: 'help' },
    ],
  },
  {
    title: 'Company',
    links: [
      { label: 'About', route: 'about' },
      { label: 'Evidence', route: 'evidence' },
    ],
  },
  {
    title: 'Legal',
    links: [
      { label: 'Privacy', route: 'privacy' },
      { label: 'Help & docs', route: 'help' },
    ],
  },
]

const linkStyle = {
  fontSize: '13.5px', color: 'var(--muted)', background: 'none', border: 'none',
  cursor: 'pointer', fontFamily: 'inherit', padding: 0, textAlign: 'left',
  lineHeight: 1.3, textDecoration: 'none', width: 'fit-content',
}

export default function MarketingFooter({ onNav }) {
  const nav = (r) => () => onNav && onNav(r)

  return (
    <footer style={{
      borderTop: '1px solid var(--border)', background: 'var(--surface)', marginTop: 24,
    }}>
      {/* Scoped, self-contained responsive rules — not added to styles.css, CSP-safe. */}
      <style>{`
        @media (max-width: 860px) { .mk-foot-grid { grid-template-columns: 1fr 1fr !important; row-gap: 28px; } }
        @media (max-width: 520px) { .mk-foot-grid { grid-template-columns: 1fr !important; } }
      `}</style>
      <div className="foot-grid mk-foot-grid" style={{
        maxWidth: 1240, margin: '0 auto', padding: '52px 28px 28px',
        display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr 1fr', gap: 32,
      }}>
        {/* Brand + honesty statement */}
        <div>
          <button onClick={nav('home')} aria-label="RadAssist home" style={{
            display: 'flex', alignItems: 'center', gap: 11,
            background: 'none', border: 'none', cursor: 'pointer', padding: 0,
          }}>
            <span style={{
              width: 32, height: 32, borderRadius: 9, display: 'grid', placeItems: 'center',
              background: 'linear-gradient(135deg,var(--primary),var(--teal))', flex: 'none',
            }}>
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff"
                strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
                <path d="M12 3v18M3 12h18" /><circle cx="12" cy="12" r="9" />
              </svg>
            </span>
            <span style={{ fontFamily: WORDMARK_FONT, fontWeight: 700, fontSize: 17, color: 'var(--ink)' }}>
              Rad<span style={{ color: 'var(--primary)' }}>Assist</span>
            </span>
          </button>
          <p style={{ fontSize: '13.5px', color: 'var(--muted)', margin: '14px 0 0', maxWidth: 280 }}>
            Explainable AI radiology decision-support. AI drafts; a licensed clinician reviews,
            corrects and approves.
          </p>
          <div style={{ marginTop: 16, fontSize: '11.5px', color: 'var(--faint)', lineHeight: 1.6 }}>
            Research prototype · Not a medical device · Not FDA-cleared · For investigational,
            non-clinical use only
          </div>
        </div>

        {/* Link columns */}
        {COLUMNS.map((col) => (
          <div key={col.title}>
            <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--ink)', marginBottom: 14 }}>
              {col.title}
            </div>
            <nav aria-label={col.title} style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
              {col.links.map((l) => (
                <button key={l.label + col.title} onClick={nav(l.route)} style={linkStyle}>
                  {l.label}
                </button>
              ))}
            </nav>
          </div>
        ))}
      </div>

      {/* Copyright bar */}
      <div style={{ borderTop: '1px solid var(--border)', padding: '18px 28px' }}>
        <div style={{
          maxWidth: 1240, margin: '0 auto', display: 'flex', justifyContent: 'space-between',
          gap: 16, flexWrap: 'wrap', fontSize: '12.5px', color: 'var(--muted)',
        }}>
          <span>© {YEAR} RadAssist. All rights reserved.</span>
          <span>Images analysed on-device · No diagnosis is asserted without clinician review</span>
        </div>
      </div>
    </footer>
  )
}
