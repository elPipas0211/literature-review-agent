import { useEffect, useState } from 'react'
import PaperCard from './PaperCard.jsx'

const CATEGORIES = [
  { key: null,                       label: 'All' },
  { key: 'relevante',                label: 'Relevant',  cls: 'relevant' },
  { key: 'potencialmente_relevante', label: 'Potential', cls: 'potential' },
  { key: 'no_relevante',             label: 'Low' },
  { key: 'unevaluated',              label: 'Unscored' },
]

const PAGE = 100   // cards rendered at a time; keeps large libraries responsive

export default function PaperLibrary({
  papers, scopedPapers, libraryEmpty, listKey, onSelectPaper, onToggleStar, onKeyword,
  activeClusterLabel, onClearCluster,
  categoryFilter, onCategoryFilter,
  hideFlagged, onHideFlagged,
  starredOnly, onStarredOnly,
  reviewsOnly, onReviewsOnly,
  textFilter, onTextFilter,
  sortBy, onSortBy,
}) {
  const [limit, setLimit] = useState(PAGE)
  useEffect(() => { setLimit(PAGE) }, [listKey])

  const counts = {}
  for (const p of scopedPapers) {
    const c = p.evaluation?.category || 'unevaluated'
    counts[c] = (counts[c] || 0) + 1
  }
  const shown = papers.slice(0, limit)
  const remaining = papers.length - shown.length

  return (
    <div>
      <div className="library-toolbar">
        <input className="input input-grow" placeholder="Filter by title, abstract, author, venue, keyword, note…"
          value={textFilter} onChange={(e) => onTextFilter(e.target.value)} />
        {textFilter && <button className="btn btn-ghost btn-sm" onClick={() => onTextFilter('')}>Clear</button>}
        <select className="input select" value={sortBy} onChange={(e) => onSortBy(e.target.value)}>
          <option value="score">Sort: score</option>
          <option value="citations">Sort: citations</option>
          <option value="year">Sort: year</option>
        </select>
      </div>

      <div className="category-filter">
        {CATEGORIES.filter(({ key }) => key === null || counts[key]).map(({ key, label, cls }) => (
          <button key={String(key)}
            className={`filter-pill${categoryFilter === key ? ` active${cls ? ' ' + cls : ''}` : ''}`}
            onClick={() => onCategoryFilter(key)}>
            {label} <span className="pill-count">{key ? counts[key] : scopedPapers.length}</span>
          </button>
        ))}
      </div>
      <div className="category-filter">
        <label className="check-row">
          <input type="checkbox" checked={starredOnly} onChange={(e) => onStarredOnly(e.target.checked)} />
          ★ Starred only
        </label>
        <label className="check-row">
          <input type="checkbox" checked={reviewsOnly} onChange={(e) => onReviewsOnly(e.target.checked)} />
          Surveys / reviews only
        </label>
        <label className="check-row">
          <input type="checkbox" checked={hideFlagged} onChange={(e) => onHideFlagged(e.target.checked)} />
          Hide flagged
        </label>
      </div>

      <div className="library-header">
        <span className="library-count">{papers.length} {papers.length === 1 ? 'paper' : 'papers'}</span>
        {activeClusterLabel && (
          <div className="cluster-chip">
            <span>{activeClusterLabel}</span>
            <button onClick={onClearCluster} title="Clear cluster filter">×</button>
          </div>
        )}
      </div>

      {papers.length === 0 ? (
        <div className="empty-state">
          <p>{libraryEmpty ? 'No papers yet — run a search or import a CSV to begin.'
            : starredOnly && !scopedPapers.length ? 'No starred papers here yet — click ☆ on a paper to add it to your reading list.'
            : 'No papers match the current filters.'}</p>
        </div>
      ) : (
        <>
          <div className="paper-list">
            {shown.map((paper) => (
              <PaperCard key={paper.id} paper={paper} onClick={onSelectPaper}
                onToggleStar={onToggleStar} onKeyword={onKeyword} />
            ))}
          </div>
          {remaining > 0 && (
            <div className="show-more">
              <button className="btn btn-outline btn-sm" onClick={() => setLimit((l) => l + PAGE)}>
                Show {Math.min(PAGE, remaining)} more
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setLimit(papers.length)}>
                Show all ({papers.length})
              </button>
              <span className="hint">{shown.length} of {papers.length} shown</span>
            </div>
          )}
        </>
      )}
    </div>
  )
}
