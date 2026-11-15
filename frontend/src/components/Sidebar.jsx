import { useState } from 'react'
import { downloadExport, streamClusters } from '../api/client.js'

const SOURCE = { semantic_scholar: 'Semantic Scholar', openalex: 'OpenAlex', scopus_csv: 'Scopus (CSV)',
                 wos_csv: 'Web of Science (CSV)', zotero_csv: 'Zotero (CSV)' }

function StatCards({ papers }) {
  const count = (c) => papers.filter((p) => p.evaluation?.category === c).length
  return (
    <section className="sidebar-section">
      <div className="sidebar-label">Collection</div>
      <div className="stat-cards">
        <div className="stat-card"><span className="stat-card-label">Total</span><span className="stat-card-number">{papers.length}</span></div>
        <div className="stat-card relevant"><span className="stat-card-label">Relevant</span><span className="stat-card-number">{count('relevante')}</span></div>
        <div className="stat-card potential"><span className="stat-card-label">Potential</span><span className="stat-card-number">{count('potencialmente_relevante')}</span></div>
        <div className="stat-card"><span className="stat-card-label">Low</span><span className="stat-card-number">{count('no_relevante')}</span></div>
      </div>
    </section>
  )
}

function Prisma({ prisma }) {
  if (!prisma || !prisma.sessions?.length) return null
  return (
    <section className="sidebar-section">
      <div className="sidebar-label">PRISMA — identification</div>
      <table className="prisma-table">
        <tbody>
          {Object.entries(prisma.identified_by_source).map(([s, n]) => (
            <tr key={s}><td>Records from {SOURCE[s] || s}</td><td>{n}</td></tr>
          ))}
          <tr className="sum"><td>Records identified</td><td>{prisma.identified_total}</td></tr>
          <tr><td>Duplicates removed</td><td>−{prisma.duplicates_removed}</td></tr>
          <tr className="sum"><td>Records to screen</td><td>{prisma.records_in_library}</td></tr>
        </tbody>
      </table>
      <details>
        <summary className="hint">{prisma.sessions.length} searches / imports</summary>
        <ul className="session-list">
          {prisma.sessions.map((s) => (
            <li key={s.session_id}>
              <span className="session-date">{(s.started_at || '').slice(0, 16).replace('T', ' ')}</span>{' '}
              {s.kind === 'import' ? `📄 ${s.file}` : `🔎 “${s.query}”`}
              {(s.year_from || s.year_to) && ` [${s.year_from || ''}–${s.year_to || ''}]`}
              {' '}→ {s.identified} found, {s.added} new
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

function Exports({ project, total, visibleIds }) {
  const [error, setError] = useState(null)
  const run = (fmt, ids) => downloadExport(project, fmt, ids).catch((e) => setError(e.message))
  const partial = visibleIds.length < total
  return (
    <section className="sidebar-section">
      <div className="sidebar-label">Export</div>
      <div className="export-grid">
        {['csv', 'ris', 'bib'].map((fmt) => (
          <button key={fmt} className="btn btn-outline btn-sm" disabled={!total}
            onClick={() => run(fmt, null)} title={`Whole library (${total})`}>
            {fmt.toUpperCase()}
          </button>
        ))}
      </div>
      {partial && (
        <div className="export-grid">
          {['csv', 'ris', 'bib'].map((fmt) => (
            <button key={fmt} className="btn btn-ghost btn-sm" disabled={!visibleIds.length}
              onClick={() => run(fmt, visibleIds)}>
              {fmt.toUpperCase()} · view ({visibleIds.length})
            </button>
          ))}
        </div>
      )}
      <p className="hint">CSV/RIS → ASReview, Rayyan, Zotero. BibTeX keys match the “Copy” button.</p>
      {error && <p className="hint" style={{ color: 'var(--error)' }}>{error}</p>}
    </section>
  )
}

function ClusterFilter({ clusters, activeCluster, onSelect, project, onGenerated }) {
  const [generating, setGenerating] = useState(false)
  const [onlyRelevant, setOnlyRelevant] = useState(true)
  const [log, setLog] = useState([])
  const list = clusters?.clusters || []

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
  activeCluster, onClusterSelect, onClustersGenerated,
  filterSettings, defaults, onFilterSettings,
}) {
  return (
    <>
      <StatCards papers={papers} />
      <Prisma prisma={prisma} />
      {project && <Exports project={project} total={papers.length} visibleIds={visibleIds} />}
      <div className="divider" />
      <ClusterFilter clusters={clusters} activeCluster={activeCluster} onSelect={onClusterSelect}
        project={project} onGenerated={onClustersGenerated} />
      <div className="divider" />
      <FilterSettings settings={filterSettings} defaults={defaults} onChange={onFilterSettings} />
    </>
  )
}
