import StudyMetadataStrip from '../StudyMetadataStrip.jsx'

// StudyContextBar — the design's top "study context bar" (RadAssist.dc.html 692-708),
// re-skinned around the REAL analysis data. It is a presentation shell only; it
// asserts nothing the model does not.
//
// HONESTY: the design mock shows an "Analysed on-device" chip. That is FALSE for
// this system — analysis runs SERVER-SIDE against a de-identified, in-memory image.
// We reword truthfully to "Analysed server-side · de-identified".
//
// It also carries the modality tab bar (xray/ct/mri) and the analyzer utility
// buttons, and the real <StudyMetadataStrip> for the full de-identification detail.

const TABS = [
  { id: 'xray', label: 'Chest X-ray · AI' },
  { id: 'ct', label: 'CT · viewer + AI' },
  { id: 'mri', label: 'MRI · viewer + AI' },
]

function formatModalityLine(analysis) {
  if (!analysis) return 'No study loaded'
  const mod = (analysis.modality || 'CR').toUpperCase()
  const src = analysis.source_format === 'dicom' ? 'DICOM' : 'PNG/JPG'
  const view = analysis.view_position && analysis.view_position.trim()
    ? analysis.view_position.toUpperCase()
    : 'view unknown — confirm'
  return `${mod} · Chest · ${view} · ${src}`
}

const toolBtn = {
  padding: '8px 12px',
  borderRadius: 9,
  border: '1px solid var(--border-2)',
  background: 'var(--surface)',
  color: 'var(--ink)',
  fontWeight: 600,
  fontSize: 12.5,
  cursor: 'pointer',
  fontFamily: 'inherit',
  whiteSpace: 'nowrap',
}

export default function StudyContextBar({
  analysis,
  tab,
  setTab,
  railsCollapsed,
  setRailsCollapsed,
  onOpenInfo,
  onOpenLimitations,
  onOpenFailures,
  onOpenAdmin,
}) {
  const imageId = analysis?.image_id || '—'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Modality tab bar + utility buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <nav
          role="tablist"
          aria-label="Modality"
          style={{ display: 'flex', gap: 4, background: 'var(--surface-3)', borderRadius: 10, padding: 4 }}
        >
          {TABS.map((t) => {
            const active = tab === t.id
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={active}
                onClick={() => setTab(t.id)}
                style={{
                  padding: '7px 13px',
                  borderRadius: 7,
                  border: 'none',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  fontSize: 12.5,
                  fontWeight: 600,
                  background: active ? 'var(--surface)' : 'none',
                  color: active ? 'var(--primary)' : 'var(--ink-2)',
                  boxShadow: active ? 'var(--shadow-sm)' : 'none',
                }}
              >
                {t.label}
              </button>
            )
          })}
        </nav>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 7, flexWrap: 'wrap' }}>
          <button style={toolBtn} onClick={onOpenInfo} aria-haspopup="dialog">? How to use</button>
          <button style={toolBtn} onClick={onOpenLimitations} aria-haspopup="dialog">⚠ Limitations</button>
          <button style={toolBtn} onClick={onOpenFailures} aria-haspopup="dialog">🔬 Where it fails</button>
          <button style={toolBtn} onClick={onOpenAdmin} aria-haspopup="dialog">📊 Model tuning</button>
        </div>
      </div>

      {/* Study context bar (design 692-708) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          flexWrap: 'wrap',
          padding: '14px 18px',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 14,
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span
            aria-hidden="true"
            style={{ width: 40, height: 40, borderRadius: 11, display: 'grid', placeItems: 'center', background: 'var(--navy)', color: 'var(--on-primary, #fff)', flex: 'none' }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3v18M7 6c2 1 3 1 5 0s3-1 5 0M7 6v12c2 1 3 1 5 0s3-1 5 0V6" />
            </svg>
          </span>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <span
                className="mono"
                style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 15, color: 'var(--ink)' }}
                title="De-identified server id — not a patient identifier"
              >
                {imageId}
              </span>
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 1 }}>
              {formatModalityLine(analysis)}
            </div>
          </div>
        </div>

        {/* HONEST status chips — reworded from the mock's false "on-device". */}
        <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 600, padding: '5px 10px', borderRadius: 8, background: 'var(--success-tint)', color: 'var(--success)' }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M20 6 9 17l-5-5" /></svg>
            Analysed server-side · de-identified
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 600, padding: '5px 10px', borderRadius: 8, background: 'var(--surface-3)', color: 'var(--ink-2)' }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>
            Not stored server-side
          </span>
        </div>

        {analysis && (
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 9 }}>
            <button
              style={toolBtn}
              onClick={() => setRailsCollapsed((v) => !v)}
              aria-pressed={railsCollapsed}
              title="Collapse the report rail so the image gets the full width"
            >
              {railsCollapsed ? '⇥ Show report' : '⇤ Focus viewer'}
            </button>
          </div>
        )}
      </div>

      {/* Real de-identification detail (image id, identifiers removed, source, view). */}
      {analysis && <StudyMetadataStrip analysis={analysis} />}
    </div>
  )
}
