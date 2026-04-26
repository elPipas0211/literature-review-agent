import { useEffect, useMemo, useRef, useState } from 'react'
import { getClusters, getPapers, getProjects, streamSearch } from './api/client.js'

import ImportModal   from './components/ImportModal.jsx'
import Masthead      from './components/Masthead.jsx'
import PaperDetail   from './components/PaperDetail.jsx'
import PaperLibrary  from './components/PaperLibrary.jsx'
import PipelineLog   from './components/PipelineLog.jsx'
import SearchPanel   from './components/SearchPanel.jsx'
import SemanticQuery from './components/SemanticQuery.jsx'
import Sidebar       from './components/Sidebar.jsx'

// ── Client-side re-evaluation ──────────────────────────────────────────────────
// Mirrors embedding_evaluator.py: log1p(cites)/log1p(ref), weighted sum, thresholds.
function recompute(papers, s) {
  const wImp = 1 - s.weightSemantic
  return papers.map((paper) => {
    const ev = paper.evaluation
    if (!ev || ev.semantic_score == null) return paper   // not evaluated — keep as-is

    const sem = ev.semantic_score
    if (sem < s.minSemantic) {
      return { ...paper, evaluation: { ...ev, score: sem, category: 'descartado_semantica' } }
    }
    const cites = Math.max(0, paper.citationCount || 0)
    const ref   = Math.max(1, s.citationRef)
    const imp   = Math.min(Math.log1p(cites) / Math.log1p(ref), 1.0)
    const score = s.weightSemantic * sem + wImp * imp

    const category =
      score >= s.thresholdRelevant  ? 'relevante'
      : score >= s.thresholdPotential ? 'potencialmente_relevante'
      : 'no_relevante'

    return {
      ...paper,
      evaluation: {
        ...ev,
        score:        Math.round(score * 10000) / 10000,
        impact_score: Math.round(imp   * 10000) / 10000,
        category,
      },
    }
  })
}

const DEFAULT_SETTINGS = {
  minSemantic:        0.40,
  weightSemantic:     0.80,
  citationRef:        300,
  thresholdRelevant:  0.50,
  thresholdPotential: 0.30,
}

// ── App ────────────────────────────────────────────────────────────────────────
export default function App() {
  const [projects, setProjects]             = useState([])
  const [project, setProject]               = useState('')
  const [rawPapers, setRawPapers]           = useState([])      // from API
  const [clusters, setClusters]             = useState(null)
  const [activeCluster, setActiveCluster]   = useState(null)
  const [categoryFilter, setCategoryFilter] = useState(null)    // null | 'relevante' | 'potencialmente_relevante'
  const [selectedPaper, setSelectedPaper]   = useState(null)
  const [searchLogs, setSearchLogs]         = useState([])
  const [isSearching, setIsSearching]       = useState(false)
  const [activeTab, setActiveTab]           = useState('library')
  const [showImport, setShowImport]         = useState(false)
  const [filterSettings, setFilterSettings] = useState(DEFAULT_SETTINGS)
  const searchCtrl = useRef(null)

  // ── Re-evaluate papers whenever raw papers or settings change ──────────────
  const allPapers = useMemo(() => recompute(rawPapers, filterSettings), [rawPapers, filterSettings])

  // ── Apply cluster + category filters ──────────────────────────────────────
  const displayPapers = useMemo(() => {
    // Hide papers rejected by the semantic floor (minSemantic slider)
    let papers = allPapers.filter((p) => p.evaluation?.category !== 'descartado_semantica')

    if (activeCluster != null && clusters?.clusters) {
      const clusterObj = clusters.clusters.find((c) => c.id === activeCluster)
      if (clusterObj) {
        const dois = new Set(clusterObj.papers.map((p) => (p.doi || '').toLowerCase()).filter(Boolean))
        papers = papers.filter((p) => dois.has(((p.externalIds?.DOI) || '').toLowerCase()))
      }
    }

    if (categoryFilter) {
      papers = papers.filter((p) => p.evaluation?.category === categoryFilter)
    }

    return papers
  }, [allPapers, activeCluster, clusters, categoryFilter])

  // ── Load projects ──────────────────────────────────────────────────────────
  const loadProjects = () => getProjects().then(setProjects).catch(console.error)
  useEffect(() => { loadProjects() }, [])

  // ── Load papers + clusters when project changes ────────────────────────────
  useEffect(() => {
    if (!project) { setRawPapers([]); setClusters(null); setActiveCluster(null); setCategoryFilter(null); return }
    loadPapers()
    loadClusters()
  }, [project])

  const loadPapers   = () => getPapers(project).then(setRawPapers).catch(console.error)
  const loadClusters = () => getClusters(project).then(setClusters).catch(console.error)

  // ── Search ─────────────────────────────────────────────────────────────────
  const handleSearch = async (query, context, maxResults) => {
    searchCtrl.current?.abort()
    const ctrl = new AbortController()
    searchCtrl.current = ctrl
    setIsSearching(true)
    setSearchLogs([])
    try {
      for await (const event of streamSearch(project, { query, context, max_results: maxResults }, ctrl.signal)) {
        setSearchLogs((prev) => [...prev, event])
        if (event.type === 'done') { await loadPapers(); await loadClusters() }
      }
    } catch (err) {
      if (err.name !== 'AbortError')
        setSearchLogs((prev) => [...prev, { type: 'error', message: err.message }])
    } finally {
      setIsSearching(false)
    }
  }

  // ── Tab badge text ─────────────────────────────────────────────────────────
  const tabBadge = (() => {
    if (allPapers.length === 0) return null
    const shown = displayPapers.length
    const total = allPapers.length
    return shown < total ? `${shown}/${total}` : `${total}`
  })()

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="app">
      <Masthead
        projects={projects}
        currentProject={project}
        onProjectChange={(p) => {
          setProject(p)
          setActiveCluster(null)
          setCategoryFilter(null)
          setSelectedPaper(null)
        }}
        onProjectsReload={loadProjects}
        onImport={() => setShowImport(true)}
      />

      <div className="main-layout">
        {/* ── Left column ── */}
        <div className="main-column">
          <SearchPanel
            onSearch={handleSearch}
            isSearching={isSearching}
            disabled={!project}
          />

          {searchLogs.length > 0 && (
            <PipelineLog logs={searchLogs} isRunning={isSearching} />
          )}

          <div className="tab-bar">
            <button
              className={`tab-btn ${activeTab === 'library' ? 'active' : ''}`}
              onClick={() => setActiveTab('library')}
            >
              Papers
              {tabBadge && <span className="tab-badge">{tabBadge}</span>}
            </button>
            <button
              className={`tab-btn ${activeTab === 'query' ? 'active' : ''}`}
              onClick={() => setActiveTab('query')}
            >
              Ask
            </button>
          </div>

          <div className="main-column-scroll">
            {activeTab === 'library' && (
              <PaperLibrary
                papers={displayPapers}
                onSelectPaper={setSelectedPaper}
                activeCluster={activeCluster}
                onClearCluster={() => setActiveCluster(null)}
                categoryFilter={categoryFilter}
                onCategoryFilter={setCategoryFilter}
              />
            )}
            {activeTab === 'query' && (
              <SemanticQuery project={project} />
            )}
          </div>
        </div>

        {/* ── Right sidebar ── */}
        <aside className="sidebar">
          <Sidebar
            project={project}
            papers={allPapers}
            clusters={clusters}
            activeCluster={activeCluster}
            onClusterSelect={setActiveCluster}
            onClustersGenerated={() => { loadClusters(); loadPapers() }}
            filterSettings={filterSettings}
            onFilterSettings={setFilterSettings}
          />
        </aside>
      </div>

      {selectedPaper && (
        <PaperDetail
          paper={selectedPaper}
          onClose={() => setSelectedPaper(null)}
        />
      )}

      {showImport && (
        <ImportModal
          project={project}
          onClose={() => setShowImport(false)}
          onDone={() => { loadPapers(); setShowImport(false) }}
        />
      )}
    </div>
  )
}
