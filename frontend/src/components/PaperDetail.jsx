import { useState } from 'react'
import { paperToBibtex } from '../api/client.js'

function Badge({ category }) {
  if (category === 'relevante')
    return <span className="badge badge-relevant">Relevant</span>
  if (category === 'potencialmente_relevante')
    return <span className="badge badge-potential">Potentially Relevant</span>
  if (!category || category === 'unevaluated')
    return <span className="badge badge-none">Uncategorized</span>
  return null
}

export default function PaperDetail({ paper, onClose }) {
  const [copied, setCopied] = useState(false)
  const ev = paper.evaluation || {}
  const doi = paper.externalIds?.DOI
  const bibtex = paperToBibtex(paper)
  const authors = (paper.authors || []).map((a) => a.name).join(', ')

  const copy = async () => {
    await navigator.clipboard.writeText(bibtex)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="detail-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="detail-panel">
        <div className="detail-close">
          <button className="btn btn-outline btn-sm" onClick={onClose}>Close ×</button>
        </div>

        <div className="detail-badges">
          <Badge category={ev.category} />
          {paper.year && <span className="paper-year">{paper.year}</span>}
          {paper.citationCount != null && (
            <span className="paper-cites">{paper.citationCount.toLocaleString()} citations</span>
          )}
        </div>

        <h2 className="detail-title">{paper.title}</h2>

        {authors && (
          <p className="detail-meta">{authors}</p>
        )}
        {paper.venue && (
          <p className="detail-meta" style={{ fontStyle: 'italic' }}>{paper.venue}</p>
        )}

        {paper.abstract && (
          <div>
            <div className="detail-section-label">Abstract</div>
            <p className="detail-abstract">{paper.abstract}</p>
          </div>
        )}

        {ev.score != null && (
          <div>
            <div className="detail-section-label">Evaluation scores</div>
            <div className="score-grid">
              <div className="score-cell">
                <span className="score-val">{ev.score?.toFixed(3)}</span>
                <span className="score-lbl">Combined</span>
              </div>
              <div className="score-cell">
                <span className="score-val">{ev.semantic_score?.toFixed(3)}</span>
                <span className="score-lbl">Semantic</span>
              </div>
              <div className="score-cell">
                <span className="score-val">{ev.impact_score?.toFixed(3)}</span>
                <span className="score-lbl">Impact</span>
              </div>
            </div>
          </div>
        )}

        {doi && (
          <div>
            <div className="detail-section-label">DOI</div>
            <div className="doi-row">
              <span>{doi}</span>
              <a
                href={`https://doi.org/${doi}`}
                target="_blank"
                rel="noreferrer"
                className="btn btn-outline btn-sm"
              >
                Open ↗
              </a>
            </div>
          </div>
        )}

        <div>
          <div className="detail-section-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>BibTeX</span>
            <button className="btn btn-outline btn-sm copy-btn" onClick={copy}>
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
          <pre className="bibtex-block">{bibtex}</pre>
        </div>
      </div>
    </div>
  )
}
