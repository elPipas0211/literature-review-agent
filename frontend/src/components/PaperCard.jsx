export const FLAG_LABELS = {
  missing_abstract: 'no abstract',
  missing_doi: 'no DOI',
  missing_citation_count: 'no citation count',
  below_citation_floor: 'below citation floor',
}

export function Badge({ category }) {
  if (category === 'relevante') return <span className="badge badge-relevant">Relevant</span>
  if (category === 'potencialmente_relevante') return <span className="badge badge-potential">Potential</span>
  if (category === 'no_relevante') return <span className="badge badge-low">Low</span>
  return <span className="badge badge-none">Unscored</span>
}

export default function PaperCard({ paper, onClick }) {
  const ev = paper.evaluation
  const abstract = (paper.abstract || '').trim()
  return (
    <article className="paper-card" onClick={() => onClick(paper)}>
      <div className="paper-card-meta">
        <Badge category={ev?.category} />
        {ev?.score != null && <span className="paper-score" title="Relevance score">{ev.score.toFixed(2)}</span>}
        <span className="paper-year">{paper.year || '—'}</span>
        {paper.citationCount != null && <span className="paper-cites">{paper.citationCount.toLocaleString()}</span>}
        {(paper.flags || []).map((f) => <span key={f} className="flag-chip">{FLAG_LABELS[f] || f}</span>)}
      </div>
      <h2 className="paper-title">{paper.title}</h2>
      {paper.venue && <p className="paper-venue">{paper.venue}</p>}
      {abstract && <p className="paper-abstract">{abstract}</p>}
    </article>
  )
}
