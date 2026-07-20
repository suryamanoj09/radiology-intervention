import { useState } from 'react'
import { jsPDF } from 'jspdf'
import { generateCtReport, generateMrReport } from '../api.js'

// CtReportPanel — the CT/MRI report rail, at UX parity with the chest X-ray
// ReportPanel (sign-off gate + local jsPDF export) but at DELIBERATE sub-parity in
// CLAIMS. It renders the backend's CT/MRI report shape (services/ct_report.py):
// four sections — Technique / Measurements / Research candidates / Patient note —
// plus the mandatory disclaimer. It is a SUMMARY of clinician-CONFIRMED, UNVALIDATED
// research candidates + the clinician's own anatomy measurements. It is NOT a
// diagnosis, NOT triage, NOT a calibrated probability, and carries NO differentials.
//
// Honesty is structural: the backend forces the modality, strips any diagnostic /
// probability phrasing server-side, and guarantees not_a_normal_result. This panel
// renders that framing PROMINENTLY and never shows a candidate salience as a %.

// Map the viewer's measurement objects -> backend CtMeasurement shape. ROI intensity
// stats are echoed verbatim (HU for CT, arbitrary a.u. for MR — never tissue-typed).
function toCtMeasurements(list) {
  return (list || []).map((m) => {
    if (m.type === 'roi' && m.roi) {
      return {
        kind: 'roi', unit: m.roi.unit || '',
        mean: m.roi.mean, sd: m.roi.sd, min: m.roi.min, max: m.roi.max,
        area_mm2: m.roi.area_mm2, slice_index: m.sliceIndex,
      }
    }
    if (m.type === 'length') return { kind: 'length', unit: 'mm', value: m.value, slice_index: m.sliceIndex }
    if (m.type === 'angle') return { kind: 'angle', unit: 'deg', value: m.value, slice_index: m.sliceIndex }
    return null
  }).filter(Boolean)
}

// Map a CONFIRMED research candidate -> backend CtConfirmedCandidate shape. Confirming
// attests the REGION only, never a disease. NO probability is carried — only the coarse
// non-probabilistic salience band.
function toCtCandidates(list) {
  return (list || []).map((c) => ({
    label: c.label, kind: c.kind || '',
    salience_band: c.salience_band || 'low',
    est_max_mm: c.est_max_mm ?? null,
    mean_hu: c.mean_hu ?? null,
    slice_index: c.region?.slice_index ?? null,
    note: '',
  }))
}

export default function CtReportPanel({
  modality = 'CT',          // 'CT' | 'MR'
  technique = '',
  seriesId = null,
  measurements = [],        // raw viewer measurement objects
  confirmedCandidates = [], // raw CONFIRMED CandidateFinding objects
}) {
  const [history, setHistory] = useState('')
  const [tech, setTech] = useState(technique)
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState(null)
  const [reviewer, setReviewer] = useState('')
  const [attested, setAttested] = useState(false)

  const isMr = modality === 'MR'
  const signedOff = attested && reviewer.trim().length > 0
  const mappedMeas = toCtMeasurements(measurements)
  const mappedCands = toCtCandidates(confirmedCandidates)

  function buildPayload() {
    return {
      technique: (tech || '').trim(),
      clinical_history: history,
      series_id: seriesId || null,
      measurements: mappedMeas,
      candidates: mappedCands,
    }
  }

  async function handleGenerate() {
    if (!signedOff) return
    setBusy(true); setError(null)
    try {
      const fn = isMr ? generateMrReport : generateCtReport
      const r = await fn(buildPayload())
      setReport(r)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  function exportPdf() {
    if (!report || exporting) return
    setExporting(true)
    try {
    const doc = new jsPDF({ unit: 'pt', format: 'a4' })
    const margin = 48
    const width = doc.internal.pageSize.getWidth() - margin * 2
    let y = margin
    const line = (txt, size = 10, bold = false, gap = 13, color = 20) => {
      doc.setFont('helvetica', bold ? 'bold' : 'normal')
      doc.setFontSize(size); doc.setTextColor(color)
      for (const l of doc.splitTextToSize(txt || '', width)) {
        if (y > 800) { doc.addPage(); y = margin }
        doc.text(l, margin, y); y += gap
      }
    }

    doc.setFont('helvetica', 'bold'); doc.setFontSize(15)
    doc.text(`${report.modality} research summary (pending clinician sign-off)`, margin, y); y += 20
    line('RESEARCH SUMMARY OF UNVALIDATED CANDIDATES + MEASUREMENTS — NOT A DIAGNOSIS.', 9, true, 12, 160)
    line('Not triage, not a probability, no differentials. A research tool, not a medical device.', 8, false, 11, 90)
    y += 4
    line(`Reviewer: ${reviewer.trim() || '-'}    Generated: ${new Date().toISOString().slice(0, 16).replace('T', ' ')}${seriesId ? `    Series: ${seriesId}` : ''}`, 9)
    y += 6
    line(report.not_a_normal_result_message, 8, false, 11, 150)
    y += 8
    line(report.technique_section, 10); y += 6
    line(report.measurements_section, 10); y += 6
    line(report.candidates_section, 10); y += 6
    line(report.patient_note, 10); y += 8
    doc.setDrawColor(200); doc.line(margin, y, margin + width, y); y += 12
    line('DISCLAIMER', 9, true); line(report.disclaimer, 8, false, 11, 90)
    doc.save(`${report.modality.toLowerCase()}-research-summary-${seriesId || 'study'}.pdf`)
    } finally {
      setExporting(false)
    }
  }

  const section = (title, text) => (
    <div className="ctr-section">
      <h4>{title}</h4>
      <pre className="ctr-text">{text}</pre>
    </div>
  )

  return (
    <div className="card ctr-panel">
      <div className="report-head"><h3>{modality} research summary</h3></div>

      {/* PROMINENT honest framing — shown before AND after generation. */}
      <div className="ctr-framing" role="alert">
        <strong>Research summary of unvalidated candidates + measurements — NOT a diagnosis.</strong>
        <span>
          This is a summary of the research candidates a clinician CONFIRMED as regions to
          review, plus the clinician's own measurements. It is not triage, not a probability,
          and carries no differentials. The {modality} AI is unvalidated research — it may miss
          real disease or flag normal anatomy — and is not a medical device.
        </span>
      </div>

      {/* Draft composition — what will be summarised. */}
      <div className="ctr-draft">
        <label className="field">
          Technique / series
          <input type="text" value={tech} placeholder={`${modality} study`}
            onChange={(e) => setTech(e.target.value)} />
        </label>
        <label className="field">
          Clinical history (optional)
          <textarea rows={2} value={history} placeholder="Clinical history / indication"
            onChange={(e) => setHistory(e.target.value)} />
        </label>
        <div className="ctr-counts">
          <span><b>{mappedMeas.length}</b> measurement{mappedMeas.length === 1 ? '' : 's'}</span>
          <span><b>{mappedCands.length}</b> confirmed candidate{mappedCands.length === 1 ? '' : 's'}</span>
          <span className="muted small">
            Only candidates you CONFIRMED in the Candidate findings panel are included.
            ROI intensity is {isMr ? 'arbitrary a.u. (not tissue-specific)' : 'HU (Hounsfield)'}.
          </span>
        </div>
      </div>

      {/* Mandatory sign-off gate (parity with the X-ray report). */}
      <div className="signoff">
        <label className="field">
          Reviewing clinician (required to sign off)
          <input type="text" value={reviewer} placeholder="Name of licensed reviewer"
            onChange={(e) => setReviewer(e.target.value)} />
        </label>
        <label className="check">
          <input type="checkbox" checked={attested} onChange={(e) => setAttested(e.target.checked)} />
          I have reviewed the images and the confirmed candidates, and I understand this is a
          research summary and not a diagnosis.
        </label>
      </div>

      <div className="toolbar-actions">
        <button className="btn primary" onClick={handleGenerate} disabled={busy || !signedOff}
          title={signedOff ? '' : 'Enter reviewer name and attest to enable'}>
          {busy ? 'Working…' : report ? 'Regenerate summary' : 'Generate research summary'}
        </button>
        {report && (
          <button className="btn" onClick={exportPdf} disabled={exporting}>
            {exporting ? 'Exporting…' : 'Export PDF'}
          </button>
        )}
      </div>
      {report && (
        <p style={{ margin: '4px 0 0', fontSize: '0.78rem', color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>
          Downloads a local PDF to this device (your Downloads folder) - not saved on the server; not a signed medical record.
        </p>
      )}
      {!signedOff && <p className="muted small">Sign-off required before generating or exporting.</p>}
      {error && <div className="error-bar" role="alert">{error}</div>}

      {report && (
        <>
          {/* The "absence is not normality" guarantee, from the CONTRACT — always shown,
              emphasised when nothing was confirmed. */}
          <div className={report.candidate_count === 0 ? 'ctr-notnormal ctr-notnormal-empty' : 'ctr-notnormal'} role="alert">
            {report.candidate_count === 0
              ? <><strong>No candidates were confirmed — this is NOT a "normal" result.</strong> {report.not_a_normal_result_message}</>
              : report.not_a_normal_result_message}
          </div>

          {section('Technique', report.technique_section)}
          {section('Measurements', report.measurements_section)}
          {section('Research candidates', report.candidates_section)}
          {section('Patient note', report.patient_note)}

          <div className="ctr-disclaimer" role="note">{report.disclaimer}</div>
          <p className="muted small">
            Deterministic template summary (generator: {report.generator}) · research_only ·
            not validated · a licensed clinician is responsible for interpretation. No impression,
            no differentials, no probability by design.
          </p>
        </>
      )}
    </div>
  )
}
