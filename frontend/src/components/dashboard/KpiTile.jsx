// A single KPI tile for the console dashboard. Faithful to design lines 606-613:
// label, big mono value, a small pill tag, and a sub-line. Pure presentation —
// the Dashboard decides what each number MEANS and whether it is model-measured
// (real, from the behaviour card) or clearly labelled illustrative "Demo data".
//
// `tone` selects the pill colour from the theme tint tokens:
//   neutral | success | warn | teal | demo
// The `demo` tone is reserved for any number that is NOT a real measurement, so a
// reader can never mistake illustrative data for a measured metric.
const TONES = {
  neutral: { bg: 'var(--surface-3)', fg: 'var(--ink-2)' },
  success: { bg: 'var(--success-tint)', fg: 'var(--success)' },
  warn: { bg: 'var(--warn-tint)', fg: 'var(--warn)' },
  teal: { bg: 'var(--teal-tint)', fg: 'var(--teal-2)' },
  primary: { bg: 'var(--primary-tint)', fg: 'var(--primary)' },
  demo: { bg: 'var(--warn-tint)', fg: 'var(--warn)' },
}

export default function KpiTile({ label, value, tag, tone = 'neutral', sub }) {
  const t = TONES[tone] || TONES.neutral
  return (
    <div
      style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 15, padding: 18, boxShadow: 'var(--shadow-sm)',
      }}
    >
      <div style={{ fontSize: 12.5, color: 'var(--muted)', fontWeight: 500 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        <span
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 600,
            color: 'var(--ink)', letterSpacing: '-.02em',
          }}
        >
          {value}
        </span>
        {tag && (
          <span
            style={{
              fontSize: 11.5, fontWeight: 700, padding: '2px 8px', borderRadius: 99,
              background: t.bg, color: t.fg,
            }}
          >
            {tag}
          </span>
        )}
      </div>
      {sub && <div style={{ fontSize: 11.5, color: 'var(--faint)', marginTop: 6 }}>{sub}</div>}
    </div>
  )
}
