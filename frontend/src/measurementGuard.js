// Measurement / laterality guardrail (frontend-only, deterministic — no LLM).
//
// Purpose: LLMs cheerfully invent specifics. A generated chest-radiograph report
// can print "a 12 mm nodule in the left lower lobe" even when the clinician never
// measured anything and never picked a side. Those numbers/sides can leak into a
// signed document and be read as fact. This module scans the *generated* report
// text (clinical + patient) for any measurement (mm/cm) or left/right/bilateral
// laterality that is NOT backed by a clinician-entered structured field or a
// caliper (region-of-attention) estimate, so the UI can flag it in amber for the
// reviewer to confirm or delete before sign-off.
//
// Framing note: this NEVER rewrites the report. It only surfaces unverified
// specifics — the human stays the source of truth.

// A number immediately followed by mm/cm, optionally an area suffix (2 / ² / ^2).
const MEAS_SRC = '(\\d+(?:\\.\\d+)?)\\s*(mm|cm)(2|²|\\^2)?'
// Anatomic laterality words. \b keeps "upright" / "copyright" from matching.
const LAT_SRC = '\\b(left|right|bilateral)\\b'

function toMm(value, unit) {
  return unit.toLowerCase() === 'cm' ? value * 10 : value
}

function toMm2(value, unit) {
  // 1 cm² = 100 mm²
  return unit.toLowerCase() === 'cm' ? value * 100 : value
}

// Pull explicit mm/cm measurements out of a clinician-typed free-text string.
// Whatever the clinician wrote themselves counts as "entered", so a number they
// typed backs the same number appearing in the generated narrative.
function extractMeasurements(text) {
  const out = { lengthsMm: [], areasMm2: [] }
  if (!text) return out
  const re = new RegExp(MEAS_SRC, 'gi')
  let m
  while ((m = re.exec(text)) !== null) {
    const val = parseFloat(m[1])
    if (!isFinite(val)) continue
    if (m[3]) out.areasMm2.push(toMm2(val, m[2]))
    else out.lengthsMm.push(toMm(val, m[2]))
  }
  return out
}

// Build the set of measurements/laterality the report is ALLOWED to state,
// from clinician-confirmed structured fields + caliper estimates on the vision
// findings + anything the clinician typed into free text.
export function collectVerified(structured, analysis) {
  const s = structured || {}
  const lengthsMm = []
  const areasMm2 = []
  let left = false
  let right = false

  // Clinician-measured nodule size (mm), entered in FindingsForm.
  if (typeof s.nodule_size_mm === 'number' && isFinite(s.nodule_size_mm)) {
    lengthsMm.push(s.nodule_size_mm)
  }

  // Measurements the clinician typed into the free-text box.
  const ft = extractMeasurements(s.free_text)
  lengthsMm.push(...ft.lengthsMm)
  areasMm2.push(...ft.areasMm2)

  // Caliper estimates from the region of model attention (already framed as
  // estimates in the PDF). These legitimately back a stated ~size.
  for (const f of analysis?.findings || []) {
    if (typeof f.est_max_2d_mm === 'number' && isFinite(f.est_max_2d_mm)) lengthsMm.push(f.est_max_2d_mm)
    if (typeof f.est_area_mm2 === 'number' && isFinite(f.est_area_mm2)) areasMm2.push(f.est_area_mm2)
  }

  // Laterality from clinician-selected side fields.
  for (const side of [s.effusion_side, s.pneumothorax_side]) {
    if (side === 'left') left = true
    else if (side === 'right') right = true
    else if (side === 'bilateral') { left = true; right = true }
  }

  // Laterality implied by lobe location codes (RUL/RML/RLL vs LUL/LLL).
  for (const loc of [s.nodule_location, s.consolidation_location]) {
    if (typeof loc === 'string' && loc.length) {
      const c = loc[0].toUpperCase()
      if (c === 'R') right = true
      if (c === 'L') left = true
    }
  }

  // Laterality the clinician wrote in free text.
  const ftLower = (s.free_text || '').toLowerCase()
  if (/\bleft\b/.test(ftLower)) left = true
  if (/\bright\b/.test(ftLower)) right = true
  if (/\bbilateral\b/.test(ftLower)) { left = true; right = true }

  return { lengthsMm, areasMm2, left, right }
}

function backedLength(mm, verified) {
  // Lenient tolerance: prefer under-flagging a genuine clinician measurement over
  // nagging about a value the report merely rounded (e.g. 12.3 -> "12 mm").
  return verified.lengthsMm.some((v) => Math.abs(v - mm) <= Math.max(2, mm * 0.2))
}

function backedArea(mm2, verified) {
  return verified.areasMm2.some((v) => Math.abs(v - mm2) <= Math.max(4, mm2 * 0.25))
}

// Scan one text blob; return raw (un-deduped) warnings tagged with the tab.
export function scanReportText(text, tab, verified) {
  const warnings = []
  if (!text) return warnings

  const measRe = new RegExp(MEAS_SRC, 'gi')
  let m
  while ((m = measRe.exec(text)) !== null) {
    const val = parseFloat(m[1])
    if (!isFinite(val)) continue
    let ok
    if (m[3]) ok = backedArea(toMm2(val, m[2]), verified)
    else ok = backedLength(toMm(val, m[2]), verified)
    if (!ok) warnings.push({ type: 'measurement', tab, text: m[0].trim() })
  }

  const latRe = new RegExp(LAT_SRC, 'gi')
  while ((m = latRe.exec(text)) !== null) {
    const word = m[1].toLowerCase()
    let ok
    if (word === 'left') ok = verified.left
    else if (word === 'right') ok = verified.right
    else ok = verified.left && verified.right // bilateral needs both sides backed
    if (!ok) warnings.push({ type: 'laterality', tab, text: m[0] })
  }
  return warnings
}

// Top-level entry: deduped warnings across the clinical + patient report text.
// Returns [] when nothing is generated yet or everything is backed.
export function measurementWarnings(report, structured, analysis) {
  if (!report) return []
  const verified = collectVerified(structured, analysis)
  const raw = [
    ...scanReportText(report.clinical, 'clinical', verified),
    ...scanReportText(report.patient, 'patient', verified),
  ]
  const seen = new Set()
  const out = []
  for (const w of raw) {
    const key = `${w.type}|${w.tab}|${w.text.toLowerCase()}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(w)
  }
  return out
}
