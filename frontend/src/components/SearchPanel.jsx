import { useEffect, useRef, useState } from 'react'

export default function SearchPanel({ onSearch, onApplyContext, isSearching, disabled, projectContext, project, prefill, focusRequest }) {
  const [applying, setApplying] = useState(false)
  const queryRef = useRef(null)
  const contextRef = useRef(null)
  const [query, setQuery]       = useState('')
  const [context, setContext]   = useState(projectContext)
  const [maxResults, setMax]    = useState(100)
  const [yearFrom, setYearFrom] = useState('')
  const [yearTo, setYearTo]     = useState('')

  // The research question belongs to the project: reload it when the project changes.
  // Once written it is shown as one line; "Edit" opens the text box again.
  const [editingContext, setEditingContext] = useState(!projectContext)
  useEffect(() => { setContext(projectContext) }, [projectContext, project])
  useEffect(() => { setEditingContext(!projectContext) }, [project, projectContext])

  const editContext = () => { setEditingContext(true); setTimeout(() => contextRef.current?.focus(), 0) }

  // Requests from the empty-project checklist: { target: 'search' | 'context', nonce }.
  useEffect(() => {
    if (!focusRequest) return
    if (focusRequest.target === 'context') editContext()
    else queryRef.current?.focus()
  }, [focusRequest])

  // "↻ reuse" from the search history puts an old query back in the form.
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
      {editingContext ? (
        <div className="search-meta">
          <textarea
            ref={contextRef}
            className="input input-grow context-input"
            rows={2}
            placeholder="Research question — Spanish or English. Used to rank every paper in the project."
            value={context}
            onChange={(e) => setContext(e.target.value)}
            disabled={disabled}
          />
        </div>
      ) : (
        <div className="context-summary">
          <span className="search-meta-label">Research question</span>
          <span className="context-text" title={projectContext}>{projectContext}</span>
          <button type="button" className="btn-text" onClick={editContext}>Edit</button>
        </div>
      )}
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
      {editingContext && contextChanged && !disabled && (
        <p className="hint">
          {projectContext ? 'Changing the question rescores the whole library. ' : ''}
          <button type="button" className="btn-text" disabled={applying || isSearching || !context.trim()}
            onClick={async () => {
              setApplying(true)
              try { await onApplyContext(context.trim()); setEditingContext(false) } finally { setApplying(false) }
            }}>
            {applying ? 'saving…' : projectContext ? 'Save and rescore' : 'Save question'}
          </button>
          {projectContext && (
            <> · <button type="button" className="btn-text"
              onClick={() => { setContext(projectContext); setEditingContext(false) }}>Cancel</button></>
          )}
          {' '}(otherwise it is saved with the next search)
        </p>
      )}
      {editingContext && !contextChanged && projectContext && (
        <p className="hint"><button type="button" className="btn-text" onClick={() => setEditingContext(false)}>Done</button></p>
      )}
    </form>
  )
}
