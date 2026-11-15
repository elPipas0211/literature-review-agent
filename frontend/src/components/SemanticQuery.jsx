import { useState } from 'react'
import { queryPapers } from '../api/client.js'

export default function SemanticQuery({ project, onOpen }) {
  const [question, setQuestion] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleQuery = async (e) => {
    e.preventDefault()
    if (!question.trim() || loading) return
    setLoading(true)
    setError(null)
    try {
      setResults(await queryPapers(project, question.trim(), 10))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="semantic-query">
      <form className="query-input-row" onSubmit={handleQuery}>
        <input className="input input-grow"
          placeholder="Ask about the library, in Spanish or English — e.g. ¿qué métodos no supervisados se usan?"
          value={question} onChange={(e) => setQuestion(e.target.value)} disabled={!project} />
        <button type="submit" className="btn btn-primary" disabled={!question.trim() || loading || !project}>
          {loading ? '…' : 'Ask'}
        </button>
      </form>
      <p className="hint">Returns the papers whose title + abstract are closest in meaning to your question.</p>

      {error && <p style={{ fontSize: 12, color: 'var(--error)' }}>{error}</p>}

      {results.length > 0 && (
        <div className="query-results">
          {results.map((r) => (
            <div key={r.id} className="query-result-item clickable" onClick={() => onOpen(r.id)}>
              <span className="query-result-score" title="Cosine similarity">{r.similarity.toFixed(3)}</span>
              <div>
                <div className="query-result-title">{r.title}</div>
                <div className="query-result-meta">{r.year || '—'}{r.venue ? ` · ${r.venue}` : ''}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
