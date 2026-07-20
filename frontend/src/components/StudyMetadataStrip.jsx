// Study metadata strip — a de-identified, at-a-glance header shown above the
// Viewer. Surfaces acquisition context (modality, projection/view, source
// format) and the privacy posture (de-identified image id + how many DICOM
// direct identifiers were scrubbed at ingest). Never shows PHI: image_id is an
// opaque server id, and no patient identifiers are ever in the AnalyzeResponse.

function formatView(vp) {
  const v = (vp || '').toUpperCase().trim()
  if (v === 'PA') return 'PA (postero-anterior)'
  if (v === 'AP') return 'AP (antero-posterior)'
  if (['LL', 'RL', 'LATERAL', 'LAT'].includes(v)) return 'Lateral'
  return vp // pass through any other DICOM ViewPosition verbatim
}

function formatSource(sf) {
  if (sf === 'dicom') return 'DICOM'
  if (sf === 'camera_photo') return 'Photo (PNG/JPG)'
  return 'PNG / JPG'
}

function formatModality(m) {
  const v = (m || '').toUpperCase().trim()
  if (v === 'CR') return 'CR (computed radiography)'
  if (v === 'DX') return 'DX (digital radiography)'
  return m || 'unknown'
}

export default function StudyMetadataStrip({ analysis }) {
  if (!analysis) return null
  const { modality, source_format, view_position, image_id, identifiers_removed } = analysis
  const isDicom = source_format === 'dicom'
  // The chest model is trained on frontal views; PNG/JPG carry no reliable
  // projection tag, so the view is unknown until the clinician confirms it.
  const viewKnown = isDicom && !!(view_position && view_position.trim())

  return (
    <div className="study-meta-strip" role="group" aria-label="Study metadata">
      <div className="meta-item">
        <span className="meta-label">Modality</span>
        <span className="meta-value">{formatModality(modality)}</span>
      </div>
      <div className="meta-item">
        <span className="meta-label">View</span>
        {viewKnown ? (
          <span className="meta-value">{formatView(view_position)}</span>
        ) : (
          <span className="meta-value meta-warn">unknown — confirm</span>
        )}
      </div>
      <div className="meta-item">
        <span className="meta-label">Source</span>
        <span className="meta-value">{formatSource(source_format)}</span>
      </div>
      <div className="meta-item">
        <span className="meta-label">Image ID</span>
        <span className="meta-value meta-mono" title="De-identified server id — not a patient identifier">
          {image_id}
        </span>
      </div>
      <div className="meta-item">
        <span className="meta-label">De-identification</span>
        {isDicom ? (
          <span className="meta-value meta-deid">
            {identifiers_removed} identifier{identifiers_removed === 1 ? '' : 's'} removed
          </span>
        ) : (
          <span className="meta-value muted">no embedded DICOM identifiers</span>
        )}
      </div>
    </div>
  )
}
