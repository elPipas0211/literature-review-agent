import PaperCard from './PaperCard.jsx'

const CATEGORIES = [
  { key: null,                       label: 'All' },
  { key: 'relevante',                label: 'Relevant',  cls: 'relevant' },
  { key: 'potencialmente_relevante', label: 'Potential', cls: 'potential' },
  { key: 'no_relevante',             label: 'Low' },
  { key: 'unevaluated',              label: 'Unscored' },
]

export default function PaperLibrary({
  papers, scopedPapers, libraryEmpty, onSelectPaper,
  activeClusterLabel, onClearCluster,
  categoryFilter, onCategoryFilter,
  hideFlagged, onHideFlagged,
  textFilter, onTextFilter,
  sortBy, onSortBy,
}) {
  const counts = {}
  for (const p of scopedPapers) {
    const c = p.evaluation?.category || 'unevaluated'
    counts[c] = (counts[c] || 0) + 1
  }

  return (
    <div>
      <div className="library-toolbar">
        <input className="input input-grow" placeholder="Filter by title, abstract, author, venue…"
          value={textFilter} onChange={(e) => onTextFilter(e.target.value)} />
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
          <p>{libraryEmpty ? 'No papers yet — run a search or import a CSV to begin.' : 'No papers match the current filters.'}</p>
        </div>
      ) : (
        <div className="paper-list">
          {papers.map((paper) => <PaperCard key={paper.id} paper={paper} onClick={onSelectPaper} />)}
        </div>
      )}
    </div>
  )
}
