// Anatomy-overlay legend: one row per computed region. This lists ANATOMY labels
// only — a color swatch, a visibility checkbox, the region name, and an estimated
// size chip. It is not a findings list: there is no accept/adopt-to-report
// affordance and no pathology, score, or probability anywhere.
export default function StructureLegend({ regions, hidden, onToggle }) {
  if (!regions || !regions.length) return null
  return (
    <div className="ao-legend" role="group" aria-label="Anatomy overlay regions">
      {regions.map((r) => {
        const visible = !hidden?.has(r.structure_id)
        return (
          <label key={r.structure_id} className="ao-legend-row">
            <input
              type="checkbox"
              checked={visible}
              onChange={() => onToggle(r.structure_id)}
              aria-label={`Show ${r.label}`}
            />
            <span className="ao-legend-swatch" style={{ backgroundColor: r.color }} aria-hidden="true" />
            <span className="ao-legend-label">{r.label}</span>
            <span className="ao-legend-size">
              {r.volume_ml != null
                ? `≈ ${Math.round(r.volume_ml)} mL (auto — confirm)`
                : 'volume n/a'}
            </span>
          </label>
        )
      })}
    </div>
  )
}
