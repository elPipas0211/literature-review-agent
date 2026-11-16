import { useEffect, useMemo, useRef, useState } from 'react'
import {
  annotatePaper, getClusters, getConfig, getMeta, getPapers, getPrisma, getProjects, setContext,
  streamSearch, streamSnowball,
} from './api/client.js'
import { loadPref, savePref } from './prefs.js'

import ErrorBoundary from './components/ErrorBoundary.jsx'
import ImportModal   from './components/ImportModal.jsx'
import MapView       from './components/MapView.jsx'
import Masthead      from './components/Masthead.jsx'
import PaperDetail   from './components/PaperDetail.jsx'
import PaperLibrary  from './components/PaperLibrary.jsx'
import PipelineLog   from './components/PipelineLog.jsx'
import SearchPanel   from './components/SearchPanel.jsx'
import SemanticQuery from './components/SemanticQuery.jsx'
import Sidebar       from './components/Sidebar.jsx'
import TrendsView    from './components/TrendsView.jsx'

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

const TABS = [
  { key: 'library', label: 'Papers' },
  { key: 'map',     label: 'Map' },
  { key: 'trends',  label: 'Trends' },
  { key: 'query',   label: 'Ask' },
]

const DEFAULT_VIEW = {
  categoryFilter: null, hideFlagged: false, starredOnly: false, reviewsOnly: false,
  sortBy: 'score', activeTab: 'library',
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
  const [view, setView]                     = useState(DEFAULT_VIEW)
  const [textFilter, setTextFilter]         = useState('')
  const [selectedId, setSelectedId]         = useState(null)
  const [searchLogs, setSearchLogs]         = useState([])
  const [isSearching, setIsSearching]       = useState(false)
  const [showImport, setShowImport]         = useState(false)
  const [prefill, setPrefill]               = useState(null)
  const [annotateError, setAnnotateError]   = useState(null)
  const searchCtrl = useRef(null)
  const prefsFor = useRef('')      // project whose preferences are currently loaded
  const scrollRef = useRef(null)

  const setViewKey = (key) => (value) => setView((v) => ({ ...v, [key]: value }))
  const { categoryFilter, hideFlagged, starredOnly, reviewsOnly, sortBy, activeTab } = view
  const setActiveTab = setViewKey('activeTab')

  useEffect(() => { scrollRef.current?.scrollTo(0, 0) }, [activeTab])

  useEffect(() => {
    getConfig().then((c) => {
      setEvalConfig(c.evaluation)
      setFilterSettings((prev) => prev ?? settingsFromConfig(c.evaluation))
    }).catch(console.error)
    loadProjects().then((list) => {
      const last = loadPref('lastProject')
      if (last && list?.some((p) => (p.name ?? p) === last)) setProject(last)
    })
  }, [])

  const allPapers = useMemo(
    () => recompute(rawPapers, filterSettings, evalConfig?.similarity_range),
    [rawPapers, filterSettings, evalConfig],
  )
  const papersById = useMemo(() => Object.fromEntries(allPapers.map((p) => [p.id, p])), [allPapers])
  const selectedPaper = selectedId ? papersById[selectedId] : null

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
    if (starredOnly) papers = papers.filter((p) => p.starred)
    if (reviewsOnly) papers = papers.filter((p) => p.is_review)
    const q = textFilter.trim().toLowerCase()
    if (q) {
      papers = papers.filter((p) =>
        `${p.title} ${p.abstract} ${(p.authors || []).map((a) => a.name).join(' ')} ${p.venue} ${(p.keywords || []).join(' ')} ${p.note || ''}`
          .toLowerCase().includes(q))
    }
    return papers
  }, [allPapers, activeCluster, clusters, hideFlagged, starredOnly, reviewsOnly, textFilter])

  const displayPapers = useMemo(() => {
    const papers = categoryFilter
      ? scopedPapers.filter((p) => (p.evaluation?.category || 'unevaluated') === categoryFilter)
      : scopedPapers
    const key = SORTERS[sortBy] || SORTERS.score
    return [...papers].sort((a, b) => key(b) - key(a))
  }, [scopedPapers, categoryFilter, sortBy])

  function loadProjects() {
    return getProjects().then((list) => { setProjects(list); return list }).catch((e) => { console.error(e); return [] })
  }

  const loadProjectData = (p = project) => {
    if (!p) return Promise.resolve()
    return Promise.all([
      getPapers(p).then(setRawPapers),
      getClusters(p).then(setClusters),
      getPrisma(p).then(setPrisma),
      getMeta(p).then(setMeta),
    ]).catch(console.error)
  }

  // Project switch: load its data and its remembered view/scoring settings.
  useEffect(() => {
    setActiveCluster(null); setSelectedId(null); setSearchLogs([]); setTextFilter(''); setPrefill(null)
    if (project) savePref('lastProject', project)
    const stored = project ? loadPref(`project:${project}`) : null
    prefsFor.current = project
    setView({ ...DEFAULT_VIEW, ...(stored?.view || {}) })
    if (stored?.filterSettings) setFilterSettings(stored.filterSettings)
    else if (evalConfig) setFilterSettings(settingsFromConfig(evalConfig))
    if (!project) { setRawPapers([]); setClusters(null); setPrisma(null); setMeta(null); return }
    loadProjectData(project)
  }, [project])

  // Remember view + scoring settings per project (only after that project's prefs were loaded).
  useEffect(() => {
    if (!project || prefsFor.current !== project) return
    savePref(`project:${project}`, { view, filterSettings })
  }, [view, filterSettings])

  const handleSearch = (params) => runStream((signal) => streamSearch(project, params, signal))

  const handleSnowball = (id, direction, max) => {
    setSelectedId(null)
    setActiveTab('library')
    return runStream((signal) => streamSnowball(project, { id, direction, max_results: max }, signal))
  }

  const runStream = async (open) => {
    searchCtrl.current?.abort()
    const ctrl = new AbortController()
    searchCtrl.current = ctrl
    setIsSearching(true)
    setSearchLogs([])
    try {
      for await (const event of open(ctrl.signal)) {
        setSearchLogs((prev) => [...prev, event])
        if (event.type === 'result') await loadProjectData()
      }
    } catch (err) {
      if (err.name !== 'AbortError') setSearchLogs((prev) => [...prev, { type: 'error', message: err.message }])
    } finally {
      setIsSearching(false)
    }
  }

  // Reading list: optimistic update, rolled back if the server refuses.
  const handleAnnotate = async (id, fields) => {
    const before = rawPapers.find((p) => p.id === id)
    if (!before) return
    setAnnotateError(null)
    setRawPapers((ps) => ps.map((p) => (p.id === id ? { ...p, ...fields } : p)))
    try {
      await annotatePaper(project, id, fields)
    } catch (err) {
      setRawPapers((ps) => ps.map((p) => (p.id === id ? before : p)))
      setAnnotateError(`Could not save: ${err.message}`)
    }
  }

  const handleReuseSearch = (s) => {
    setPrefill({ query: s.query || '', year_from: s.year_from, year_to: s.year_to,
                 max_results: s.max_results, nonce: Date.now() })
  }

  const showCluster = (id) => { setActiveCluster(id); setActiveTab('library') }

  const tabBadge = allPapers.length === 0 ? null
    : displayPapers.length < allPapers.length ? `${displayPapers.length}/${allPapers.length}`
    : `${allPapers.length}`

  const openById = (id) => { if (papersById[id]) setSelectedId(id) }

  // Show-more pagination restarts whenever the filters change (not when a paper is starred).
  const listKey = [project, activeCluster, categoryFilter, hideFlagged, starredOnly, reviewsOnly, textFilter, sortBy].join('|')

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
          <ErrorBoundary area="the search panel">
            <SearchPanel
              onSearch={handleSearch}
              onApplyContext={(ctx) => setContext(project, ctx).then(() => loadProjectData()).catch((e) => alert(e.message))}
              isSearching={isSearching}
              disabled={!project}
              projectContext={meta?.context || ''}
              project={project}
              prefill={prefill}
            />
          </ErrorBoundary>

          {searchLogs.length > 0 && <PipelineLog logs={searchLogs} isRunning={isSearching} />}

          <div className="tab-bar" role="tablist">
            {TABS.map((t) => (
              <button key={t.key} role="tab" aria-selected={activeTab === t.key}
                className={`tab-btn ${activeTab === t.key ? 'active' : ''}`}
                onClick={() => setActiveTab(t.key)}>
                {t.label}
                {t.key === 'library' && tabBadge && <span className="tab-badge">{tabBadge}</span>}
              </button>
            ))}
          </div>

          <div className="main-column-scroll" ref={scrollRef}>
            {annotateError && (
              <p className="error-inline">{annotateError}
                <button className="btn-text" onClick={() => setAnnotateError(null)}>dismiss</button></p>
            )}
            <ErrorBoundary key={activeTab} area={`the ${TABS.find((t) => t.key === activeTab)?.label || ''} tab`}>
              {activeTab === 'library' && (
                <PaperLibrary
                  papers={displayPapers}
                  scopedPapers={scopedPapers}
                  libraryEmpty={allPapers.length === 0}
                  listKey={listKey}
                  onSelectPaper={(p) => setSelectedId(p.id)}
                  onToggleStar={(p) => handleAnnotate(p.id, { starred: !p.starred })}
                  onKeyword={setTextFilter}
                  activeClusterLabel={activeCluster != null
                    ? clusters?.clusters?.find((c) => c.id === activeCluster)?.label : null}
                  onClearCluster={() => setActiveCluster(null)}
                  categoryFilter={categoryFilter}
                  onCategoryFilter={setViewKey('categoryFilter')}
                  hideFlagged={hideFlagged}
                  onHideFlagged={setViewKey('hideFlagged')}
                  starredOnly={starredOnly}
                  onStarredOnly={setViewKey('starredOnly')}
                  reviewsOnly={reviewsOnly}
                  onReviewsOnly={setViewKey('reviewsOnly')}
                  textFilter={textFilter}
                  onTextFilter={setTextFilter}
                  sortBy={sortBy}
                  onSortBy={setViewKey('sortBy')}
                />
              )}
              {activeTab === 'map' && (
                <MapView clusters={clusters} papersById={papersById} onOpen={openById}
                  activeCluster={activeCluster} onClusterSelect={setActiveCluster} />
              )}
              {activeTab === 'trends' && (
                <TrendsView papers={allPapers} clusters={clusters} onShowCluster={showCluster} onOpen={openById} />
              )}
              {activeTab === 'query' && <SemanticQuery project={project} onOpen={openById} />}
            </ErrorBoundary>
          </div>
        </div>

        <aside className="sidebar">
          <ErrorBoundary area="the sidebar">
            <Sidebar
              project={project}
              papers={allPapers}
              visibleIds={displayPapers.map((p) => p.id)}
              prisma={prisma}
              clusters={clusters}
              activeCluster={activeCluster}
              onClusterSelect={setActiveCluster}
              onClustersGenerated={() => loadProjectData()}
              onReuseSearch={handleReuseSearch}
              onShowStarred={() => { setView((v) => ({ ...v, starredOnly: true, activeTab: 'library' })) }}
              onShowReviews={() => { setView((v) => ({ ...v, reviewsOnly: true, activeTab: 'library' })) }}
              filterSettings={filterSettings}
              defaults={evalConfig ? settingsFromConfig(evalConfig) : null}
              onFilterSettings={setFilterSettings}
            />
          </ErrorBoundary>
        </aside>
      </div>

      {selectedPaper && (
        <ErrorBoundary area="the paper detail">
          <PaperDetail paper={selectedPaper} onClose={() => setSelectedId(null)}
            onSnowball={handleSnowball} busy={isSearching}
            onAnnotate={(fields) => handleAnnotate(selectedPaper.id, fields)}
            onKeyword={(k) => { setSelectedId(null); setTextFilter(k); setActiveTab('library') }} />
        </ErrorBoundary>
      )}

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
