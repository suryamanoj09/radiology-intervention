import { useEffect, useState } from 'react'
import Sidebar from './Sidebar.jsx'
import TopBar from './TopBar.jsx'

// Console layout shell: fixed Sidebar + a content column of (TopBar, then the
// routed page). Below ~900px the sidebar hides so the content column gets the
// full width (nav then lives in the top bar / page as the caller sees fit).
//
// Honesty rule: pure layout — asserts nothing about the model.
//
// Props:
//   route     : current page key — forwarded to Sidebar for active-item marking.
//   title     : page title — forwarded to TopBar.
//   user      : { name?, initials? } — forwarded to TopBar.
//   onNav     : (routeKey) => void — nav callback shared by Sidebar + TopBar.
//   onSearch  : (query) => void — optional; forwarded to TopBar's local search.
//   alerts    : array of { id, kind:'urgent'|'abstain'|'draft', text, onDismiss? } —
//               optional; forwarded to TopBar's notifications bell/popover.
//   items     : optional CLINICAL nav override — forwarded to Sidebar.
//   items2    : optional ACCOUNT nav override — forwarded to Sidebar.
//   promoRoute: optional promo-card target — forwarded to Sidebar.
//   themeSlot : optional node for TopBar's theme-toggle slot (defaults to
//               <ThemeToggle/> inside TopBar).
//   children  : the routed page content.

const NARROW_QUERY = '(max-width: 900px)'

// Tracks whether the viewport is below the sidebar-collapse breakpoint.
function useIsNarrow() {
  const get = () => (typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(NARROW_QUERY).matches : false)
  const [narrow, setNarrow] = useState(get)
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined
    const mql = window.matchMedia(NARROW_QUERY)
    const onChange = () => setNarrow(mql.matches)
    onChange()
    // addEventListener is the modern API; addListener is the legacy fallback.
    if (mql.addEventListener) mql.addEventListener('change', onChange)
    else mql.addListener(onChange)
    return () => {
      if (mql.removeEventListener) mql.removeEventListener('change', onChange)
      else mql.removeListener(onChange)
    }
  }, [])
  return narrow
}

export default function AppShell({
  route, title, user, onNav, onSearch, alerts,
  items, items2, promoRoute, themeSlot, children,
}) {
  const narrow = useIsNarrow()

  return (
    <div className="console-shell" style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg)' }}>
      {!narrow && (
        <Sidebar
          route={route}
          onNav={onNav}
          items={items}
          items2={items2}
          promoRoute={promoRoute}
        />
      )}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <TopBar
          title={title}
          user={user}
          onNav={onNav}
          onSearch={onSearch}
          alerts={alerts}
        >
          {themeSlot}
        </TopBar>
        <div style={{ flex: 1, minWidth: 0 }}>
          {children}
        </div>
      </div>
    </div>
  )
}
