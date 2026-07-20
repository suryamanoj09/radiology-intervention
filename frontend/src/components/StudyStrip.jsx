// Study strip: thumbnails for every CURRENT view in the study plus the PRIOR
// image (if any). Clicking a thumbnail selects which image the Viewer shows, so
// the clinician can flip between PA / lateral / other views and the prior study.
// Purely a selector over already-analyzed images — no scoring happens here.

const VIEW_BADGE = { PA: 'PA', AP: 'AP', Lateral: 'LAT', Frontal: 'FRONT', Other: 'OTH' }

function Thumb({ item, active, tag, onSelect }) {
  const { image_url, image_id, view, top_finding, competence } = item
  const abstained = competence === 'abstain' || !image_url
  return (
    <button
      type="button"
      className={`study-thumb ${active ? 'active' : ''} ${abstained ? 'abstained' : ''}`}
      aria-pressed={active}
      onClick={() => onSelect(image_id)}
      title={abstained ? 'Not analyzed (not a chest radiograph or unreadable)' : `${view} view`}
    >
      <span className="st-view">{tag || VIEW_BADGE[view] || view}</span>
      {abstained ? (
        <span className="st-abstain">✕</span>
      ) : (
        <img src={image_url} alt={`${view} view`} loading="lazy" draggable={false} />
      )}
      <span className="st-caption">
        {abstained ? 'not analyzed' : top_finding ? top_finding : 'no flag'}
      </span>
    </button>
  )
}

export default function StudyStrip({ images = [], prior = null, selectedId, onSelect }) {
  const hasMulti = images.length > 1
  if (!hasMulti && !prior) return null // nothing to switch between
  return (
    <div className="card study-strip">
      <div className="ss-head">
        <h3>Study views</h3>
        <span className="muted small">
          {images.length} current{prior ? ' + 1 prior' : ''} — click a view to inspect it
        </span>
      </div>
      <div className="ss-row" role="group" aria-label="Study images">
        {images.map((im) => (
          <Thumb
            key={im.image_id}
            item={im}
            active={im.image_id === selectedId}
            onSelect={onSelect}
          />
        ))}
        {prior && (
          <Thumb
            item={prior}
            tag="PRIOR"
            active={prior.image_id === selectedId}
            onSelect={onSelect}
          />
        )}
      </div>
    </div>
  )
}
