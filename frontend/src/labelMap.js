// UNIQUE, faithful display name per RAW model label. RULE: a display name may only
// GENERALIZE the raw label, never SPECIALIZE it. The model emits a generic
// `Fracture` (CheXpert-derived from ANY fracture mention — clavicle/humerus/
// vertebral/rib), so it renders "Fracture (site unspecified)" — NEVER "Rib
// fracture" (the model never localized a bone). Every raw label maps to a distinct
// string, so two labels can never collapse into one duplicate card.
// Keys MUST equal model.pathologies exactly (asserted in backend test).
export const RAW_DISPLAY = {
  Atelectasis: 'Atelectasis',
  Consolidation: 'Consolidation',
  Infiltration: 'Infiltration',
  Pneumothorax: 'Pneumothorax',
  Edema: 'Pulmonary edema',
  Emphysema: 'Emphysema',
  Fibrosis: 'Fibrosis',
  Effusion: 'Pleural effusion',
  Pneumonia: 'Pneumonia',
  Pleural_Thickening: 'Pleural thickening',
  Cardiomegaly: 'Cardiomegaly',
  Nodule: 'Nodule',
  Mass: 'Mass',
  Hernia: 'Hernia',
  'Lung Lesion': 'Lung lesion',
  Fracture: 'Fracture (site unspecified)',
  'Lung Opacity': 'Lung opacity',
  'Enlarged Cardiomediastinum': 'Enlarged cardiomediastinum',
}

// Mirror of backend services/label_map.py — vision label -> structured key.
// NOTE: this many-to-one grouping is ONLY for prefilling the clinician's structured
// FORM + disagreement prompts + completeness (a clinician confirms "consolidation"
// once). It is NOT the finding-card display identity — that is RAW_DISPLAY above,
// which is one-to-one so cards never duplicate.
export const LABEL_TO_KEY = {
  Nodule: 'nodule_present',
  Mass: 'nodule_present',
  'Lung Lesion': 'nodule_present',
  Effusion: 'pleural_effusion',
  Pneumothorax: 'pneumothorax',
  Consolidation: 'consolidation',
  Pneumonia: 'consolidation',
  Infiltration: 'consolidation',
  'Lung Opacity': 'consolidation',
  Cardiomegaly: 'cardiomegaly',
  'Enlarged Cardiomediastinum': 'cardiomegaly',
  Fracture: 'rib_fracture',
}

export const KEY_DISPLAY = {
  nodule_present: 'Pulmonary nodule / mass',
  pleural_effusion: 'Pleural effusion',
  pneumothorax: 'Pneumothorax',
  consolidation: 'Consolidation / opacity',
  cardiomegaly: 'Enlarged cardiac silhouette',
  rib_fracture: 'Rib fracture',
}

// Structured key -> words that count as "addressed in free text".
// Mirror of backend services/label_map.py KEY_SYNONYMS — keep in sync.
export const KEY_SYNONYMS = {
  nodule_present: ['nodule', 'mass', 'lesion'],
  pleural_effusion: ['effusion', 'fluid'],
  pneumothorax: ['pneumothorax', 'ptx'],
  consolidation: ['consolidation', 'opacity', 'pneumonia', 'infiltrate', 'infiltration', 'airspace'],
  cardiomegaly: ['cardiomegaly', 'enlarged heart', 'cardiac silhouette', 'heart size'],
  rib_fracture: ['fracture', 'rib'],
}

// True when the clinician has addressed a finding in free text (mirrors backend
// label_map.mentioned_in_text). Used so disagreement prompts don't nag about a
// finding the clinician already wrote up in narrative form.
export function mentionedInText(key, text) {
  const t = (text || '').toLowerCase()
  return (KEY_SYNONYMS[key] || []).some((syn) => t.includes(syn))
}

// Structured key -> explanation-map key (mirrors backend templates.py keys).
const STRUCT_TO_EXPLAIN = {
  nodule_present: 'nodule',
  pleural_effusion: 'pleural_effusion',
  pneumothorax: 'pneumothorax',
  consolidation: 'consolidation',
  cardiomegaly: 'cardiomegaly',
  rib_fracture: 'rib_fracture',
}

// Deterministic, human-curated explanation content. Mirror of backend
// services/templates.py (PATIENT_EXPLANATIONS + DIFFERENTIALS_MAP). NEVER
// model-generated. Keep in sync with the backend if that source changes.
export const FINDING_EXPLANATIONS = {
  nodule: {
    title: 'Pulmonary nodule / mass',
    what: 'a small spot was seen in the lung. Many lung spots are harmless scars from old infections, but follow-up imaging may be advised to be sure',
    differentials: [
      'Granuloma (prior infection)',
      'Primary lung neoplasm',
      'Metastasis',
      'Hamartoma',
      'Intrapulmonary lymph node',
    ],
  },
  pleural_effusion: {
    title: 'Pleural effusion',
    what: 'there is some extra fluid in the space around the lung. This can have many causes, interpreted together with the clinical picture',
    differentials: [
      'Congestive heart failure',
      'Parapneumonic effusion',
      'Malignant effusion',
      'Hypoalbuminemia',
    ],
  },
  pneumothorax: {
    title: 'Pneumothorax',
    what: 'some air has leaked into the space around the lung, which can make the lung less inflated than normal. The care team decides if it needs treatment or monitoring',
    differentials: [
      'Spontaneous pneumothorax',
      'Traumatic pneumothorax',
      'Iatrogenic (post-procedure)',
    ],
  },
  consolidation: {
    title: 'Consolidation / airspace opacity',
    what: 'part of the lung looks denser than normal, which is often seen with an infection such as pneumonia',
    differentials: [
      'Community-acquired pneumonia',
      'Aspiration',
      'Pulmonary edema',
      'Atelectasis',
    ],
  },
  cardiomegaly: {
    title: 'Enlarged cardiac silhouette',
    what: 'the shadow of the heart looks larger than usual on this image. This is a clue, not a diagnosis - sometimes it is just how the picture was taken',
    differentials: [
      'Dilated cardiomyopathy',
      'Pericardial effusion',
      'Multivalvular heart disease',
      'Technical factor (AP projection magnification)',
    ],
  },
  rib_fracture: {
    title: 'Rib fracture',
    what: 'there may be a break in one of the ribs. Rib fractures usually heal on their own, but pain control and follow-up matter',
    differentials: [
      'Traumatic fracture',
      'Pathologic fracture (underlying lesion)',
      'Stress fracture (e.g., chronic cough)',
    ],
  },
}

// Resolve a vision Finding to a card: the TITLE is the unique RAW_DISPLAY name (so
// two distinct labels never render the same title), the raw model label is exposed,
// and the what/differentials body comes from the clinically-grouped curated content
// (shared body is fine; the identity is the raw label). Never an LLM.
export function explainForFinding(finding) {
  if (!finding || !finding.label) return null
  const title = RAW_DISPLAY[finding.label] || finding.label
  const structKey = LABEL_TO_KEY[finding.label]
  const key = structKey && STRUCT_TO_EXPLAIN[structKey]
  const entry = key && FINDING_EXPLANATIONS[key]
  return {
    key: key || null,
    rawLabel: finding.label,
    title,
    what: entry?.what || null,
    differentials: entry?.differentials || [],
  }
}

// Distinct FLAGGED findings, one per RAW label (raw labels are already unique, so
// this is a stable identity/sort — never a collapse of distinct labels into one).
export function distinctFlagged(findings) {
  const seen = new Set()
  const out = []
  for (const f of findings || []) {
    if (!f.flagged || seen.has(f.label)) continue
    seen.add(f.label)
    out.push(f)
  }
  return out.sort((a, b) => b.probability - a.probability)
}

// Distinct AI suggestions (deduped by structured key) from a set of flagged findings.
export function aiSuggestions(findings) {
  const byKey = new Map()
  for (const f of findings || []) {
    if (!f.flagged) continue
    const key = LABEL_TO_KEY[f.label]
    if (!key) continue
    const prev = byKey.get(key)
    if (!prev || f.probability > prev.probability) {
      byKey.set(key, { key, label: f.label, probability: f.probability })
    }
  }
  return [...byKey.values()].sort((a, b) => b.probability - a.probability)
}

export function emptyStructured() {
  return {
    reviewed_no_acute: false,
    nodule_present: false,
    nodule_size_mm: null,
    nodule_location: null,
    pleural_effusion: false,
    effusion_side: null,
    pneumothorax: false,
    pneumothorax_side: null,
    consolidation: false,
    consolidation_location: null,
    cardiomegaly: false,
    rib_fracture: false,
    free_text: '',
  }
}
