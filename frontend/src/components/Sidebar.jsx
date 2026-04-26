import { useState } from 'react'
import { streamClusters } from '../api/client.js'

// ── Stat cards ────────────────────────────────────────────────────────────────
function StatCards({ papers }) {
  const total    = papers.length
  const relevant = papers.filter((p) => p.evaluation?.category === 'relevante').length
  const potential = papers.filter((p) => p.evaluation?.category === 'potencialmente_relevante').length
  const scored   = papers.filter((p) => p.evaluation?.score != null)
  const avg      = scored.length > 0
    ? scored.reduce((s, p) => s + p.evaluation.score, 0) / scored.length
    : null

  return (
    <section className="sidebar-section">
      <div className="sidebar-label">Collection</div>
      <div className="stat-cards">
        <div className="stat-card">
          <span className="stat-card-label">Total</span>
          <span className="stat-card-number">{total}</span>
        </div>
        <div className="stat-card relevant">
          <span className="stat-card-label">Relevant</span>
          <span className="stat-card-number">{relevant}</span>
        </div>
        <div className="stat-card potential">
          <span className="stat-card-label">Potential</span>
          <span className="stat-card-number">{potential}</span>
        </div>
        {avg != null && (
          <div className="stat-card score">
            <span className="stat-card-label">Avg. score</span>
            <span className="stat-card-number">{avg.toFixed(3)}</span>
          </div>
        )}
      </div>
    </section>
  )
}

// ── Cluster filter ─────────────────────────────────────────────────────────────
function ClusterFilter({ clusters, activeCluster, onSelect, project, onGenerated }) {
  const [generating, setGenerating] = useState(false)
  const [log, setLog] = useState([])
  const list = clusters?.clusters || []

  const handleGenerate = async () => {
    setGenerating(true)
    setLog([])
    const ctrl = new AbortController()
    try {
      for await (const ev of streamClusters(project, {}, ctrl.signal)) {
        if (ev.type === 'loaded')      setLog((l) => [...l, `Loaded ${ev.count} papers`])
        if (ev.type === 'elbow_start') setLog((l) => [...l, `Trying k=${ev.k_min}…${ev.k_max}`])
        if (ev.type === 'elbow_step')  setLog((l) => [...l, `  k=${ev.k}  inertia=${ev.inertia}`])
        if (ev.type === 'clustered')   setLog((l) => [...l, `Elbow at k=${ev.k} → ${ev.num_clusters} clusters`])
        if (ev.type === 'labeling')    setLog((l) => [...l, 'Labeling clusters…'])
        if (ev.type === 'done')        { setLog((l) => [...l, `Done — ${ev.num_clusters} clusters`]); onGenerated() }
        if (ev.type === 'error')       setLog((l) => [...l, `Error: ${ev.message}`])
      }
    } catch (err) {
      if (err.name !== 'AbortError') setLog((l) => [...l, `Error: ${err.message}`])
    } finally {
      setGenerating(false)
    }
  }

  return (
    <section className="sidebar-section">
      <div className="sidebar-label">Clusters</div>
      {list.length > 0 ? (
        <div className="cluster-list">
          <button
            className={`cluster-all-btn${activeCluster == null ? ' active' : ''}`}
            onClick={() => onSelect(null)}
          >
            All papers
          </button>
          {list.map((c) => (
            <div
              key={c.id}
              className={`cluster-card${activeCluster === c.id ? ' active' : ''}`}
              onClick={() => onSelect(activeCluster === c.id ? null : c.id)}
            >
              <span className="cluster-card-name">{c.label}</span>
              <span className="cluster-card-badge">{c.paper_count}</span>
            </div>
          ))}
        </div>
      ) : (
        <p style={{ fontSize: 11, color: 'var(--ink-faint)' }}>No clusters yet.</p>
      )}
      <button
        className="btn btn-outline btn-sm btn-block"
        onClick={handleGenerate}
        disabled={generating || !project}
        style={{ marginTop: 4 }}
      >
        {generating ? 'Generating…' : list.length > 0 ? 'Regenerate' : 'Generate clusters'}
      </button>
      {log.length > 0 && (
        <div style={{ fontSize: 10, color: 'var(--ink-faint)', lineHeight: 1.6 }}>
          {log.map((l, i) => <div key={i}>{l}</div>)}
        </div>
      )}
    </section>
  )
}

// ── Filter settings ────────────────────────────────────────────────────────────
const DEFAULTS = {
  minSemantic:        0.40,
  weightSemantic:     0.80,
  citationRef:        300,
  thresholdRelevant:  0.50,
  thresholdPotential: 0.30,
}

function Slider({ label, desc, sub, min, max, step, value, fmt, onChange }) {
  return (
    <div className="slider-row">
      <div className="slider-header">
        <span className="slider-name">{label}</span>
        <span className="slider-value">{fmt ? fmt(value) : value}</span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {desc && <p className="slider-desc">{desc}</p>}
      {sub  && <span className="slider-sub">{sub(value)}</span>}
    </div>
  )
}

function FilterSettings({ settings, onChange }) {
  // Functional updater form: each batched call receives the already-updated
  // state as `prev`, not the stale `settings` closure captured at render time.
  const set = (key) => (val) => onChange(prev => ({ ...prev, [key]: val }))
  const reset = () => onChange(DEFAULTS)

  return (
    <details className="filter-settings-details">
      <summary className="filter-settings-summary">Filter settings</summary>
      <div className="slider-group">
        <Slider
          label="Min. semantic score"
          desc="Abstracts below this threshold are discarded regardless of citations."
          min={0} max={0.8} step={0.01}
          value={settings.minSemantic}
          fmt={(v) => v.toFixed(2)}
          onChange={set('minSemantic')}
        />
        <Slider
          label="Semantic weight"
          desc="Balance between topic relevance and citation impact in the combined score."
          min={0} max={1} step={0.01}
          value={settings.weightSemantic}
          fmt={(v) => `${Math.round(v * 100)}%`}
          sub={(v) => `Impact weight: ${Math.round((1 - v) * 100)}%`}
          onChange={set('weightSemantic')}
        />
        <Slider
          label="Citation reference"
          desc="Papers with this many citations reach the maximum impact score."
          min={50} max={2000} step={50}
          value={settings.citationRef}
          fmt={(v) => v.toLocaleString()}
          onChange={set('citationRef')}
        />
        <Slider
          label="Relevant threshold"
          desc="Minimum combined score to mark a paper as relevant."
          min={0.1} max={0.95} step={0.01}
          value={settings.thresholdRelevant}
          fmt={(v) => v.toFixed(2)}
          onChange={set('thresholdRelevant')}
        />
        <Slider
          label="Potential threshold"
          desc="Minimum score to keep a paper as potentially relevant."
          min={0.05} max={0.9} step={0.01}
          value={settings.thresholdPotential}
          fmt={(v) => v.toFixed(2)}
          onChange={set('thresholdPotential')}
        />
        <button className="reset-link" onClick={reset}>Reset to defaults</button>
      </div>
    </details>
  )
}

// ── Main sidebar ───────────────────────────────────────────────────────────────
export default function Sidebar({
  project, papers, clusters,
  activeCluster, onClusterSelect, onClustersGenerated,
  filterSettings, onFilterSettings,
}) {
  return (
    <>
      <StatCards papers={papers} />
      <div className="divider" />
      <ClusterFilter
        clusters={clusters}
        activeCluster={activeCluster}
        onSelect={onClusterSelect}
        project={project}
        onGenerated={onClustersGenerated}
      />
      <div className="divider" />
      <FilterSettings settings={filterSettings} onChange={onFilterSettings} />
    </>
  )
}
