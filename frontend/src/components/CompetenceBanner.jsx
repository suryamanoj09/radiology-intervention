// Shows the self-audit gate result: the "AI that knows when to shut up".
export default function CompetenceBanner({ competence, reasons, oodScore }) {
  if (!competence || competence === 'read') return null
  const abstain = competence === 'abstain'
  return (
    <div
      className={abstain ? 'competence competence-abstain' : 'competence competence-caution'}
      role={abstain ? 'alert' : 'status'}
    >
      <strong>
        {abstain
          ? 'Analysis withheld — this does not look like a chest radiograph I can read.'
          : 'Reduced confidence — this image may be low quality or atypical.'}
      </strong>
      {reasons?.length > 0 && <span> {reasons.join('; ')}.</span>}
      <span className="muted small">
        {' '}The tool refused to score rather than guess (out-of-distribution score{' '}
        {Math.round((oodScore ?? 0) * 100)}%).
      </span>
    </div>
  )
}
