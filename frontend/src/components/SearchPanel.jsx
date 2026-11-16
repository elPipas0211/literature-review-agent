import { useEffect, useRef, useState } from 'react'

export default function SearchPanel({ onSearch, onApplyContext, isSearching, disabled, projectContext, project, prefill }) {
  const [applying, setApplying] = useState(false)
  const [query, setQuery]       = useState('')
  const [context, setContext]   = useState(projectContext)
  const [maxResults, setMax]    = useState(100)
  const [yearFrom, setYearFrom] = useState('')
  const [yearTo, setYearTo]     = useState('')

  // The research context belongs to the project: reload it when the project changes.
  useEffect(() => { setContext(projectContext) }, [projectContext, project])

  // "↻ reuse" from the search history puts an old query back in the form.
  const queryRef = useRef(null)
  useEffect(() => {
    if (!prefill) return
    setQuery(prefill.query || '')
    setYearFrom(prefill.year_from ?? '')
    setYearTo(prefill.year_to ?? '')
    if (prefill.max_results) setMax(prefill.max_results)
    queryRef.current?.focus()
  }, [prefill])

  const canSearch = query.trim().length > 0 && !isSearching && !disabled
  const contextChanged = context.trim() !== (projectContext || '').trim()

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!canSearch) return
    onSearch({
      query: query.trim(),
      context: context.trim() || null,
      max_results: maxResults,
      year_from: yearFrom ? Number(yearFrom) : null,
      year_to: yearTo ? Number(yearTo) : null,
    })
  }

  return (
    <form className="search-panel" onSubmit={handleSubmit}>
      <div className="search-row">
        <input
          ref={queryRef}
          className="input input-grow"
          placeholder="Search query (English works best) — e.g. anomaly detection industrial time series"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={disabled}
        />
        <button type="submit" className="btn btn-primary" disabled={!canSearch}
          title={disabled ? 'Select a project first' : !query.trim() ? 'Enter a search query' : ''}>
          {isSearching ? 'Searching…' : 'Search'}
        </button>
      </div>
      <div className="search-meta">
        <textarea
          className="input input-grow context-input"
          rows={2}
          placeholder="Research context / question — Spanish or English. Used to rank every paper in the project."
          value={context}
          onChange={(e) => setContext(e.target.value)}
          disabled={disabled}
        />
      </div>
      <div className="search-meta">
        <span className="search-meta-label">Years</span>
        <input type="number" className="input-number" placeholder="from" value={yearFrom}
          onChange={(e) => setYearFrom(e.target.value)} disabled={disabled} />
        <input type="number" className="input-number" placeholder="to" value={yearTo}
          onChange={(e) => setYearTo(e.target.value)} disabled={disabled} />
        <span className="search-meta-label">Max results</span>
        <input type="number" className="input-number" min={10} max={2000} value={maxResults}
          onChange={(e) => setMax(Math.min(2000, Math.max(10, Number(e.target.value) || 100)))}
          disabled={disabled} />
      </div>
      {contextChanged && !disabled && (
        <p className="hint">
          Changing the context rescores the whole library against the new text (applied on the next search, or now:{' '}
          <button type="button" className="btn-text" disabled={applying || isSearching}
            onClick={async () => { setApplying(true); try { await onApplyContext(context.trim()) } finally { setApplying(false) } }}>
            {applying ? 'rescoring…' : 'apply & rescore'}
          </button>)
        </p>
      )}
      {disabled && <p className="hint">Select or create a project in the header to start.</p>}
    </form>
  )
}
