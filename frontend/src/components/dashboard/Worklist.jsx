// Worklist table for the console dashboard. Faithful to design lines 658-673
// (5-column grid: Study · Modality · Priority · AI · Status). HONESTY: there is
// NO server PHI worklist — every row here comes from studies analysed in THIS
// browser session (localStorage / the sessionStudies prop), and ids are opaque
// de-identified tokens, never patient names. When there is nothing local we show
// an honest empty state rather than inventing a queue.
//
// `rows` arrive already filtered by the Dashboard's session search (studyQuery).
// `studyQuery` is passed only so we can tell the two empty states apart: an
// active search that matched nothing vs. a session with no studies at all.
const COLS = '1.3fr 1.1fr .8fr 1fr .7fr'

export default function Worklist({ rows = [], onOpenStudy, onNav, studyQuery = '' }) {
  const filteredEmpty = rows.length === 0 && String(studyQuery).trim() !== ''
  return (
    <div
      style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 16, boxShadow: 'var(--shadow-sm)', overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 22px 12px' }}>
        <div style={{ fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: 16 }}>Worklist</div>
        <button
          onClick={() => onNav && onNav('app')}
          style={{
            fontSize: 13, fontWeight: 600, color: 'var(--primary)', background: 'none',
            border: 'none', cursor: 'pointer', fontFamily: 'inherit',
          }}
        >
          New analysis →
        </button>
      </div>

      <div
        style={{
          display: 'grid', gridTemplateColumns: COLS, gap: 8, padding: '0 22px 8px',
          fontSize: 11, fontWeight: 700, letterSpacing: '.04em', color: 'var(--faint)',
          textTransform: 'uppercase',
        }}
      >
        <span>Study</span><span>Modality</span><span>Priority</span><span>AI signal</span><span>Analysed</span>
      </div>

      {filteredEmpty ? (
        <div style={{ padding: '26px 22px 30px', borderTop: '1px solid var(--border)', textAlign: 'center' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>No studies in this session match</div>
          <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 4, maxWidth: 340, marginInline: 'auto' }}>
            Nothing in this session matches “{String(studyQuery).trim()}”. Clear the search to see every study you analysed.
          </div>
        </div>
      ) : rows.length === 0 ? (
        <div style={{ padding: '26px 22px 30px', borderTop: '1px solid var(--border)', textAlign: 'center' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>No studies in this session yet</div>
          <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 4, maxWidth: 340, marginInline: 'auto' }}>
            The worklist is built only from studies you analyse in this browser — nothing is pulled from a server.
          </div>
          <button
            onClick={() => onNav && onNav('app')}
            style={{
              marginTop: 14, padding: '9px 16px', borderRadius: 10, border: 'none',
              background: 'var(--primary)', color: '#fff', fontWeight: 600, fontSize: 13,
              cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            Analyse a study
          </button>
        </div>
      ) : (
        rows.map((w) => (
          <button
            key={w.key}
            onClick={() => (onOpenStudy ? onOpenStudy(w.study) : onNav && onNav('app'))}
            style={{
              width: '100%', display: 'grid', gridTemplateColumns: COLS, gap: 8,
              alignItems: 'center', padding: '12px 22px', border: 'none',
              borderTop: '1px solid var(--border)', background: 'none', cursor: 'pointer',
              fontFamily: 'inherit', textAlign: 'left',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-2)' }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
          >
            <span style={{ fontWeight: 600, fontSize: 13.5, color: 'var(--ink)', fontFamily: 'var(--font-mono)' }}>{w.id}</span>
            <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>
              {w.mod} {w.view && <span style={{ color: 'var(--faint)' }}>· {w.view}</span>}
            </span>
            <span>
              <span style={{ fontSize: 11.5, fontWeight: 700, padding: '2px 9px', borderRadius: 99, background: w.prioBg, color: w.prioFg }}>
                {w.prio}
              </span>
            </span>
            <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>{w.ai}</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 7, height: 7, borderRadius: 99, background: w.statusDot, flex: 'none' }} />
              <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>{w.time}</span>
            </span>
          </button>
        ))
      )}
    </div>
  )
}
