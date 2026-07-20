import { useState } from 'react'

// A small, human-curated glossary of common chest X-ray terms, each defined in
// plain, 6th-grade language. Definitions avoid false reassurance and avoid
// stating a diagnosis — they explain what a word means, not what it means for
// the patient. Keys MUST be lowercase (matching is case-insensitive).
export const GLOSSARY = {
  'nodule': 'A small round spot in the lung. Many are harmless, like scars from an old infection, but some are checked further to be safe.',
  'pleural effusion': 'Extra fluid in the thin space around the lungs.',
  'effusion': 'A build-up of extra fluid where it does not usually collect — here, around the lungs.',
  'pneumothorax': 'Air that has leaked into the space around a lung, which can stop the lung from filling all the way.',
  'consolidation': 'An area of lung that looks more solid than normal, often because the tiny air spaces are filled with fluid.',
  'cardiomegaly': 'A heart shadow that looks larger than usual on the image. Sometimes this is just how the picture was taken.',
  'rib fracture': 'A crack or break in one of the ribs.',
  'pleura': 'The thin lining that wraps around the lungs and lines the inside of the chest.',
  'mediastinum': 'The space in the middle of the chest, between the lungs, where the heart and main blood vessels sit.',
  'opacity': 'An area that looks whiter or more solid than normal on an X-ray.',
  'atelectasis': 'A part of the lung that is not fully open, or has partly collapsed.',
  'edema': 'Extra fluid that has built up in the body’s tissue. In the lungs this is called pulmonary edema.',
  'pneumonia': 'An infection in the lung that causes swelling and fluid in the air spaces.',
  'granuloma': 'A small clump of healed tissue, often left behind after an old infection has cleared up.',
  'radiograph': 'A picture made with a small amount of X-ray energy — a chest X-ray is one kind.',
  'follow-up': 'A later check — such as another scan, a test, or a visit — to see how something stays the same or changes over time.',
}

const SORTED = Object.keys(GLOSSARY).sort((a, b) => b.length - a.length)

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Longest phrases first so "pleural effusion" wins over "effusion".
const TERM_RE = new RegExp('\\b(' + SORTED.map(escapeRegExp).join('|') + ')\\b', 'gi')

function Term({ term, definition }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="glossary-term-wrap">
      <button
        type="button"
        className="glossary-term"
        aria-expanded={open}
        title={definition}
        onClick={() => setOpen((o) => !o)}
      >
        {term}
      </button>
      {open && (
        <span className="glossary-pop" role="tooltip">
          <strong>{term}:</strong> {definition}
        </span>
      )}
    </span>
  )
}

// Renders plain text, wrapping any recognised medical term in a tap-to-define
// tooltip. Line breaks are preserved via CSS (white-space: pre-wrap).
export default function GlossaryText({ text }) {
  if (!text) return null
  const out = []
  let last = 0
  let key = 0
  let m
  TERM_RE.lastIndex = 0
  while ((m = TERM_RE.exec(text)) !== null) {
    const matched = m[0]
    const def = GLOSSARY[matched.toLowerCase()]
    if (!def) continue
    if (m.index > last) out.push(text.slice(last, m.index))
    out.push(<Term key={key++} term={matched} definition={def} />)
    last = m.index + matched.length
  }
  if (last < text.length) out.push(text.slice(last))
  return <div className="glossary-text">{out}</div>
}
