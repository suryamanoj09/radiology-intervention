// Central route registry. A plain, dependency-free data map that App.jsx consumes
// to decide which shell wraps a given page and what document title to use.
//
// shell:
//   'marketing' — public-facing pages (landing, info) with the marketing chrome
//   'console'   — authenticated product surface (nav rail + workspace chrome)
//   'bare'      — no chrome (e.g. the sign-in screen)
//
// Keep this file free of imports so it can be shared by any layer without
// pulling in React or app state.

export const ROUTES = {
  home: { shell: 'marketing', title: 'RadAssist' },
  about: { shell: 'marketing', title: 'About' },
  help: { shell: 'marketing', title: 'Help' },
  evidence: { shell: 'marketing', title: 'Evidence' },
  privacy: { shell: 'marketing', title: 'Privacy' },
  dashboard: { shell: 'console', title: 'Dashboard' },
  upload: { shell: 'console', title: 'Upload studies' },
  app: { shell: 'console', title: 'Workspace' },
  profile: { shell: 'console', title: 'Profile' },
  settings: { shell: 'console', title: 'Settings' },
  login: { shell: 'bare', title: 'Sign in' },
}

// The shell used when a route is unknown. 'marketing' is the safest public default.
export const DEFAULT_SHELL = 'marketing'

// Returns the shell type ('marketing' | 'console' | 'bare') for a route.
// Falls back to DEFAULT_SHELL for unknown routes.
export function shellFor(route) {
  const r = ROUTES[route]
  return r ? r.shell : DEFAULT_SHELL
}

// Returns the document title for a route. Falls back to 'RadAssist'.
export function titleFor(route) {
  const r = ROUTES[route]
  return r ? r.title : 'RadAssist'
}
