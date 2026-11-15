import { useState } from 'react'
import { Badge, FLAG_LABELS } from './PaperCard.jsx'

const TYPE_LABELS = {
  article: 'Journal article', conference: 'Conference paper', chapter: 'Book chapter',
  book: 'Book', preprint: 'Preprint', thesis: 'Thesis', other: 'Other',
}
const SOURCE = { semantic_scholar: 'Semantic Scholar', openalex: 'OpenAlex', scopus_csv: 'Scopus CSV',
                 wos_csv: 'Web of Science CSV', zotero_csv: 'Zotero CSV' }

export default function PaperDetail({ paper, onClose }) {
  const [copied, setCopied] = useState(false)
  const ev = paper.evaluation || {}
  const doi = paper.externalIds?.DOI
  const authors = (paper.authors || []).map((a) => a.name).join('; ')
  const queries = [...new Set((paper.found_in || []).map((f) => f.query).filter(Boolean))]

  const copy = async () => {
    await navigator.clipboard.writeText(paper.bibtex || '')
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
          {paper.citationCount != null && <span className="paper-cites">{paper.citationCount.toLocaleString()} citations</span>}
          <span className="paper-year">{TYPE_LABELS[paper.publicationType] || paper.publicationType}</span>
          {(paper.flags || []).map((f) => <span key={f} className="flag-chip">{FLAG_LABELS[f] || f}</span>)}
        </div>

        <h2 className="detail-title">{paper.title}</h2>
        {authors && <p className="detail-meta">{authors}</p>}
        {paper.venue && <p className="detail-meta" style={{ fontStyle: 'italic' }}>{paper.venue}</p>}

        {paper.abstract
          ? <div><div className="detail-section-label">Abstract</div><p className="detail-abstract">{paper.abstract}</p></div>
          : <p className="hint">No abstract available from the sources — check the full text before deciding.</p>}

        {ev.score != null && (
          <div>
            <div className="detail-section-label">Scores</div>
            <div className="score-grid">
              <div className="score-cell"><span className="score-val">{ev.score.toFixed(3)}</span><span className="score-lbl">Combined</span></div>
              <div className="score-cell"><span className="score-val">{ev.semantic_score?.toFixed(3)}</span><span className="score-lbl">Semantic</span></div>
              <div className="score-cell"><span className="score-val">{ev.impact_score?.toFixed(3)}</span><span className="score-lbl">Impact</span></div>
              <div className="score-cell"><span className="score-val">{ev.similarity?.toFixed(3)}</span><span className="score-lbl">Raw cosine</span></div>
            </div>
          </div>
        )}

        <div className="doi-row">
          {doi && <a href={`https://doi.org/${doi}`} target="_blank" rel="noreferrer" className="btn btn-outline btn-sm">DOI {doi} ↗</a>}
          {paper.openAccessPdf && <a href={paper.openAccessPdf} target="_blank" rel="noreferrer" className="btn btn-outline btn-sm">Open access ↗</a>}
        </div>

        <div>
          <div className="detail-section-label">Provenance</div>
          <p className="detail-meta">Sources: {(paper._sources || []).map((s) => SOURCE[s] || s).join(', ')}</p>
          {queries.length > 0 && <p className="detail-meta">Found by: {queries.map((q) => `“${q}”`).join(', ')}</p>}
        </div>

        <div>
          <div className="detail-section-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>BibTeX <code>{paper.cite_key}</code></span>
            <button className="btn btn-outline btn-sm copy-btn" onClick={copy}>{copied ? 'Copied!' : 'Copy'}</button>
          </div>
          <pre className="bibtex-block">{paper.bibtex}</pre>
        </div>
      </div>
    </div>
  )
}
