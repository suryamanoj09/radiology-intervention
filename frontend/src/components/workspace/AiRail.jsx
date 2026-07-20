import { useState } from 'react'
import FindingsForm from '../FindingsForm.jsx'
import DisagreementPrompts from '../DisagreementPrompts.jsx'
import ReportPanel from '../ReportPanel.jsx'
import PatientIntake from '../PatientIntake.jsx'
import WhatNotChecked from '../WhatNotChecked.jsx'
import NotNormalReadBanner from './NotNormalReadBanner.jsx'

// AiRail — the design's right-hand rail (RadAssist.dc.html 764-859): an
// "AI findings" / "Report" tab switcher. This is a COMPOSITION shell only — the
// two tabs render the REAL functional components unchanged:
//   • AI findings → FindingsForm (AI suggestions unchecked-by-default, confirm/
//     dismiss, voice dictation) + DisagreementPrompts (discordance surfacing).
//   • Report      → ReportPanel (its own clinical/patient/differential sub-tabs,
//     completeness, mandatory sign-off, AI-vs-edited provenance, jsPDF export).
// The per-finding accept/reject cards the mock draws by hand ARE FindingsForm /
// DisagreementPrompts — we frame them, we do not reimplement them.

const railTab = (active) => ({
  flex: 1,
  padding: 9,
  borderRadius: 8,
  border: 'none',
  cursor: 'pointer',
  fontFamily: 'inherit',
  fontSize: 13.5,
  fontWeight: 600,
  background: active ? 'var(--primary)' : 'none',
  color: active ? 'var(--on-primary, #fff)' : 'var(--ink-2)',
})

const card = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 14,
  padding: '16px 18px',
  boxShadow: 'var(--shadow-sm)',
}

export default function AiRail({
  analysis,
  suggestions,
  structured,
  setStructured,
  history,
  setHistory,
  patient,
  setPatient,
  behaviorCard,
  comparison,
  setFocusedFinding,
}) {
  const [active, setActive] = useState('findings') // 'findings' | 'report'

  const findingsCount = suggestions?.length || 0
  const acceptedCount = (suggestions || []).filter((s) => structured?.[s.key]).length
  // Zero-flag: an analysis exists but the model flagged nothing. Never let this
  // read as "normal" — surface the safety banner.
  const zeroFlag = !!analysis && findingsCount === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Tab switcher (design 766-769) */}
      <div style={{ display: 'flex', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 11, padding: 4, boxShadow: 'var(--shadow-sm)' }}>
        <button onClick={() => setActive('findings')} style={railTab(active === 'findings')}>
          AI findings <span style={{ fontSize: 11, opacity: 0.8 }}>· {findingsCount}</span>
        </button>
        <button onClick={() => setActive('report')} style={railTab(active === 'report')}>
          Report
        </button>
      </div>

      {active === 'findings' && (
        <>
          {/* Accepted-count summary (design 772-775) */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', padding: '11px 15px', background: 'var(--primary-tint)', border: '1px solid color-mix(in srgb, var(--primary) 22%, transparent)', borderRadius: 12 }}>
            <div style={{ fontSize: 13, color: 'var(--ink-2)' }}>
              <b style={{ color: 'var(--primary)' }}>{acceptedCount}</b> of {findingsCount} suggestions confirmed
            </div>
            <span style={{ fontSize: 11.5, color: 'var(--muted)' }}>You decide every finding</span>
          </div>

          {zeroFlag && (
            <NotNormalReadBanner
              show
              message={analysis?.read_disposition_message}
              npv={behaviorCard?.no_flag_npv}
            />
          )}

          {/* Real confirm/dismiss UI, framed. */}
          <div style={card}>
            <FindingsForm
              key={`form-${analysis.image_id}`}
              structured={structured}
              onChange={setStructured}
              history={history}
              onHistoryChange={setHistory}
              suggestions={suggestions}
            />
          </div>

          <DisagreementPrompts
            key={`disagree-${analysis.image_id}`}
            suggestions={suggestions}
            structured={structured}
            onConfirm={(key) => setStructured((prev) => ({ ...prev, [key]: true }))}
          />

          <div style={{ fontSize: 11.5, color: 'var(--faint)', lineHeight: 1.5, padding: '0 4px' }}>
            AI suggestions are decision support, not a diagnosis — a signal for review. The confidence
            shown is a raw ranking score at the operating point, not a calibrated probability of disease;
            where a per-label calibration exists the viewer shows a separate P≈. A licensed radiologist
            confirms every finding.
          </div>
        </>
      )}

      {active === 'report' && (
        <>
          {/* Patient identifiers (optional, client-only) live with the report,
              since that is the one place they are rendered (the exported PDF). */}
          <PatientIntake patient={patient} onChange={setPatient} />

          {/* Real ReportPanel: clinical/patient/differential sub-tabs, sign-off,
              provenance and jsPDF export — all preserved. */}
          <ReportPanel
            key={`report-${analysis.image_id}`}
            structured={structured}
            history={history}
            analysis={analysis}
            comparison={comparison}
            patient={patient}
            onFocusFinding={setFocusedFinding}
          />

          <WhatNotChecked notAssessed={analysis.not_assessed} />
        </>
      )}
    </div>
  )
}
