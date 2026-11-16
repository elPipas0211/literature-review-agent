import { memo } from 'react'

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

export function StarButton({ starred, onToggle, large }) {
  return (
    <button type="button" className={`star-btn${starred ? ' on' : ''}${large ? ' large' : ''}`}
      aria-pressed={!!starred} title={starred ? 'Remove from reading list' : 'Add to reading list'}
      onClick={(e) => { e.stopPropagation(); onToggle() }}>
      {starred ? '★' : '☆'}
    </button>
  )
}

export function KeywordChips({ keywords, onKeyword, max = 5 }) {
  if (!keywords?.length) return null
  return (
    <div className="kw-row">
      {keywords.slice(0, max).map((k) => (
        <button key={k} type="button" className="kw-chip clickable" title={`Filter the library by “${k}”`}
          onClick={(e) => { e.stopPropagation(); onKeyword?.(k) }}>{k}</button>
      ))}
    </div>
  )
}

function PaperCard({ paper, onClick, onToggleStar, onKeyword }) {
  const ev = paper.evaluation
  const abstract = (paper.abstract || '').trim()
  return (
    <article className={`paper-card${paper.starred ? ' starred' : ''}`} onClick={() => onClick(paper)}>
      <div className="paper-card-meta">
        <StarButton starred={paper.starred} onToggle={() => onToggleStar(paper)} />
        <Badge category={ev?.category} />
        {paper.is_review && <span className="badge badge-review" title="Survey / review article">Review</span>}
        {ev?.score != null && <span className="paper-score" title="Relevance score">{ev.score.toFixed(2)}</span>}
        <span className="paper-year">{paper.year || '—'}</span>
        {paper.note && <span className="note-mark" title={paper.note}>✎ note</span>}
        {paper.citationCount != null && <span className="paper-cites">{paper.citationCount.toLocaleString()}</span>}
        {(paper.flags || []).map((f) => <span key={f} className="flag-chip">{FLAG_LABELS[f] || f}</span>)}
      </div>
      <h2 className="paper-title">{paper.title}</h2>
      {paper.venue && <p className="paper-venue">{paper.venue}</p>}
      {abstract && <p className="paper-abstract">{abstract}</p>}
      <KeywordChips keywords={paper.keywords} onKeyword={onKeyword} max={4} />
    </article>
  )
}

export default memo(PaperCard)
