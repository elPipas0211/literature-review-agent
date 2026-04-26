function Badge({ category }) {
  if (category === 'relevante')
    return <span className="badge badge-relevant">Relevant</span>
  if (category === 'potencialmente_relevante')
    return <span className="badge badge-potential">Potential</span>
  if (!category || category === 'unevaluated')
    return <span className="badge badge-none">Uncategorized</span>
  // no_relevante, descartado_semantica, error — shown when re-evaluation pushed them down
  return <span className="badge badge-none" title={category}>—</span>
}

export default function PaperCard({ paper, onClick }) {
  const category = paper.evaluation?.category
  const abstract = (paper.abstract || '').trim()

  return (
    <article className="paper-card" onClick={() => onClick(paper)}>
      <div className="paper-card-meta">
        <Badge category={category} />
        <span className="paper-year">{paper.year || '—'}</span>
        {paper.citationCount != null && (
          <span className="paper-cites">{paper.citationCount.toLocaleString()}</span>
        )}
      </div>
      <h2 className="paper-title">{paper.title}</h2>
      {paper.venue && <p className="paper-venue">{paper.venue}</p>}
      {abstract && <p className="paper-abstract">{abstract}</p>}
    </article>
  )
}
