import { useState } from 'react'
import { downloadExport, streamClusters, streamCompleteDetails, streamKeySentences, streamRefreshKeywords } from '../api/client.js'

import { SOURCE_LABELS as SOURCE } from '../sources.js'

function StatCards({ papers, onShowStarred, onShowReviews }) {
  const count = (c) => papers.filter((p) => p.evaluation?.category === c).length
  const starred = papers.filter((p) => p.starred).length
  const reviews = papers.filter((p) => p.is_review).length
  return (
    <section className="sidebar-section">
      <div className="sidebar-label">Collection</div>
      <div className="stat-cards">
        <div className="stat-card"><span className="stat-card-label">Total</span><span className="stat-card-number">{papers.length}</span></div>
        <div className="stat-card relevant"><span className="stat-card-label">Relevant</span><span className="stat-card-number">{count('relevante')}</span></div>
        <div className="stat-card potential"><span className="stat-card-label">Potential</span><span className="stat-card-number">{count('potencialmente_relevante')}</span></div>
        <div className="stat-card"><span className="stat-card-label">Low</span><span className="stat-card-number">{count('no_relevante')}</span></div>
        <button className={`stat-card${starred ? ' clickable' : ''}`} onClick={() => starred && onShowStarred()}
          title={starred ? 'Show the reading list' : 'Star papers (☆) to build your reading list'}>
          <span className="stat-card-label">★ Reading list</span><span className="stat-card-number">{starred}</span></button>
        <button className={`stat-card${reviews ? ' clickable' : ''}`} onClick={() => reviews && onShowReviews()}
          title={reviews ? 'Show surveys and reviews' : 'No surveys or reviews detected yet'}>
          <span className="stat-card-label">Surveys</span><span className="stat-card-number">{reviews}</span></button>
      </div>
    </section>
  )
}

function Prisma({ prisma, onReuseSearch }) {
  if (!prisma || !prisma.sessions?.length) return null
  const db = prisma.databases || prisma
  const cit = prisma.citation_searching
  return (
    <section className="sidebar-section">
      <div className="sidebar-label">PRISMA — identification</div>
      <table className="prisma-table">
        <tbody>
          {Object.entries(db.identified_by_source).map(([s, n]) => (
            <tr key={s}><td>Records from {SOURCE[s] || s}</td><td>{n}</td></tr>
          ))}
          <tr><td>Duplicates removed</td><td>−{db.duplicates_removed}</td></tr>
          {cit?.identified_total > 0 && (
            <>
              <tr className="sum"><td>From databases</td><td>{db.added}</td></tr>
              <tr><td>Citation searching (snowballing)</td><td>{cit.identified_total}</td></tr>
              <tr><td>Duplicates / already found</td><td>−{cit.duplicates_removed}</td></tr>
              <tr className="sum"><td>From citation searching</td><td>{cit.added}</td></tr>
            </>
          )}
          <tr className="sum"><td>Records to screen</td><td>{prisma.records_in_library}</td></tr>
        </tbody>
      </table>
      <details>
        <summary className="hint">{prisma.sessions.length} searches / imports</summary>
        <ul className="session-list">
          {prisma.sessions.map((s) => (
            <li key={s.session_id}>
              <span className="session-date">{(s.started_at || '').slice(0, 16).replace('T', ' ')}</span>{' '}
              {s.kind === 'import' ? `📄 ${s.file}` : s.kind === 'snowball' ? `🔗 ${s.query}` : `🔎 “${s.query}”`}
              {(s.year_from || s.year_to) && ` [${s.year_from || ''}–${s.year_to || ''}]`}
              {' '}→ {s.identified} found, {s.added} new
              {s.kind === 'search' && s.query && (
                <button className="btn-text reuse-btn" title="Put this query back in the search box"
                  onClick={() => onReuseSearch(s)}>↻ reuse</button>
              )}
              {Object.entries(s.sources || {}).filter(([, v]) => v.error).map(([k]) => (
                <span key={k} className="flag-chip">{SOURCE[k] || k} failed</span>
              ))}
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}

const FORMATS = [['csv', 'CSV'], ['ris', 'RIS'], ['bib', 'BibTeX'], ['apa', 'APA']]

function Exports({ project, total, visibleIds, starredIds, readingIds, missingDetails, onReload }) {
  const [error, setError] = useState(null)
  const [preparing, setPreparing] = useState(false)
  // Key sentences are computed (and cached) first with a progress stream, then the CSV downloads.
  const exportReading = async () => {
    setPreparing('Starting…'); setError(null)
    try {
      for await (const ev of streamKeySentences(project, readingIds)) {
        if (ev.type === 'summary_progress') setPreparing(`Reading abstracts… ${Math.round((ev.done / ev.total) * 100)}%`)
        if (ev.type === 'error') throw new Error(ev.message)
      }
      setPreparing('Downloading…')
      await downloadExport(project, 'csv', readingIds)
      onReload()
    } catch (e) { setError(e.message) } finally { setPreparing(false) }
  }
  const [details, setDetails] = useState(null)
  const completeDetails = async () => {
    setDetails('Starting…')
    try {
      for await (const ev of streamCompleteDetails(project)) {
        if (ev.type === 'details_progress') setDetails(`Checking ${ev.done} / ${ev.total}…`)
        if (ev.type === 'wait') setDetails(ev.message)
        if (ev.type === 'error') setDetails(`Error: ${ev.message}`)
        if (ev.type === 'result') {
          setDetails(`Completed ${ev.result.updated} of ${ev.result.checked}. The rest are not in OpenAlex or have no volume/pages there.`)
          onReload()
        }
      }
    } catch (err) {
      setDetails(`Error: ${err.message}`)
    }
  }
  const run = (fmt, ids) => downloadExport(project, fmt, ids).catch((e) => setError(e.message))
  const partial = visibleIds.length < total
  return (
    <section className="sidebar-section">
      <div className="sidebar-label">Export</div>
      {readingIds.length > 0 && (
        <>
          <button className="btn btn-primary btn-sm" disabled={preparing} onClick={exportReading}
            title="Starred papers first, then the relevant ones, with title, abstract, key sentence, keywords, topic, notes and APA">
            {preparing || `CSV · ★ starred + relevant (${readingIds.length})`}
          </button>
          <p className="hint">One row per paper: title, abstract, the sentence closest to your research question,
            keywords, topic, your notes and the APA citation. Opens in Excel. The first time it reads every
            abstract (about 1–2 minutes for 600 papers); after that it is instant.</p>
        </>
      )}
      <div className="export-grid">
        {FORMATS.map(([fmt, label]) => (
          <button key={fmt} className="btn btn-outline btn-sm" disabled={!total}
            onClick={() => run(fmt, null)} title={`Whole library (${total})`}>
            {label}
          </button>
        ))}
      </div>
      {starredIds.length > 0 && (
        <button className="btn btn-outline btn-sm" onClick={() => run('apa', starredIds)}>
          APA references · reading list ({starredIds.length})
        </button>
      )}
      {partial && (
        <>
          <div className="sidebar-sublabel">Only the current view ({visibleIds.length})</div>
          <div className="export-grid">
            {FORMATS.map(([fmt, label]) => (
              <button key={fmt} className="btn btn-ghost btn-sm" disabled={!visibleIds.length}
                onClick={() => run(fmt, visibleIds)}>{label}</button>
            ))}
          </div>
        </>
      )}
      <p className="hint">CSV / RIS → ASReview, Rayyan, Zotero. BibTeX keys match the “Copy” button.
        APA → a Word-ready reference list (.rtf, alphabetical, italics kept).</p>
      {missingDetails > 0 && (
        <p className="hint">
          {missingDetails} papers with a DOI lack volume / pages for their APA reference.{' '}
          <button className="btn-text" disabled={details != null && /…$/.test(details)} onClick={completeDetails}>
            Complete from OpenAlex</button>
        </p>
      )}
      {details && <p className="hint">{details}</p>}
      {error && <p className="hint" style={{ color: 'var(--error)' }}>{error}</p>}
    </section>
  )
}

function ClusterFilter({ clusters, activeCluster, onSelect, project, onGenerated }) {
  const [generating, setGenerating] = useState(false)
  const [onlyRelevant, setOnlyRelevant] = useState(true)
  const [log, setLog] = useState([])
  const [kwState, setKwState] = useState(null)   // null | 'running' | message
  const list = clusters?.clusters || []

  const handleKeywords = async () => {
    setKwState('Starting…')
    try {
      for await (const ev of streamRefreshKeywords(project)) {
        if (ev.type === 'keywords_progress') setKwState(`Keywords ${ev.done} / ${ev.total}…`)
        if (ev.type === 'error') setKwState(`Error: ${ev.message}`)
        if (ev.type === 'result') {
          setKwState(`Updated ${ev.result.updated} papers.${list.length ? ' Regenerate clusters to refresh their labels.' : ''}`)
          onGenerated()
        }
      }
    } catch (err) {
      setKwState(`Error: ${err.message}`)
    }
  }
  const kwRunning = kwState != null && /…$/.test(kwState)

  const handleGenerate = async () => {
    setGenerating(true)
    setLog([])
    const params = onlyRelevant ? { only_categories: ['relevante', 'potencialmente_relevante'] } : {}
    try {
      for await (const ev of streamClusters(project, params)) {
        if (ev.type === 'loaded')    setLog((l) => [...l, `Loaded ${ev.count} papers`])
        if (ev.type === 'clustered') setLog((l) => [...l, `Elbow at k=${ev.k}`])
        if (ev.type === 'labeling')  setLog((l) => [...l, 'Labeling clusters…'])
        if (ev.type === 'error')     setLog((l) => [...l, `Error: ${ev.message}`])
        if (ev.type === 'result')    { setLog([]); onGenerated() }
      }
    } catch (err) {
      setLog((l) => [...l, `Error: ${err.message}`])
    } finally {
      setGenerating(false)
    }
  }

  return (
    <section className="sidebar-section">
      <div className="sidebar-label">Clusters</div>
      {list.length > 0 ? (
        <div className="cluster-list">
          <button className={`cluster-all-btn${activeCluster == null ? ' active' : ''}`} onClick={() => onSelect(null)}>
            All papers
          </button>
          {list.map((c) => (
            <div key={c.id} className={`cluster-card${activeCluster === c.id ? ' active' : ''}`}
              onClick={() => onSelect(activeCluster === c.id ? null : c.id)} title={c.top_titles?.join('\n')}>
              <span className="cluster-card-name">{c.label}</span>
              <span className="cluster-card-badge">{c.paper_count}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="hint">No clusters yet.</p>
      )}
      <label className="check-row">
        <input type="checkbox" checked={onlyRelevant} onChange={(e) => setOnlyRelevant(e.target.checked)} />
        Only relevant + potential
      </label>
      <button className="btn btn-outline btn-sm btn-block" onClick={handleGenerate} disabled={generating || !project}>
        {generating ? 'Generating…' : list.length > 0 ? 'Regenerate' : 'Generate clusters'}
      </button>
      {log.length > 0 && <div className="hint">{log.map((l, i) => <div key={i}>{l}</div>)}</div>}
      <button className="btn-text" onClick={handleKeywords} disabled={kwRunning || generating || !project}
        title="Re-extract the keyphrases of every paper (about 6 s per 100 papers)">
        Recompute keywords
      </button>
      {kwState && <p className="hint">{kwState}</p>}
    </section>
  )
}

function Slider({ label, desc, min, max, step, value, fmt, onChange }) {
  return (
    <div className="slider-row">
      <div className="slider-header">
        <span className="slider-name">{label}</span>
        <span className="slider-value">{fmt ? fmt(value) : value}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} />
      {desc && <p className="slider-desc">{desc}</p>}
    </div>
  )
}

function FilterSettings({ settings, defaults, onChange }) {
  if (!settings) return null
  const set = (key) => (val) => onChange((prev) => ({ ...prev, [key]: val }))
  return (
    <details className="filter-settings-details">
      <summary className="filter-settings-summary">Scoring settings</summary>
      <div className="slider-group">
        <p className="slider-desc">Labels only — no paper is ever removed. Saved defaults live in config.yaml.</p>
        <Slider label="Semantic weight" min={0} max={1} step={0.05} value={settings.weightSemantic}
          fmt={(v) => `${Math.round(v * 100)}% / ${Math.round((1 - v) * 100)}% citations`}
          desc="Topic similarity vs. citation impact in the combined score." onChange={set('weightSemantic')} />
        <Slider label="Citation reference" min={50} max={2000} step={50} value={settings.citationRef}
          fmt={(v) => v.toLocaleString()} desc="Citations at which the impact score saturates."
          onChange={set('citationRef')} />
        <Slider label="Relevant threshold" min={0.1} max={0.95} step={0.01} value={settings.thresholdRelevant}
          fmt={(v) => v.toFixed(2)} onChange={set('thresholdRelevant')} />
        <Slider label="Potential threshold" min={0.05} max={0.9} step={0.01} value={settings.thresholdPotential}
          fmt={(v) => v.toFixed(2)} onChange={set('thresholdPotential')} />
        {defaults && <button className="reset-link" onClick={() => onChange(defaults)}>Reset to config.yaml defaults</button>}
      </div>
    </details>
  )
}

export default function Sidebar({
  project, papers, visibleIds, prisma, clusters,
  activeCluster, onClusterSelect, onClustersGenerated, onReuseSearch, onShowStarred, onShowReviews,
  filterSettings, defaults, onFilterSettings,
}) {
  return (
    <>
      <StatCards papers={papers} onShowStarred={onShowStarred} onShowReviews={onShowReviews} />
      <Prisma prisma={prisma} onReuseSearch={onReuseSearch} />
      {project && <Exports project={project} total={papers.length} visibleIds={visibleIds}
        starredIds={papers.filter((p) => p.starred).map((p) => p.id)}
        missingDetails={papers.filter((p) => p.externalIds?.DOI && !p.volume && !p.pages).length}
        readingIds={[...papers].filter((p) => p.starred || p.evaluation?.category === 'relevante')
          .sort((a, b) => (Number(!!b.starred) - Number(!!a.starred)) || (b.evaluation?.score ?? 0) - (a.evaluation?.score ?? 0))
          .map((p) => p.id)}
        onReload={onClustersGenerated} />}
      <div className="divider" />
      <ClusterFilter clusters={clusters} activeCluster={activeCluster} onSelect={onClusterSelect}
        project={project} onGenerated={onClustersGenerated} />
      <div className="divider" />
      <FilterSettings settings={filterSettings} defaults={defaults} onChange={onFilterSettings} />
    </>
  )
}
