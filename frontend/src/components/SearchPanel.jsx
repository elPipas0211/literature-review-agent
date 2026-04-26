import { useState } from 'react'

export default function SearchPanel({ onSearch, isSearching, disabled }) {
  const [query, setQuery]       = useState('')
  const [context, setContext]   = useState('')
  const [maxResults, setMax]    = useState(50)

  const canSearch = query.trim().length > 0 && !isSearching && !disabled

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!canSearch) return
    onSearch(query.trim(), context.trim() || null, maxResults)
  }

  return (
    <form className="search-panel" onSubmit={handleSubmit}>
      <div className="search-row">
        <input
          className="input input-grow"
          placeholder="Search query — e.g. anomaly detection deep learning industrial…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={disabled}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={!canSearch}
          title={
            disabled        ? 'Select a project first' :
            !query.trim()   ? 'Enter a search query'   :
            isSearching     ? 'Search in progress…'    : ''
          }
        >
          {isSearching ? 'Searching…' : 'Search'}
        </button>
      </div>
      <div className="search-meta">
        <input
          className="input input-grow"
          placeholder="Research context for semantic evaluation — optional"
          value={context}
          onChange={(e) => setContext(e.target.value)}
          disabled={disabled}
        />
        <span className="search-meta-label">Max</span>
        <input
          type="number"
          className="input-number"
          min={10}
          max={500}
          value={maxResults}
          onChange={(e) => setMax(Math.min(500, Math.max(10, Number(e.target.value) || 50)))}
          disabled={disabled}
        />
      </div>
      {disabled && (
        <p style={{ fontSize: 11, color: 'var(--ink-faint)', marginTop: 2 }}>
          Select a project from the header to enable search.
        </p>
      )}
    </form>
  )
}
