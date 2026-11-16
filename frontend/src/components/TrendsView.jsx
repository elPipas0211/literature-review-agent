import { useEffect, useMemo, useRef, useState } from 'react'
import { getTrend } from '../api/client.js'
import { Spark, YearBars } from './charts.jsx'
import { clusterColor } from './MapView.jsx'

const NOW = new Date().getFullYear()
const SPARK_YEARS = Array.from({ length: 12 }, (_, i) => NOW - 11 + i)

/**
 * Keyphrases that appear much more in the last 3 years than before, among `papers`.
 * Uses the per-paper KeyBERT keywords computed locally (no paid API).
 */
export function emergingKeywords(papers, n = 5) {
  const recent = {}, older = {}
  for (const p of papers) {
    if (!p.year) continue
    const bucket = p.year >= NOW - 2 ? recent : older
    for (const k of p.keywords || []) bucket[k] = (bucket[k] || 0) + 1
  }
  return Object.keys(recent)
    .filter((k) => recent[k] >= 2)
    .map((k) => ({ k, r: recent[k], o: older[k] || 0, s: ((recent[k] + 0.5) / ((older[k] || 0) + 0.5)) * Math.log1p(recent[k]) }))
    .sort((a, b) => b.s - a.s)
    .slice(0, n)
}

function yearCounts(papers) {
  const c = {}
  for (const p of papers) if (p.year) c[p.year] = (c[p.year] || 0) + 1
  return c
}

function GlobalTrend({ query, setQuery }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [input, setInput] = useState(query)
  const ref = useRef(null)

  useEffect(() => {
    setInput(query)
    if (query) { run(query); ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  }, [query])

  async function run(q) {
    if (!q.trim()) return
    setLoading(true); setError(null)
    try { setData(await getTrend(q.trim(), 2000)) } catch (e) { setError(e.message) } finally { setLoading(false) }
  }

  const growth = data?.growth
  return (
    <section className="trend-section" ref={ref}>
      <h3>How much is published on a topic? <span className="hint">(all of OpenAlex)</span></h3>
      <form className="query-input-row" onSubmit={(e) => { e.preventDefault(); setQuery(input) }}>
        <input className="input input-grow" value={input} onChange={(e) => setInput(e.target.value)}
          placeholder='Topic in English — use "quotes" for an exact phrase, e.g. "digital twin" predictive maintenance' />
        <button className="btn btn-primary" disabled={loading || !input.trim()}>{loading ? '…' : 'Check'}</button>
      </form>
      {error && <p className="hint" style={{ color: 'var(--error)' }}>{error}</p>}
      {data && (
        <>
          <div className="trend-stats">
            <div className="stat-card"><span className="stat-card-label">Works since 2000</span>
              <span className="stat-card-number">{data.total.toLocaleString()}</span></div>
            <div className="stat-card"><span className="stat-card-label">Last 3 full years</span>
              <span className="stat-card-number">{data.recent_3y.toLocaleString()}</span></div>
            <div className="stat-card"><span className="stat-card-label">Growth vs previous 3</span>
              <span className="stat-card-number">{growth == null ? '—' : `${growth >= 0 ? '+' : ''}${Math.round(growth * 100)}%`}</span></div>
          </div>
          <YearBars data={data.counts} partialYear={data.partial_year} label="works" />
          <p className="hint">
            Title/abstract matches. {data.partial_year} is still in progress (lighter bar). Absolute numbers grow
            for almost every topic because science grows — compare topics with each other, not with zero.
          </p>
          <details>
            <summary className="hint">Show data table</summary>
            <table className="prisma-table">
              <tbody>{data.counts.map((r) => <tr key={r.year}><td>{r.year}</td><td>{r.count.toLocaleString()}</td></tr>)}</tbody>
            </table>
          </details>
        </>
      )}
    </section>
  )
}

export default function TrendsView({ papers, clusters, onShowCluster, onOpen }) {
  const [query, setQuery] = useState('')
  const list = clusters?.clusters || []
  const byId = useMemo(() => Object.fromEntries(papers.map((p) => [p.id, p])), [papers])

  const rows = useMemo(() => list.map((c, i) => {
    const ps = (c.paper_ids || []).map((id) => byId[id]).filter(Boolean)
    const recent = ps.filter((p) => p.year >= NOW - 2).length
    return {
      c, rank: i, ps,
      counts: yearCounts(ps),
      recentShare: ps.length ? recent / ps.length : 0,
      reviews: ps.filter((p) => p.is_review).sort((a, b) => (b.citationCount || 0) - (a.citationCount || 0)),
      emerging: emergingKeywords(ps, 4),
    }
  }), [list, byId])

  const libraryYears = useMemo(() => {
    const c = yearCounts(papers)
    const years = Object.keys(c).map(Number).filter((y) => y >= 1990)
    if (!years.length) return []
    const out = []
    for (let y = Math.min(...years); y <= Math.max(...years); y++) out.push({ year: y, count: c[y] || 0 })
    return out
  }, [papers])

  const libEmerging = useMemo(() => emergingKeywords(papers, 8), [papers])
  const reviews = useMemo(() => papers.filter((p) => p.is_review)
    .sort((a, b) => (b.evaluation?.score ?? 0) - (a.evaluation?.score ?? 0)).slice(0, 6), [papers])

  return (
    <div className="trends-view">
      <GlobalTrend query={query} setQuery={setQuery} />

      <section className="trend-section">
        <h3>Your library per year <span className="hint">({papers.length} papers)</span></h3>
        {libraryYears.length ? (
          <YearBars data={libraryYears} partialYear={NOW} label="papers" color="#6250d6" />
        ) : <p className="hint">No papers yet.</p>}
        <p className="hint">Reflects what you searched and imported, not the field as a whole.</p>
      </section>

      <section className="trend-section">
        <h3>Topics in your library</h3>
        {rows.length === 0 ? (
          <p className="hint">Generate clusters in the sidebar to compare the topics inside your library.</p>
        ) : (
          <table className="topic-table">
            <thead>
              <tr><th>Topic</th><th>Papers</th><th title="Papers per year in your library, last 12 years">Per year</th>
                <th title="Share of the cluster published in the last 3 years">Recent</th><th>Emerging keywords</th><th /></tr>
            </thead>
            <tbody>
              {rows.map(({ c, rank, ps, counts, recentShare, reviews: rv, emerging }) => (
                <tr key={c.id}>
                  <td>
                    <span className="legend-swatch" style={{ background: clusterColor(rank) }} />
                    <span className="legend-num">{rank + 1}</span>{c.label}
                    {rv.length > 0 && (
                      <div className="hint">Read first: {rv.slice(0, 2).map((p) => (
                        <a key={p.id} className="link" onClick={() => onOpen(p.id)}>{trim(p.title, 60)}</a>
                      )).reduce((a, b) => [a, ' · ', b])}</div>
                    )}
                  </td>
                  <td className="num">{ps.length}</td>
                  <td><Spark counts={counts} years={SPARK_YEARS} color={clusterColor(rank)} /></td>
                  <td className="num">{Math.round(recentShare * 100)}%</td>
                  <td>{emerging.length ? emerging.map((e) => <span key={e.k} className="kw-chip" title={`${e.r} recent / ${e.o} before`}>{e.k}</span>) : <span className="hint">—</span>}</td>
                  <td className="actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => setQuery(`"${c.keyphrases?.[0] || c.label}"`)}>Global trend</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => onShowCluster(c.id)}>Papers</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">
          “Recent” and the per-year bars describe <em>your library</em>, which depends on what you searched.
          Use “Global trend” to check the topic across all of OpenAlex.
        </p>
      </section>

      <section className="trend-section two-col">
        <div>
          <h3>Emerging keywords (whole library)</h3>
          {libEmerging.length ? libEmerging.map((e) => (
            <button key={e.k} className="kw-chip clickable" title="Check global trend"
              onClick={() => setQuery(`"${e.k}"`)}>{e.k} <span className="pill-count">{e.r}↑ {e.o}</span></button>
          )) : <p className="hint">Not enough recent papers yet.</p>}
          <p className="hint">Keyphrases far more frequent in papers from {NOW - 2}–{NOW} than before. Click one to see its global trend.</p>
        </div>
        <div>
          <h3>Surveys & reviews to read first</h3>
          {reviews.length ? (
            <ul className="read-list">
              {reviews.map((p) => (
                <li key={p.id}><a className="link" onClick={() => onOpen(p.id)}>{p.title}</a>
                  <span className="hint"> {p.year} · {p.citationCount ?? 0} cit.</span></li>
              ))}
            </ul>
          ) : <p className="hint">No surveys detected yet — try searching “survey” or “review” plus your topic.</p>}
          <p className="hint">Their “future work / open challenges” sections are a good source of thesis topics.</p>
        </div>
      </section>
    </div>
  )
}

const trim = (s, n) => (s && s.length > n ? `${s.slice(0, n - 1)}…` : s)
