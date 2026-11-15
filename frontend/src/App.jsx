import { useEffect, useMemo, useRef, useState } from 'react'
import {
  getClusters, getConfig, getMeta, getPapers, getPrisma, getProjects, setContext, streamSearch,
} from './api/client.js'

import ImportModal   from './components/ImportModal.jsx'
import Masthead      from './components/Masthead.jsx'
import PaperDetail   from './components/PaperDetail.jsx'
import PaperLibrary  from './components/PaperLibrary.jsx'
import PipelineLog   from './components/PipelineLog.jsx'
import SearchPanel   from './components/SearchPanel.jsx'
import SemanticQuery from './components/SemanticQuery.jsx'
import Sidebar       from './components/Sidebar.jsx'

// ── Client-side re-scoring ─────────────────────────────────────────────────────
// Mirrors src/evaluation/scoring.py so weights/thresholds can be tuned live.
// Nothing is ever removed: the category is only a label used for filtering.
function recompute(papers, s, simRange) {
  if (!s || !simRange) return papers
  const [lo, hi] = simRange
  return papers.map((paper) => {
    const ev = paper.evaluation
    if (!ev || ev.similarity == null) return paper
    const sem = Math.min(1, Math.max(0, (ev.similarity - lo) / Math.max(hi - lo, 1e-9)))
    const imp = Math.min(Math.log1p(Math.max(0, paper.citationCount || 0)) / Math.log1p(Math.max(1, s.citationRef)), 1)
    const score = s.weightSemantic * sem + (1 - s.weightSemantic) * imp
    const category =
      score >= s.thresholdRelevant ? 'relevante'
      : score >= s.thresholdPotential ? 'potencialmente_relevante'
      : 'no_relevante'
    return {
      ...paper,
      evaluation: { ...ev, semantic_score: sem, impact_score: imp, score, category },
    }
  })
}

export function settingsFromConfig(ev) {
  return {
    weightSemantic:     ev.weights.semantic,
    citationRef:        ev.citation_ref,
    thresholdRelevant:  ev.thresholds.relevant,
    thresholdPotential: ev.thresholds.potentially,
  }
}

const SORTERS = {
  score:     (p) => p.evaluation?.score ?? -1,
  citations: (p) => p.citationCount ?? -1,
  year:      (p) => p.year ?? -1,
}

export default function App() {
  const [evalConfig, setEvalConfig]         = useState(null)
  const [filterSettings, setFilterSettings] = useState(null)
  const [projects, setProjects]             = useState([])
  const [project, setProject]               = useState('')
  const [meta, setMeta]                     = useState(null)
  const [rawPapers, setRawPapers]           = useState([])
  const [clusters, setClusters]             = useState(null)
  const [prisma, setPrisma]                 = useState(null)
  const [activeCluster, setActiveCluster]   = useState(null)
  const [categoryFilter, setCategoryFilter] = useState(null)
  const [hideFlagged, setHideFlagged]       = useState(false)
  const [textFilter, setTextFilter]         = useState('')
  const [sortBy, setSortBy]                 = useState('score')
  const [selectedPaper, setSelectedPaper]   = useState(null)
  const [searchLogs, setSearchLogs]         = useState([])
  const [isSearching, setIsSearching]       = useState(false)
  const [activeTab, setActiveTab]           = useState('library')
  const [showImport, setShowImport]         = useState(false)
  const searchCtrl = useRef(null)

  useEffect(() => {
    getConfig().then((c) => {
      setEvalConfig(c.evaluation)
      setFilterSettings(settingsFromConfig(c.evaluation))
    }).catch(console.error)
    loadProjects()
  }, [])

  const allPapers = useMemo(
    () => recompute(rawPapers, filterSettings, evalConfig?.similarity_range),
    [rawPapers, filterSettings, evalConfig],
  )

  // Every filter except the category pills (so the pills can show counts for this scope).
  const scopedPapers = useMemo(() => {
    let papers = allPapers
    if (activeCluster != null && clusters?.clusters) {
      const c = clusters.clusters.find((x) => x.id === activeCluster)
      if (c) {
        const ids = new Set(c.paper_ids || [])
        papers = papers.filter((p) => ids.has(p.id))
      }
    }
    if (hideFlagged) papers = papers.filter((p) => !(p.flags || []).length)
    const q = textFilter.trim().toLowerCase()
    if (q) {
      papers = papers.filter((p) =>
        `${p.title} ${p.abstract} ${(p.authors || []).map((a) => a.name).join(' ')} ${p.venue}`
          .toLowerCase().includes(q))
    }
    return papers
  }, [allPapers, activeCluster, clusters, hideFlagged, textFilter])

  const displayPapers = useMemo(() => {
    const papers = categoryFilter
      ? scopedPapers.filter((p) => (p.evaluation?.category || 'unevaluated') === categoryFilter)
      : scopedPapers
    const key = SORTERS[sortBy]
    return [...papers].sort((a, b) => key(b) - key(a))
  }, [scopedPapers, categoryFilter, sortBy])

  function loadProjects() { return getProjects().then(setProjects).catch(console.error) }

  const loadProjectData = (p = project) => {
    if (!p) return Promise.resolve()
    return Promise.all([
      getPapers(p).then(setRawPapers),
      getClusters(p).then(setClusters),
      getPrisma(p).then(setPrisma),
      getMeta(p).then(setMeta),
    ]).catch(console.error)
  }

  useEffect(() => {
    setActiveCluster(null); setCategoryFilter(null); setSelectedPaper(null); setSearchLogs([])
    if (!project) { setRawPapers([]); setClusters(null); setPrisma(null); setMeta(null); return }
    loadProjectData(project)
  }, [project])

  const handleSearch = async (params) => {
    searchCtrl.current?.abort()
    const ctrl = new AbortController()
    searchCtrl.current = ctrl
    setIsSearching(true)
    setSearchLogs([])
    try {
      for await (const event of streamSearch(project, params, ctrl.signal)) {
        setSearchLogs((prev) => [...prev, event])
        if (event.type === 'result') await loadProjectData()
      }
    } catch (err) {
      if (err.name !== 'AbortError') setSearchLogs((prev) => [...prev, { type: 'error', message: err.message }])
    } finally {
      setIsSearching(false)
    }
  }

  const tabBadge = allPapers.length === 0 ? null
    : displayPapers.length < allPapers.length ? `${displayPapers.length}/${allPapers.length}`
    : `${allPapers.length}`

  const openById = (id) => {
    const p = allPapers.find((x) => x.id === id)
    if (p) setSelectedPaper(p)
  }

  return (
    <div className="app">
      <Masthead
        projects={projects}
        currentProject={project}
        onProjectChange={setProject}
        onProjectsReload={loadProjects}
        onImport={() => setShowImport(true)}
      />

      <div className="main-layout">
        <div className="main-column">
          <SearchPanel
            onSearch={handleSearch}
            onApplyContext={(ctx) => setContext(project, ctx).then(() => loadProjectData()).catch((e) => alert(e.message))}
            isSearching={isSearching}
            disabled={!project}
            projectContext={meta?.context || ''}
            project={project}
          />

          {searchLogs.length > 0 && <PipelineLog logs={searchLogs} isRunning={isSearching} />}

          <div className="tab-bar">
            <button className={`tab-btn ${activeTab === 'library' ? 'active' : ''}`}
              onClick={() => setActiveTab('library')}>
              Papers{tabBadge && <span className="tab-badge">{tabBadge}</span>}
            </button>
            <button className={`tab-btn ${activeTab === 'query' ? 'active' : ''}`}
              onClick={() => setActiveTab('query')}>
              Ask
            </button>
          </div>

          <div className="main-column-scroll">
            {activeTab === 'library' && (
              <PaperLibrary
                papers={displayPapers}
                scopedPapers={scopedPapers}
                libraryEmpty={allPapers.length === 0}
                onSelectPaper={setSelectedPaper}
                activeClusterLabel={activeCluster != null
                  ? clusters?.clusters?.find((c) => c.id === activeCluster)?.label : null}
                onClearCluster={() => setActiveCluster(null)}
                categoryFilter={categoryFilter}
                onCategoryFilter={setCategoryFilter}
                hideFlagged={hideFlagged}
                onHideFlagged={setHideFlagged}
                textFilter={textFilter}
                onTextFilter={setTextFilter}
                sortBy={sortBy}
                onSortBy={setSortBy}
              />
            )}
            {activeTab === 'query' && <SemanticQuery project={project} onOpen={openById} />}
          </div>
        </div>

        <aside className="sidebar">
          <Sidebar
            project={project}
            papers={allPapers}
            visibleIds={displayPapers.map((p) => p.id)}
            prisma={prisma}
            clusters={clusters}
            activeCluster={activeCluster}
            onClusterSelect={setActiveCluster}
            onClustersGenerated={() => loadProjectData()}
            filterSettings={filterSettings}
            defaults={evalConfig ? settingsFromConfig(evalConfig) : null}
            onFilterSettings={setFilterSettings}
          />
        </aside>
      </div>

      {selectedPaper && <PaperDetail paper={selectedPaper} onClose={() => setSelectedPaper(null)} />}

      {showImport && (
        <ImportModal
          project={project}
          projectContext={meta?.context || ''}
          onClose={() => setShowImport(false)}
          onDone={() => loadProjectData()}
        />
      )}
    </div>
  )
}
