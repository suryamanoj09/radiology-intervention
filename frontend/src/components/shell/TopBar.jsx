import { Children, useEffect, useRef, useState } from 'react'
import ThemeToggle from '../ThemeToggle.jsx'

// 64px glass console top bar: page title, a client-only session search, a theme
// toggle slot, a notifications bell (real session-state notices) and a profile
// menu button.
//
// Honesty rule: no product/compliance claims here. The search is explicitly a
// LOCAL, client-only filter over the current session's studies — it is NOT a
// PHI/patient lookup and issues no network request. The bell lists ONLY the
// real, caller-supplied session-state notices in `alerts` — it is never a
// fabricated inbox and asserts no unread state beyond what the caller passes.
//
// Props:
//   title    : page title (string).
//   user     : { name?, initials? } — profile button label + avatar. Initials
//              fall back to the first letters of `name`; both degrade gracefully.
//   onNav    : (routeKey) => void — profile button calls onNav('profile').
//   onSearch : (query:string) => void — called on each keystroke of the local
//              session filter. Wired to the Dashboard worklist/activity filter.
//   alerts   : array of { id:string, kind:'urgent'|'abstain'|'draft', text:string,
//              onDismiss?:()=>void }. Real session-state notices. When non-empty
//              the bell shows an unread dot; the popover lists each notice (with a
//              Dismiss for any that supply onDismiss). Empty => honest empty state.
//   children : optional node rendered in the theme-toggle slot. Defaults to
//              <ThemeToggle/> so the shared theme mechanism is preserved.

const TITLE_FONT = '"Segoe UI", system-ui, -apple-system, sans-serif'

// Visual mapping for each honest alert kind. `draft` reads as informational
// (primary/blue), never as a warning. No --info var exists, so primary is used.
const KIND_STYLE = {
  urgent: { color: 'var(--danger)', tint: 'var(--danger-tint)', label: 'Urgent' },
  abstain: { color: 'var(--warn)', tint: 'var(--warn-tint)', label: 'Abstained' },
  draft: { color: 'var(--primary)', tint: 'var(--primary-tint)', label: 'Draft' },
}

function KindIcon({ kind }) {
  const stroke = (KIND_STYLE[kind] || KIND_STYLE.draft).color
  const common = {
    width: 15, height: 15, viewBox: '0 0 24 24', fill: 'none', stroke,
    strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true,
  }
  if (kind === 'urgent') {
    return (
      <svg {...common}>
        <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
        <path d="M12 9v4" /><path d="M12 17h.01" />
      </svg>
    )
  }
  if (kind === 'abstain') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" /><path d="M12 8v4" /><path d="M12 16h.01" />
      </svg>
    )
  }
  // draft (informational)
  return (
    <svg {...common}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" /><path d="M9 13h6" /><path d="M9 17h4" />
    </svg>
  )
}

function initialsFor(user) {
  if (user?.initials) return user.initials
  const name = user?.name || ''
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return 'U'
  const first = parts[0][0]
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase()
}

const iconBtnStyle = (active) => ({
  position: 'relative', width: 38, height: 38, borderRadius: 10,
  border: `1px solid ${active ? 'var(--primary)' : 'var(--border)'}`,
  background: active ? 'var(--surface-2)' : 'var(--surface)',
  color: active ? 'var(--primary)' : 'var(--ink-2)',
  cursor: 'pointer', display: 'grid', placeItems: 'center',
  transition: 'color .12s ease, border-color .12s ease, background .12s ease',
  fontFamily: 'inherit',
})

export default function TopBar({ title, user, onNav, onSearch, alerts = [], children }) {
  const [bellHover, setBellHover] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const [profHover, setProfHover] = useState(false)
  const [searchFocus, setSearchFocus] = useState(false)
  const bellWrapRef = useRef(null)
  const hasCustomToggle = Children.count(children) > 0
  const name = user?.name || 'Account'

  const list = Array.isArray(alerts) ? alerts : []
  const hasAlerts = list.length > 0

  // Close the notifications popover on outside-click or Escape.
  useEffect(() => {
    if (!bellOpen) return undefined
    const onDocDown = (e) => {
      if (bellWrapRef.current && !bellWrapRef.current.contains(e.target)) setBellOpen(false)
    }
    const onKey = (e) => { if (e.key === 'Escape') setBellOpen(false) }
    document.addEventListener('mousedown', onDocDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [bellOpen])

  const searchHelp = 'Filters studies analysed in this browser session (client-only, non-PHI)'

  return (
    <header className="console-topbar" style={{
      position: 'sticky', top: 0, zIndex: 40, height: 64,
      background: 'var(--glass)',
      backdropFilter: 'blur(14px) saturate(140%)',
      WebkitBackdropFilter: 'blur(14px) saturate(140%)',
      borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', gap: 16, padding: '0 24px',
    }}>
      <div style={{
        fontFamily: TITLE_FONT, fontWeight: 600, fontSize: 17, color: 'var(--ink)',
        minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>{title}</div>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
        {/* Local, client-only session search (non-PHI) */}
        <div className="console-topsearch" title={searchHelp} style={{
          position: 'relative', display: 'flex', alignItems: 'center',
          background: 'var(--surface)',
          border: `1px solid ${searchFocus ? 'var(--primary)' : 'var(--border)'}`,
          borderRadius: 10, padding: '0 12px', height: 38, width: 240,
          transition: 'border-color .12s ease',
        }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--faint)"
            strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
          </svg>
          <input
            type="search"
            aria-label="Filter studies in this session"
            title={searchHelp}
            placeholder="Search studies in session…"
            onChange={(e) => onSearch && onSearch(e.target.value)}
            onFocus={() => setSearchFocus(true)}
            onBlur={() => setSearchFocus(false)}
            style={{
              border: 'none', background: 'none', outline: 'none', fontFamily: 'inherit',
              fontSize: '13.5px', color: 'var(--ink)', marginLeft: 8, width: '100%',
            }}
          />
        </div>

        {/* Theme toggle slot — preserves the shared theme mechanism */}
        {hasCustomToggle ? children : <ThemeToggle />}

        {/* Notifications — real session-state notices */}
        <div ref={bellWrapRef} style={{ position: 'relative' }}>
          <button
            type="button"
            aria-label={hasAlerts ? `Notifications (${list.length} unread)` : 'Notifications'}
            aria-haspopup="true"
            aria-expanded={bellOpen}
            onClick={() => setBellOpen((v) => !v)}
            onMouseEnter={() => setBellHover(true)}
            onMouseLeave={() => setBellHover(false)}
            style={iconBtnStyle(bellHover || bellOpen)}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.7 21a2 2 0 0 1-3.4 0" />
            </svg>
            {hasAlerts && (
              <span aria-hidden="true" style={{
                position: 'absolute', top: 8, right: 9, width: 7, height: 7, borderRadius: 99,
                background: 'var(--danger)', border: '1.5px solid var(--surface)',
              }} />
            )}
          </button>

          {bellOpen && (
            <div
              role="dialog"
              aria-label="Notifications"
              style={{
                position: 'absolute', top: 46, right: 0, width: 320, maxWidth: '86vw',
                background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 12, boxShadow: 'var(--shadow-lg)', zIndex: 60,
                overflow: 'hidden',
              }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                gap: 8, padding: '11px 14px', borderBottom: '1px solid var(--border)',
              }}>
                <span style={{
                  fontFamily: TITLE_FONT, fontWeight: 600, fontSize: 13, color: 'var(--ink)',
                }}>Notifications</span>
                <span style={{ fontSize: 11.5, color: 'var(--muted)' }}>This session</span>
              </div>

              {!hasAlerts ? (
                <div style={{
                  padding: '20px 14px', fontSize: 13, color: 'var(--muted)', textAlign: 'center',
                }}>
                  No alerts in this session.
                </div>
              ) : (
                <ul style={{
                  listStyle: 'none', margin: 0, padding: 4, maxHeight: 360, overflowY: 'auto',
                }}>
                  {list.map((a) => {
                    const ks = KIND_STYLE[a.kind] || KIND_STYLE.draft
                    return (
                      <li key={a.id} style={{
                        display: 'flex', alignItems: 'flex-start', gap: 10,
                        padding: '10px 10px', borderRadius: 8,
                      }}>
                        <span aria-hidden="true" style={{
                          flex: '0 0 auto', width: 28, height: 28, borderRadius: 8,
                          background: ks.tint, display: 'grid', placeItems: 'center',
                        }}>
                          <KindIcon kind={a.kind} />
                        </span>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{
                            fontSize: 10.5, fontWeight: 700, letterSpacing: '.04em',
                            textTransform: 'uppercase', color: ks.color, marginBottom: 2,
                          }}>{ks.label}</div>
                          <div style={{
                            fontSize: 13, lineHeight: 1.4, color: 'var(--ink)',
                            wordBreak: 'break-word',
                          }}>{a.text}</div>
                          {typeof a.onDismiss === 'function' && (
                            <button
                              type="button"
                              onClick={() => a.onDismiss()}
                              style={{
                                marginTop: 6, padding: '2px 8px', fontSize: 11.5,
                                fontFamily: 'inherit', fontWeight: 600, cursor: 'pointer',
                                color: 'var(--ink-2)', background: 'var(--surface-2)',
                                border: '1px solid var(--border)', borderRadius: 6,
                              }}>Dismiss</button>
                          )}
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* Profile menu */}
        <button
          type="button"
          onClick={() => onNav && onNav('profile')}
          aria-label={`Profile — ${name}`}
          onMouseEnter={() => setProfHover(true)}
          onMouseLeave={() => setProfHover(false)}
          style={{
            display: 'flex', alignItems: 'center', gap: 9, padding: '4px 6px 4px 4px',
            borderRadius: 99, border: `1px solid ${profHover ? 'var(--primary)' : 'var(--border)'}`,
            background: 'var(--surface)', cursor: 'pointer', fontFamily: 'inherit',
            transition: 'border-color .12s ease',
          }}>
          <span aria-hidden="true" style={{
            width: 30, height: 30, borderRadius: 99,
            background: 'linear-gradient(135deg,var(--primary),var(--teal))',
            display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 700, fontSize: 12,
          }}>{initialsFor(user)}</span>
          <span style={{
            fontSize: 13, fontWeight: 600, color: 'var(--ink)', paddingRight: 4,
            whiteSpace: 'nowrap',
          }}>{name}</span>
        </button>
      </div>
    </header>
  )
}
