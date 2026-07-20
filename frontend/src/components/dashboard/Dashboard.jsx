// Console landing page. Composes the delivered dashboard parts (KpiTile,
// AreaChart/Donut, Worklist) into the design's dashboard layout (RadAssist.dc.html
// lines 585-687), rebuilt for HONESTY:
//   - There is NO server PHI worklist / patient names / fabricated "Dr. Rao"
//     greeting / invented turnaround metrics. Every study row and every chart
//     point comes from studies analysed in THIS browser session (`sessionStudies`).
//   - The KPI tiles that carry a hard number are REAL model measurements sourced
//     live from the behaviour card (falling back to the true measured constants),
//     never illustrative theatre.
// Inline styles reference WF2's CSS tokens only (theme-aware light/dark, CSP-safe).
import KpiTile from './KpiTile.jsx'
import AreaChart, { Donut } from './MiniChart.jsx'
import Worklist from './Worklist.jsx'
import { distinctFlagged } from '../../labelMap.js'

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

// Opaque de-identified token for a study — never a patient name.
function tokenFor(a, i) {
  const raw = String(a?.image_id || `session-${i}`)
  const short = raw.replace(/[^a-zA-Z0-9]/g, '').slice(0, 6).toUpperCase() || String(i + 1)
  return `ANON-${short}`
}

// Map a raw analysis object → a Worklist row (its own honesty contract lives there).
function toRow(a, i) {
  const flagged = distinctFlagged(a?.findings)
  const abstain = a?.competence === 'abstain'
  const urgent = a?.triage === 'urgent'
  const priority = a?.triage && a.triage !== 'routine'
  const prio = abstain ? 'Abstained' : urgent ? 'STAT' : priority ? 'Priority' : 'Routine'
  const prioBg = abstain
    ? 'var(--surface-3)'
    : urgent
      ? 'var(--danger-tint)'
      : priority
        ? 'var(--warn-tint)'
        : 'var(--success-tint)'
  const prioFg = abstain
    ? 'var(--faint)'
    : urgent
      ? 'var(--danger)'
      : priority
        ? 'var(--warn)'
        : 'var(--success)'
  // A zero-flag study is NOT a normal read (research fix #1): the model can miss
  // disease, so the "all-clear" green treatment is wrong here — surface it as a
  // neutral, not-green "not a normal read" state.
  const zeroFlag = !abstain && flagged.length === 0
  const ai = abstain
    ? 'Not scored (off-domain)'
    : zeroFlag
      ? 'Not a normal read · no flags'
      : `${flagged.length} flag${flagged.length > 1 ? 's' : ''} · ${flagged[0].label}`
  const statusDot = abstain
    ? 'var(--faint)'
    : urgent
      ? 'var(--danger)'
      : zeroFlag
        ? 'var(--warn)'
        : 'var(--success)'
  return {
    key: a?.image_id || `s-${i}`,
    id: tokenFor(a, i),
    study: a,
    mod: 'Chest X-ray',
    view: a?.view || '',
    prio, prioBg, prioFg, ai, statusDot,
    time: 'This session',
  }
}

const cardStyle = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 16, padding: '20px 22px', boxShadow: 'var(--shadow-sm)',
}

export default function Dashboard({ behaviorCard, sessionStudies = [], onNav, onOpenStudy, studyQuery = '' }) {
  const bc = behaviorCard && behaviorCard.available !== false ? behaviorCard : null
  const live = !!(bc && Array.isArray(bc.detection) && bc.detection.length)

  // ---- REAL model metrics — numbers come ONLY from the live behaviour card.
  // When it is unavailable we render "—"/"unavailable" (parity with HomePage/
  // EvidencePage) instead of baked-in constants that would look measured. -------
  const fmtN = (v, digits) => (typeof v === 'number' && !Number.isNaN(v) ? v.toFixed(digits) : '—')
  const ece = live ? fmtN(bc?.calibration?.overall?.ece, 4) : '—'
  const eceN = live ? (bc?.calibration?.overall?.n ?? null) : null
  const scored = live ? (bc?.images_scored ?? null) : null
  const pa = live ? (bc?.subgroup?.groups?.PA?.micro_auroc ?? null) : null
  const ap = live ? (bc?.subgroup?.groups?.AP?.micro_auroc ?? null) : null
  const paN = live ? (bc?.subgroup?.groups?.PA?.images ?? null) : null
  const apN = live ? (bc?.subgroup?.groups?.AP?.images ?? null) : null
  const pneuRow = live ? bc?.detection?.find((d) => d.pathology === 'Pneumonia') : null
  const hernRow = live ? bc?.detection?.find((d) => d.pathology === 'Hernia') : null
  const sourceNote = live ? 'live' : 'unavailable'

  // ---- REAL session data ------------------------------------------------------
  const studies = Array.isArray(sessionStudies) ? sessionStudies.filter(Boolean) : []
  const allRows = studies.map(toRow)

  // Case-insensitive session search over study id / modality / label / status.
  // The worklist, the activity chart and the modality mix all cross-filter to the
  // matching rows; when nothing matches we show an honest "no match" state rather
  // than an empty chart. (KPI tiles stay unfiltered — they are measured facts, not
  // a view of this search.)
  const q = String(studyQuery || '').trim().toLowerCase()
  const matches = (r) =>
    !q || `${r.id} ${r.mod} ${r.view} ${r.ai} ${r.prio} ${r.time}`.toLowerCase().includes(q)
  const rows = q ? allRows.filter(matches) : allRows
  const urgentRows = rows.filter((r) => r.prio === 'STAT')

  const hasStudies = studies.length > 0
  const hasMatches = rows.length > 0
  const filteredEmpty = hasStudies && q !== '' && !hasMatches

  // 7-day activity scaffold ending today. No per-study timestamps are kept, so all
  // session studies land on today — a truthful "everything you did is this session".
  const today = new Date()
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today)
    d.setDate(today.getDate() - (6 - i))
    return { label: DOW[d.getDay()], count: 0 }
  })
  days[6].count = rows.length
  const hasActivity = hasMatches

  // Shown inside the mid-row cards when a search filtered every study out.
  const matchEmpty = (
    <div style={{ marginTop: 24, padding: '28px 12px', textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>
      No studies in this session match “{String(studyQuery).trim()}”.
    </div>
  )

  return (
    <div style={{ padding: '26px 28px 40px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header — neutral, no fabricated identity or clinic */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-head)', margin: 0 }}>Session overview</h2>
          <p style={{ color: 'var(--muted)', fontSize: 14, marginTop: 4 }}>
            Studies you analyse stay in this browser — nothing is read from a server worklist.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={() => onNav && onNav('upload')}
            style={{
              padding: '10px 16px', borderRadius: 10, border: '1px solid var(--border-2)',
              background: 'var(--surface)', color: 'var(--ink)', fontWeight: 600, fontSize: 13.5,
              cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
            }}
          >
            Upload studies
          </button>
          <button
            onClick={() => onNav && onNav('app')}
            style={{
              padding: '10px 16px', borderRadius: 10, border: 'none', background: 'var(--primary)',
              color: '#fff', fontWeight: 600, fontSize: 13.5, cursor: 'pointer', fontFamily: 'inherit',
              whiteSpace: 'nowrap', boxShadow: 'var(--shadow-sm)',
            }}
          >
            New AI analysis
          </button>
        </div>
      </div>

      {/* Priority banner — only when a REAL session study is model-flagged urgent */}
      {urgentRows.length > 0 && (
        <div style={{
          marginTop: 20, display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px',
          borderRadius: 14, background: 'var(--danger-tint)',
          border: '1px solid color-mix(in srgb, var(--danger) 30%, transparent)',
        }}>
          <span style={{ width: 34, height: 34, flex: 'none', borderRadius: 9, display: 'grid', placeItems: 'center', background: 'var(--danger)', color: '#fff' }} aria-hidden="true">!</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: 14.5, color: 'var(--danger)' }}>
              {urgentRows.length} study{urgentRows.length > 1 ? ' flags' : ' flag'} the model marked urgent
            </div>
            <div style={{ fontSize: 13, color: 'var(--ink-2)' }}>
              {urgentRows[0].id} — model-flagged, awaiting your sign-off. Not a confirmed diagnosis.
            </div>
          </div>
          <button
            onClick={() => (onOpenStudy ? onOpenStudy(urgentRows[0].study) : onNav && onNav('app'))}
            style={{ padding: '9px 15px', borderRadius: 9, border: 'none', background: 'var(--danger)', color: '#fff', fontWeight: 600, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}
          >
            Review now
          </button>
        </div>
      )}

      {/* KPI grid — session count (real) + live model measurements */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(158px, 1fr))', gap: 14, marginTop: 18 }}>
        <KpiTile label="Analysed this session" value={studies.length} tag="local" tone="primary" sub="Kept in this browser only" />
        <KpiTile label="Validation studies" value={scored != null ? scored : '—'} tag={sourceNote} tone="neutral" sub="Images in the measured benchmark" />
        <KpiTile label="Calibration ECE" value={ece} tag={sourceNote} tone="warn" sub={eceN != null ? `Over ${eceN} label-instances — the % is a score, not a probability` : 'The % is a score, not a probability'} />
        <KpiTile label="PA micro-AUROC" value={pa != null ? fmtN(pa, 3) : '—'} tag={paN != null ? `n=${paN}` : sourceNote} tone="teal" sub="Frontal PA films" />
        <KpiTile label="AP micro-AUROC" value={ap != null ? fmtN(ap, 3) : '—'} tag={apN != null ? `n=${apN}` : sourceNote} tone={ap != null && pa != null && ap < pa ? 'warn' : 'teal'} sub="Portable AP films — performance shifts" />
      </div>

      {/* Mid row — session activity + modality mix */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 16, marginTop: 16 }} className="dash-mid">
        <div style={cardStyle}>
          <div style={{ fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: 16 }}>This session's activity</div>
          <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 2 }}>Studies analysed in this browser · last 7 days</div>
          {hasActivity ? (
            <AreaChart data={days} ariaLabel="Studies analysed this session per day" />
          ) : filteredEmpty ? (
            matchEmpty
          ) : (
            <div style={{ marginTop: 24, padding: '28px 12px', textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>
              No studies analysed yet in this browser session.
            </div>
          )}
        </div>

        <div style={cardStyle}>
          <div style={{ fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: 16 }}>Modality mix</div>
          {hasActivity ? (
            <div style={{ marginTop: 16 }}>
              <Donut
                segments={[{ label: 'Chest X-ray', value: rows.length, color: 'var(--primary)' }]}
                centerValue={rows.length}
                note="This build analyses chest X-ray only. CT/MRI are viewer-only."
              />
            </div>
          ) : filteredEmpty ? (
            matchEmpty
          ) : (
            <div style={{ marginTop: 24, padding: '28px 12px', textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>
              Analyse a study to see its modality here.
            </div>
          )}
        </div>
      </div>

      {/* Bottom row — session worklist + honest model caveats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 16, marginTop: 16 }} className="dash-bot">
        <Worklist rows={rows} onOpenStudy={onOpenStudy} onNav={onNav} studyQuery={hasStudies ? studyQuery : ''} />

        <div style={cardStyle}>
          <div style={{ fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: 16 }}>Where the model is weak</div>
          <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 2 }}>Measured limits ({sourceNote}) — read before trusting a flag</div>
          <ul style={{ margin: '14px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {live && pneuRow && (
              <li style={{ fontSize: 13, color: 'var(--ink-2)' }}>
                <b style={{ color: 'var(--danger)' }}>Pneumonia</b> — AUROC {fmtN(pneuRow.auroc, 3)}, sensitivity {fmtN(pneuRow.sensitivity, 3)}{pneuRow.positives != null ? ` (only ${pneuRow.positives} positive${pneuRow.positives === 1 ? '' : 's'})` : ''}.{pneuRow.sensitivity === 0 ? ' It misses pneumonia.' : ''}
              </li>
            )}
            <li style={{ fontSize: 13, color: 'var(--ink-2)' }}>
              <b style={{ color: 'var(--warn)' }}>Grad-CAM localization is weak</b> — heatmaps show attention, not a validated lesion boundary.
            </li>
            {live && hernRow && hernRow.positives === 0 && (
              <li style={{ fontSize: 13, color: 'var(--ink-2)' }}>
                <b>{String(hernRow.pathology).replace(/_/g, ' ')} is unmeasured</b> — 0 positives in the benchmark, so it has no reliable performance.
              </li>
            )}
            {!live && (
              <li style={{ fontSize: 13, color: 'var(--muted)' }}>
                Measured per-pathology limits are unavailable right now — see the full evidence page rather than an invented figure.
              </li>
            )}
          </ul>
          <button
            onClick={() => onNav && onNav('evidence')}
            style={{ marginTop: 16, fontSize: 13, fontWeight: 600, color: 'var(--primary)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: 0 }}
          >
            See full measured evidence →
          </button>
        </div>
      </div>
    </div>
  )
}
