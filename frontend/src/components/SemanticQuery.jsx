import { useState } from 'react'
import { queryPapers } from '../api/client.js'

export default function SemanticQuery({ project }) {
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
      const data = await queryPapers(project, question.trim(), 6)
      setResults(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="semantic-query">
      <form className="query-input-row" onSubmit={handleQuery}>
        <input
          className="input input-grow"
          placeholder="Ask a question about the library…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={!project}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={!question.trim() || loading || !project}
        >
          {loading ? '…' : 'Ask'}
        </button>
      </form>

      {error && <p style={{ fontSize: 12, color: 'var(--error)' }}>{error}</p>}

      {results.length > 0 && (
        <div className="query-results">
          {results.map((r, i) => (
            <div key={r.doi || i} className="query-result-item">
              <span className="query-result-score">{Math.round(r.score * 100)}%</span>
              <div>
                <div className="query-result-title">{r.title}</div>
                {r.year && (
                  <div style={{ fontSize: 11, color: 'var(--ink-faint)', marginTop: 2 }}>
                    {r.year}{r.venue ? ` · ${r.venue}` : ''}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
