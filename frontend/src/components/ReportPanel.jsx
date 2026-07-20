import { useState } from 'react'
import { jsPDF } from 'jspdf'
import { generateReport, checkCompleteness } from '../api.js'
import { explainForFinding, distinctFlagged } from '../labelMap.js'
import { measurementWarnings } from '../measurementGuard.js'
import FindingExplanation from './FindingExplanation.jsx'
import FeedbackThumbs from './FeedbackThumbs.jsx'
import GlossaryText from './Glossary.jsx'

const TABS = [
  ['clinical', 'Clinical report'],
  ['patient', 'Patient summary'],
  ['differentials', 'Differentials'],
]

async function fetchDataUrl(url) {
  const res = await fetch(url)
  const blob = await res.blob()
  return await new Promise((resolve) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result)
    r.readAsDataURL(blob)
  })
}

// Estimated-size string for the PDF, only when the measurement workstream has
// populated the optional fields. Always framed as an estimate from attention.
function pdfMeasurement(f) {
  const parts = []
  if (typeof f.est_max_2d_mm === 'number' && isFinite(f.est_max_2d_mm)) {
    parts.push(`longest axis ~ ${f.est_max_2d_mm.toFixed(0)} mm`)
  }
  if (typeof f.est_area_mm2 === 'number' && isFinite(f.est_area_mm2)) {
    parts.push(`area ~ ${Math.round(f.est_area_mm2)} mm2`)
  }
  if (!parts.length) return null
  return `Estimated ${parts.join(', ')} - estimated from region of model attention; confirm with caliper.`
}

export default function ReportPanel({ structured, history, analysis, comparison, patient, onFocusFinding }) {
  const [report, setReport] = useState(null)
  const [tab, setTab] = useState('clinical')
  const [busy, setBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState(null)
  const [completeness, setCompleteness] = useState(null)
  const [reviewer, setReviewer] = useState('')
  const [attested, setAttested] = useState(false)
  // Provenance: the AI draft captured at generation time, so each section can be
  // marked "AI-drafted" until the reviewer edits it (then it reads "Edited by you").
  const [aiOriginal, setAiOriginal] = useState(null)

  const signedOff = attested && reviewer.trim().length > 0

  function buildPayload() {
    // PRIVACY: patient identifiers are intentionally NOT included here. They stay
    // client-side and are rendered only into the local PDF header (see exportPdf).
    return {
      // Do NOT assert a projection (PA) we can't confirm — a lateral/AP film
      // printing "PA" is a factual error in a clinician-facing document.
      modality: analysis?.source_format === 'dicom' ? 'Chest radiograph (DICOM)' : 'Chest radiograph (projection per image)',
      clinical_history: history,
      structured,
      vision_findings: analysis?.findings ?? [],
      comparison: comparison ?? null,
      triage: analysis?.triage ?? 'routine',
      attestation: { attested, reviewer_name: reviewer.trim() },
    }
  }

  async function handleCheck() {
    setBusy(true); setError(null)
    try {
      setCompleteness(await checkCompleteness(buildPayload()))
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function handleGenerate() {
    if (!signedOff) return
    setBusy(true); setError(null)
    try {
      const r = await generateReport(buildPayload())
      setReport(r)
      setAiOriginal({ clinical: r.clinical, patient: r.patient, differentials: r.differentials })
      setCompleteness(r.completeness ?? [])
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function exportPdf() {
    if (exporting) return
    setExporting(true)
    try {
    const doc = new jsPDF({ unit: 'pt', format: 'a4' })
    const margin = 48
    const width = doc.internal.pageSize.getWidth() - margin * 2
    let y = margin

    const line = (txt, size = 10, bold = false, gap = 13) => {
      doc.setFont('helvetica', bold ? 'bold' : 'normal')
      doc.setFontSize(size)
      doc.setTextColor(20)
      for (const l of doc.splitTextToSize(txt, width)) {
        if (y > 800) { doc.addPage(); y = margin }
        doc.text(l, margin, y); y += gap
      }
    }

    const addRegionImage = async (url) => {
      try {
        const dataUrl = await fetchDataUrl(url)
        const img = new Image(); img.src = dataUrl
        await new Promise((r) => { img.onload = r; img.onerror = r })
        const w = Math.min(width, 200)
        const h = img.naturalHeight ? (w * img.naturalHeight) / img.naturalWidth : w
        if (y + h + 14 > 800) { doc.addPage(); y = margin }
        doc.addImage(dataUrl, 'PNG', margin, y, w, h)
        y += h + 4
        doc.setFont('helvetica', 'italic'); doc.setFontSize(7); doc.setTextColor(90)
        doc.text('Region of model attention - not a lesion boundary.', margin, y); y += 12
        doc.setTextColor(20)
      } catch { /* image optional */ }
    }

    // (No diagonal watermark — it overlapped the body text. Safety framing is
    // carried by the title line + the disclaimer below.)
    doc.setFont('helvetica', 'bold'); doc.setFontSize(16)
    doc.text('Radiology Report (pending clinician sign-off)', margin, y); y += 22

    // Patient identifiers (optional, client-side only) — rendered ONLY here in the
    // locally-exported PDF; never transmitted to or stored by the server.
    const pid = patient || {}
    const pidParts = []
    if (pid.name) pidParts.push(`Patient: ${pid.name}`)
    if (pid.age) pidParts.push(`Age: ${pid.age}`)
    if (pid.phone) pidParts.push(`Contact: ${pid.phone}`)
    if (pidParts.length) {
      line(pidParts.join('     '), 10, true)
      line('Demo / de-identified data entered locally — not a verified medical record identifier.', 7)
      y += 2
    }

    doc.setFont('helvetica', 'normal'); doc.setFontSize(9)
    line(`Reviewer: ${reviewer.trim() || '-'}    Generated: ${new Date().toISOString().slice(0, 16).replace('T', ' ')}    Draft ID: ${analysis?.image_id || '-'}`, 9)
    line(`Triage: ${(report.triage || 'routine').toUpperCase()}${report.triage_reasons?.length ? ' - ' + report.triage_reasons.join('; ') : ''}`, 9)
    y += 6

    doc.setFont('helvetica', 'italic'); doc.setFontSize(8); doc.setTextColor(90)
    for (const l of doc.splitTextToSize(report.disclaimer, width)) {
      if (y > 800) { doc.addPage(); y = margin }
      doc.text(l, margin, y); y += 10
    }
    doc.setTextColor(20)
    y += 10

    // Per-finding region + explanation: ONE entry per RAW label (unique display
    // names => no duplicate cards; the raw model label is printed for provenance).
    const flagged = distinctFlagged(analysis?.findings || [])
    if (flagged.length) {
      line('FLAGGED FINDINGS - REGIONS & EXPLANATIONS', 12, true)
      line('Model-flagged signals for review - not confirmed diagnoses.', 8)
      y += 4
      for (const f of flagged) {
        const e = explainForFinding(f)
        line(`${e?.title || f.label} - model confidence ${Math.round(f.probability * 100)}%`, 11, true)
        line(`Raw model label: ${f.label}`, 8)
        if (f.heatmap_url) await addRegionImage(f.heatmap_url)
        const meas = pdfMeasurement(f)
        if (meas) line(meas, 8)
        if (e?.what) line(`What this is: ${e.what.charAt(0).toUpperCase() + e.what.slice(1)}.`, 9)
        if (e?.differentials?.length) line(`Differentials: ${e.differentials.join('; ')}`, 9)
        y += 8
      }
    }

    line('CLINICAL HISTORY', 12, true); line(history || 'Not provided.')
    y += 6
    line('CLINICAL REPORT', 12, true); line(report.clinical)
    y += 6
    line('PATIENT SUMMARY', 12, true); line(report.patient)
    y += 6
    line('DIFFERENTIAL CONSIDERATIONS', 12, true); line(report.differentials)
    const slug = (patient?.name || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
    doc.save(`radiology-report-${slug || 'study'}-${analysis?.image_id || 'draft'}.pdf`)
    } finally {
      setExporting(false)
    }
  }

  const warns = (completeness || []).filter((c) => c.severity === 'warn')
  const infos = (completeness || []).filter((c) => c.severity === 'info')

  const flaggedFindings = distinctFlagged(analysis?.findings || [])

  // Guardrail: measurements / laterality in the generated text that no
  // clinician-entered field or caliper backs (recomputes as the draft is edited).
  const measWarnings = measurementWarnings(report, structured, analysis)

  return (
    <div className="card">
      <div className="report-head">
        <h3>Report</h3>
      </div>

      {flaggedFindings.length > 0 && (
        <div className="explain-list">
          <h4>Finding explanations</h4>
          <p className="muted small">
            Plain-language explanation of each model-flagged finding. Hover a card to
            highlight its region in the viewer.
          </p>
          {flaggedFindings.map((f) => (
            <FindingExplanation key={f.label} finding={f} onFocus={onFocusFinding}
              imageSha256={analysis?.content_sha256} />
          ))}
        </div>
      )}

      <div className="signoff">
        <label className="field">
          Reviewing clinician (required to sign off)
          <input type="text" value={reviewer} placeholder="Name of licensed reviewer"
            onChange={(e) => setReviewer(e.target.value)} />
        </label>
        <label className="check">
          <input type="checkbox" checked={attested} onChange={(e) => setAttested(e.target.checked)} />
          I have reviewed the image and the findings above and adopt them as my own.
        </label>
      </div>

      <div className="toolbar-actions">
        <button className="btn" onClick={handleCheck} disabled={busy}>Check findings</button>
        <button className="btn primary" onClick={handleGenerate} disabled={busy || !signedOff}
          title={signedOff ? '' : 'Enter reviewer name and attest to enable'}>
          {busy ? 'Working…' : report ? 'Regenerate' : 'Generate report'}
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

      {completeness && (warns.length > 0 || infos.length > 0) && (
        <div className="completeness">
          <h4>Completeness check</h4>
          {warns.map((c, i) => <div key={`w${i}`} className="ck ck-warn">⚠ {c.message}</div>)}
          {infos.map((c, i) => <div key={`i${i}`} className="ck ck-info">ℹ {c.message}</div>)}
        </div>
      )}
      {completeness && warns.length === 0 && infos.length === 0 && (
        <p className="muted small">Completeness check: no gaps flagged.</p>
      )}

      {report && (() => {
        // A section is still "AI-drafted" until the reviewer changes its text.
        const edited = aiOriginal ? report[tab] !== aiOriginal[tab] : false
        return (
        <>
          <div className="prov-banner" role="note">
            <span className="prov-dot" aria-hidden="true" />
            <span>
              <strong>AI-generated draft.</strong> The text below was drafted by the
              report engine from your structured findings — not written by a clinician.
              Review and edit every section before use; the reviewer is responsible for
              the final content.
            </span>
          </div>
          {measWarnings.length > 0 && (
            <div className="meas-guard" role="alert">
              <h4>⚠ Unverified measurements / laterality</h4>
              <p className="muted small">
                These specifics appear in the generated text but are not backed by a
                clinician-entered field or a caliper measurement. Confirm each against
                the image, or remove it from the draft before sign-off.
              </p>
              <ul className="meas-guard-list">
                {measWarnings.map((w, i) => (
                  <li key={`${w.type}-${w.tab}-${i}`}>
                    <span className="meas-guard-token">“{w.text}”</span>
                    <span className="meas-guard-where">
                      {w.tab === 'patient' ? 'patient summary' : 'clinical report'}
                    </span>
                    <span className="meas-guard-msg">
                      Unverified {w.type === 'laterality' ? 'side' : 'measurement'} — confirm or remove
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="tabs sub-tabs" role="tablist">
            {TABS.map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id}
                className={tab === id ? 'tab active' : 'tab'} onClick={() => setTab(id)}>
                {label}
              </button>
            ))}
          </div>
          <div className="prov-section-head">
            <span className={edited ? 'prov-badge prov-badge-human' : 'prov-badge prov-badge-ai'}>
              {edited ? 'Edited by you' : 'AI-drafted — edit freely'}
            </span>
          </div>
          <textarea className={edited ? 'report-text' : 'report-text prov-ai-text'} rows={16} value={report[tab]}
            onChange={(e) => setReport({ ...report, [tab]: e.target.value })} />
          {tab === 'patient' && (
            <div className="patient-view">
              <p className="muted small">
                Patient-friendly view — tap a highlighted word to see what it means.
              </p>
              <GlossaryText text={report.patient} />
            </div>
          )}
          <p className="muted small">
            Editable draft · generated by {report.generator === 'template'
              ? 'the built-in template engine (no LLM key)'
              : report.generator} · a clinician must review before any use.
          </p>
          <FeedbackThumbs
            target="report"
            label={analysis?.top_finding || null}
            modelNote={`report draft · generator ${report.generator} · triage ${report.triage || 'routine'}`}
            prompt="Was this report draft useful?"
          />
        </>
        )
      })()}
    </div>
  )
}
