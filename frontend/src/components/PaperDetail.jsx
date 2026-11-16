import { useEffect, useState } from 'react'
import { Badge, FLAG_LABELS, KeywordChips, StarButton } from './PaperCard.jsx'

const TYPE_LABELS = {
  article: 'Journal article', conference: 'Conference paper', chapter: 'Book chapter',
  book: 'Book', preprint: 'Preprint', thesis: 'Thesis', other: 'Other',
}
const SOURCE = { semantic_scholar: 'Semantic Scholar (legacy)', openalex: 'OpenAlex', citation_search: 'Citation searching', scopus_csv: 'Scopus CSV',
                 wos_csv: 'Web of Science CSV', zotero_csv: 'Zotero CSV' }

export default function PaperDetail({ paper, onClose, onSnowball, busy, onAnnotate, onKeyword }) {
  const [copied, setCopied] = useState(false)
  const [note, setNote] = useState(paper.note || '')
  useEffect(() => { setNote(paper.note || '') }, [paper.id])
  const noteDirty = note.trim() !== (paper.note || '').trim()
  const saveNote = () => { if (noteDirty) onAnnotate({ note: note.trim() }) }

  // Esc closes the panel (saving a pending note first).
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') { saveNote(); onClose() } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  const close = () => { saveNote(); onClose() }
  const [max, setMax] = useState(100)
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
    <div className="detail-overlay" onClick={(e) => e.target === e.currentTarget && close()}>
      <div className="detail-panel">
        <div className="detail-close">
          <button className="btn btn-outline btn-sm" onClick={close}>Close ×</button>
        </div>

        <div className="detail-badges">
          <StarButton large starred={paper.starred} onToggle={() => onAnnotate({ starred: !paper.starred })} />
          <Badge category={ev.category} />
          {paper.is_review && <span className="badge badge-review">Survey / review</span>}
          {paper.year && <span className="paper-year">{paper.year}</span>}
          {paper.citationCount != null && <span className="paper-cites">{paper.citationCount.toLocaleString()} citations</span>}
          <span className="paper-year">{TYPE_LABELS[paper.publicationType] || paper.publicationType}</span>
          {(paper.flags || []).map((f) => <span key={f} className="flag-chip">{FLAG_LABELS[f] || f}</span>)}
        </div>

        <h2 className="detail-title">{paper.title}</h2>
        {authors && <p className="detail-meta">{authors}</p>}
        {paper.venue && <p className="detail-meta" style={{ fontStyle: 'italic' }}>{paper.venue}</p>}

        <KeywordChips keywords={paper.keywords} onKeyword={onKeyword} />

        <div>
          <div className="detail-section-label">Reading notes</div>
          <textarea className="input note-input" rows={3} value={note}
            placeholder="Why it matters, method, dataset, gaps it mentions… (saved with the project, exported to CSV/RIS)"
            onChange={(e) => setNote(e.target.value)} onBlur={saveNote} />
          <p className="hint">{noteDirty ? 'Unsaved — saves when you click outside the box.' : paper.note ? 'Saved.' : ''}
            {!paper.starred && ' Tip: ☆ adds the paper to your reading list.'}</p>
        </div>

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
          <div className="detail-section-label">Snowballing (citation searching)</div>
          <p className="hint">Add this paper's references (older work it builds on) and/or the papers that cite it
            (newer work) to the library. Logged separately for PRISMA.</p>
          <div className="snowball-row">
            <button className="btn btn-outline btn-sm" disabled={busy} onClick={() => { saveNote(); onSnowball(paper.id, 'references', max) }}>← References</button>
            <button className="btn btn-outline btn-sm" disabled={busy} onClick={() => { saveNote(); onSnowball(paper.id, 'citations', max) }}>Cited by →</button>
            <button className="btn btn-outline btn-sm" disabled={busy} onClick={() => { saveNote(); onSnowball(paper.id, 'both', max) }}>Both</button>
            <span className="search-meta-label">max each</span>
            <input type="number" className="input-number" min={10} max={1000} value={max}
              onChange={(e) => setMax(Math.min(1000, Math.max(10, Number(e.target.value) || 100)))} />
          </div>
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
