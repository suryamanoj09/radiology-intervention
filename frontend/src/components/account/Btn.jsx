import { useState } from 'react'

// One reusable, theme-aware, keyboard-accessible button used across the account
// cards. `variant`: 'primary' | 'default' | 'danger' | 'ghost'. `size`: 'md' | 'sm'.
// Every colour is a design CSS var, so light/dark + focus ring are automatic.
export default function Btn({
  children, onClick, variant = 'default', size = 'md',
  disabled = false, type = 'button', title, style: extra = {},
}) {
  const [hot, setHot] = useState(false)
  const [foc, setFoc] = useState(false)

  const base = {
    padding: size === 'sm' ? '7px 12px' : '10px 16px',
    borderRadius: 10, fontWeight: 600, fontSize: size === 'sm' ? 12.5 : 13.5,
    cursor: disabled ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
    whiteSpace: 'nowrap', opacity: disabled ? 0.55 : 1,
    transition: 'background .15s,border-color .15s,color .15s,box-shadow .15s',
    outline: 'none', boxShadow: foc ? 'var(--ring)' : 'none',
    display: 'inline-flex', alignItems: 'center', gap: 7,
  }

  let variantStyle
  if (variant === 'primary') {
    variantStyle = { border: 'none', background: hot && !disabled ? 'var(--primary-2)' : 'var(--primary)', color: 'var(--on-primary)', boxShadow: foc ? 'var(--ring)' : 'var(--shadow-sm)' }
  } else if (variant === 'danger') {
    variantStyle = { border: '1px solid var(--danger)', background: hot && !disabled ? 'var(--danger)' : 'var(--danger-tint)', color: hot && !disabled ? 'var(--on-primary)' : 'var(--danger)' }
  } else if (variant === 'ghost') {
    variantStyle = { border: '1px solid transparent', background: 'transparent', color: hot && !disabled ? 'var(--primary)' : 'var(--muted)' }
  } else {
    variantStyle = { border: '1px solid var(--border-2)', background: 'var(--surface)', color: hot && !disabled ? 'var(--primary)' : 'var(--ink)', borderColor: hot && !disabled ? 'var(--primary)' : 'var(--border-2)' }
  }

  return (
    <button
      type={type} onClick={onClick} disabled={disabled} title={title}
      style={{ ...base, ...variantStyle, ...extra }}
      onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      onFocus={() => setFoc(true)} onBlur={() => setFoc(false)}
    >
      {children}
    </button>
  )
}
