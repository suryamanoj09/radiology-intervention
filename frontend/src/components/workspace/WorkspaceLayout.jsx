import DisclaimerBanner from '../DisclaimerBanner.jsx'
import CompetenceBanner from '../CompetenceBanner.jsx'
import TriageBanner from '../TriageBanner.jsx'
import UploadPanel from '../UploadPanel.jsx'
import Viewer from '../Viewer.jsx'
import DicomViewer from '../DicomViewer.jsx'
import StudyContextBar from './StudyContextBar.jsx'
import AiRail from './AiRail.jsx'

// WorkspaceLayout — WF5 redesign of the analyzer workspace.
//
// This is a COMPOSITION SHELL. It re-arranges + re-skins the design's polished
// 3-pane layout (RadAssist.dc.html 690-861) while rendering the REAL functional
// components (Viewer, FindingsForm, DisagreementPrompts, ReportPanel, banners …)
// unchanged. It duplicates NONE of their logic — every piece of state and every
// handler is passed in as a prop and threaded straight through.
//
// X-RAY vs CT/MRI split: for tab==='ct'|'mri' we render the existing DicomViewer
// path untouched (WF7 owns CT/MRI parity). Only tab==='xray' gets the new grid.

const viewerFrame = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 14,
  padding: 12,
  boxShadow: 'var(--shadow-sm)',
}

export default function WorkspaceLayout({
  // modality
  tab,
  setTab,
  // analysis + review state
  analysis,
  suggestions,
  structured,
  setStructured,
  history,
  setHistory,
  patient,
  setPatient,
  behaviorCard,
  focusedFinding,
  setFocusedFinding,
  // async / status
  busySlot,
  error,
  // prior + comparison
  prior,
  comparison,
  comparisonError,
  // upload handlers
  onUpload,
  onPriorUpload,
  onClearStudy,
  onClearPrior,
  // draft recovery
  draftRestored,
  onDismissDraft,
  // viewer focus toggle
  railsCollapsed,
  setRailsCollapsed,
  // analyzer utility modal openers
  onOpenInfo,
  onOpenLimitations,
  onOpenFailures,
  onOpenAdmin,
}) {
  const contextBar = (
    <StudyContextBar
      analysis={analysis}
      tab={tab}
      setTab={setTab}
      railsCollapsed={railsCollapsed}
      setRailsCollapsed={setRailsCollapsed}
      onOpenInfo={onOpenInfo}
      onOpenLimitations={onOpenLimitations}
      onOpenFailures={onOpenFailures}
      onOpenAdmin={onOpenAdmin}
    />
  )

  // ---- CT / MRI: existing DicomViewer path (unchanged) --------------------
  if (tab !== 'xray') {
    return (
      <div id="ws-root" style={{ padding: '22px 26px 40px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <DisclaimerBanner />
        {contextBar}
        <main className="layout single">
          <DicomViewer modality={tab} />
        </main>
      </div>
    )
  }

  const abstain = analysis && analysis.competence === 'abstain'
  const active = analysis && !abstain

  return (
    <div id="ws-root" style={{ padding: '22px 26px 40px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <DisclaimerBanner />
      {contextBar}

      {analysis && (
        <CompetenceBanner
          competence={analysis.competence}
          reasons={analysis.audit_reasons}
          oodScore={analysis.ood_score}
        />
      )}
      {active && <TriageBanner triage={analysis.triage} reasons={analysis.triage_reasons} />}

      {draftRestored && analysis && (
        <div className="draft-note" role="status">
          ↩ Restored your unsaved study and report draft from this browser.
          <button className="btn btn-small" onClick={onDismissDraft}>Dismiss</button>
        </div>
      )}
      {error && <div className="error-bar" role="alert">{error}</div>}

      {/* Upload / prior-compare entry — always reachable (current + prior slots). */}
      <UploadPanel
        onUpload={onUpload}
        onPriorUpload={onPriorUpload}
        onClear={onClearStudy}
        onClearPrior={onClearPrior}
        busySlot={busySlot}
        hasPrior={!!prior}
        hasCurrent={!!analysis}
      />

      {/* ABSTAIN — image was not scored. */}
      {abstain && (
        <div className="card">
          <h3>Not analyzed</h3>
          <p className="muted">
            This image was not scored because it does not appear to be a chest radiograph.
            Upload a frontal chest X-ray to get findings and a report.
          </p>
        </div>
      )}

      {/* NO analysis yet — how-it-works empty state. */}
      {!analysis && (
        <div className="card empty-state">
          <h3>How it works</h3>
          <ol>
            <li>Upload a chest X-ray (PNG, JPG, or DICOM).</li>
            <li>The model flags possible findings and highlights its region of attention — as <em>suggestions</em>, unchecked by default.</li>
            <li>You confirm, edit, or dismiss each one — nothing is confirmed until you say so.</li>
            <li>Sign off, then generate a clinical report, patient-friendly summary, and reference differentials.</li>
          </ol>
          {behaviorCard?.available && (
            <div className="landing-metrics">
              <h4>Measured, not claimed</h4>
              <div className="lm-grid">
                {behaviorCard?.calibration?.overall?.ece != null && (
                  <div className="lm-cell"><b>ECE {behaviorCard.calibration.overall.ece}</b>
                    <span>calibration error — the raw % is a score, not a probability</span></div>
                )}
                {behaviorCard?.anatomy_gate?.fn_rate != null && (
                  <div className="lm-cell"><b>{Math.round(behaviorCard.anatomy_gate.fn_rate * 100)}%</b>
                    <span>anatomy-gate false-negative rate (it can drop true findings)</span></div>
                )}
                {behaviorCard?.subgroup?.groups?.PA?.micro_auroc != null && (
                  <div className="lm-cell"><b>PA {behaviorCard.subgroup.groups.PA.micro_auroc} / AP {behaviorCard.subgroup.groups.AP?.micro_auroc}</b>
                    <span>AUROC by view — performance shifts on portable films</span></div>
                )}
              </div>
              <button className="btn" onClick={onOpenFailures}>
                🔬 See where this system fails (measured cases)
              </button>
            </div>
          )}
        </div>
      )}

      {/* ACTIVE analysis — the design's 2-pane grid. */}
      {active && (
        <div
          className="ws-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: railsCollapsed ? 'minmax(0,1fr)' : 'minmax(0,1.4fr) minmax(0,1fr)',
            gap: 16,
          }}
        >
          {/* LEFT — the real Viewer inside a design-styled frame. */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
            <div style={viewerFrame}>
              <Viewer
                key={analysis.image_id}
                analysis={analysis}
                behaviorCard={behaviorCard}
                focusedFinding={focusedFinding}
                onFocusFinding={setFocusedFinding}
              />
            </div>

            {comparisonError && (
              <div className="card"><p className="muted">Prior comparison unavailable: {comparisonError}</p></div>
            )}
            {comparison && (
              <div className="card">
                <h3>Comparison with prior study</h3>
                <p className="muted">{comparison.summary}</p>
                <p className="muted small">Change in model confidence — not confirmed disease progression.</p>
                <table className="cmp-table">
                  <thead>
                    <tr><th>Finding</th><th>Prior</th><th>Current</th><th>Change</th></tr>
                  </thead>
                  <tbody>
                    {comparison.rows.map((r) => (
                      <tr key={r.label}>
                        <td>{r.label}</td>
                        <td>{Math.round(r.prior_probability * 100)}%</td>
                        <td>{Math.round(r.current_probability * 100)}%</td>
                        <td><span className={`chg chg-${r.change}`}>{r.change}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* RIGHT — AI findings / Report rail (hidden in focus-viewer mode). */}
          {!railsCollapsed && (
            <AiRail
              analysis={analysis}
              suggestions={suggestions}
              structured={structured}
              setStructured={setStructured}
              history={history}
              setHistory={setHistory}
              patient={patient}
              setPatient={setPatient}
              behaviorCard={behaviorCard}
              comparison={comparison}
              setFocusedFinding={setFocusedFinding}
            />
          )}
        </div>
      )}
    </div>
  )
}
