import PaperCard from './PaperCard.jsx'

const CATEGORIES = [
  { key: null,                        label: 'All' },
  { key: 'relevante',                 label: 'Relevant',   cls: 'relevant' },
  { key: 'potencialmente_relevante',  label: 'Potential',  cls: 'potential' },
]

export default function PaperLibrary({
  papers, onSelectPaper,
  activeCluster, onClearCluster,
  categoryFilter, onCategoryFilter,
}) {
  const counts = {
    relevante:               papers.filter((p) => p.evaluation?.category === 'relevante').length,
    potencialmente_relevante: papers.filter((p) => p.evaluation?.category === 'potencialmente_relevante').length,
  }

  return (
    <div>
      <div className="library-header">
        <span className="library-count">{papers.length} {papers.length === 1 ? 'paper' : 'papers'}</span>
        {activeCluster != null && (
          <div className="cluster-chip">
            <span>Cluster {activeCluster}</span>
            <button onClick={onClearCluster} title="Clear cluster filter">×</button>
          </div>
        )}
      </div>

      {/* Category filter pills */}
      <div className="category-filter">
        {CATEGORIES.map(({ key, label, cls }) => {
          const count = key ? counts[key] : papers.length
          const isActive = categoryFilter === key
          return (
            <button
              key={String(key)}
              className={`filter-pill${isActive ? ` active${cls ? ' ' + cls : ''}` : ''}`}
              onClick={() => onCategoryFilter(key)}
            >
              {label}
              {count > 0 && count !== papers.length && (
                <span style={{ marginLeft: 4, opacity: 0.75 }}>({count})</span>
              )}
            </button>
          )
        })}
      </div>

      {papers.length === 0 ? (
        <div className="empty-state">
          <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
            <path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
          <p>No papers here — run a search or import a CSV to begin.</p>
        </div>
      ) : (
        <div className="paper-list">
          {papers.map((paper) => (
            <PaperCard
              key={paper._id || paper.title}
              paper={paper}
              onClick={onSelectPaper}
            />
          ))}
        </div>
      )}
    </div>
  )
}
