// NotNormalReadBanner — the #1 safety surface.
//
// Shown when an X-ray analysis is present but the model produced NO flagged
// findings (a "zero-flag" study). The danger with a zero-flag result is the
// automation-complacency read: "the AI found nothing, so it's normal." The
// model can and does MISS disease — in validation it flagged 0% of pneumonia
// cases — so absence of a flag is emphatically NOT a normal read. A licensed
// radiologist must positively read every study before it is called normal.
//
// HONESTY: the authoritative body text is the backend's
// `read_disposition_message` (passed as `message`) — the display never asserts
// more than the API. The measured miss-rate line is computed ONLY from real
// study-level numbers in the behaviour card's `no_flag_npv` (passed as `npv`);
// when those are absent we fall back to the WF5 static copy and never fabricate
// a number.
//
// Styled as a prominent-but-non-alarming warn/info note using design tokens.
// Props:
//   show    — parent computes the zero-flag condition (or omit to always render)
//   message — analysis.read_disposition_message (authoritative absence-of-flag text)
//   npv     — behaviorCard.no_flag_npv (measured, in-distribution NPV)
const FALLBACK_MESSAGE =
  'The model can miss disease — in validation it flagged 0% of pneumonia cases — so a ' +
  'radiologist must positively read every study before it is called normal.'

// Build the measured miss-rate sentence from REAL study-level numbers only.
// Returns null if the numbers are not present (never fabricate).
function measuredNpvLine(npv) {
  const sl = npv?.study_level
  if (!sl || sl.npv == null || !sl.no_flag_images) return null
  const missPct = Math.round((sl.missed_disease / sl.no_flag_images) * 100)
  return (
    `In validation, ~${missPct}% of no-flag studies still had disease ` +
    `(NPV ${Number(sl.npv).toFixed(2)} — ${sl.missed_disease} of ${sl.no_flag_images} ` +
    `no-flag studies, in-distribution). A radiologist must read every study.`
  )
}

export default function NotNormalReadBanner({ show = true, message, npv }) {
  if (!show) return null
  const bodyText = (message && message.trim()) || FALLBACK_MESSAGE
  const npvLine = measuredNpvLine(npv)
  return (
    <div
      role="note"
      aria-label="Absence of a flag is not a normal read"
      style={{
        display: 'flex',
        gap: 12,
        alignItems: 'flex-start',
        padding: '14px 16px',
        borderRadius: 12,
        background: 'var(--warn-tint)',
        border: '1px solid color-mix(in srgb, var(--warn) 34%, transparent)',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          flex: 'none',
          width: 34,
          height: 34,
          borderRadius: 9,
          display: 'grid',
          placeItems: 'center',
          background: 'color-mix(in srgb, var(--warn) 18%, transparent)',
          color: 'var(--warn)',
        }}
      >
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      </span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: 14, color: 'var(--ink)' }}>
          Absence of a flag is not a normal read
        </div>
        <p style={{ margin: '4px 0 0', fontSize: 13, lineHeight: 1.55, color: 'var(--ink-2)' }}>
          {bodyText}
        </p>
        {npvLine && (
          <p
            style={{
              margin: '8px 0 0',
              fontSize: 12.5,
              lineHeight: 1.5,
              color: 'var(--ink-2)',
              fontWeight: 500,
            }}
          >
            {npvLine}
          </p>
        )}
      </div>
    </div>
  )
}
