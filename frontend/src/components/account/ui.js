// Shared inline-styled primitives for the Account/Security cards. Everything is
// driven by the design CSS vars so both themes and the focus ring come for free.

export const cardStyle = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 16, padding: '20px 22px', boxShadow: 'var(--shadow-sm)',
}

export const headingStyle = {
  fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: 16,
  display: 'flex', alignItems: 'center', gap: 10,
}

// A small status pill: {label, color, tint}. color/tint are CSS-var strings.
export function pillStyle(color, tint) {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12,
    fontWeight: 600, color, background: tint, padding: '3px 9px', borderRadius: 99,
  }
}
