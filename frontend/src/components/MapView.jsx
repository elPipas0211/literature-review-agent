import { useMemo, useState } from 'react'
import { OTHER, SERIES } from './charts.jsx'

export const clusterColor = (rank) => (rank < SERIES.length ? SERIES[rank] : OTHER)

/** 2-D map (t-SNE) of the clustered papers: nearby dots = similar papers. */
export default function MapView({ clusters, papersById, onOpen, activeCluster, onClusterSelect }) {
  const [hover, setHover] = useState(null)       // point index
  const [focus, setFocus] = useState(null)       // cluster id highlighted from the legend
  const points = clusters?.points || []
  const list = clusters?.clusters || []
  const rank = useMemo(() => Object.fromEntries(list.map((c, i) => [c.id, i])), [list])

  const W = 640, H = 460, P = 16
  const px = (x) => P + x * (W - 2 * P)
  const py = (y) => P + (1 - y) * (H - 2 * P)

  const centroids = useMemo(() => list.map((c) => {
    const ps = points.filter((p) => p.cluster === c.id)
    return { id: c.id, x: avg(ps.map((p) => p.x)), y: avg(ps.map((p) => p.y)) }
  }), [list, points])

  if (!points.length) {
    return <p className="hint">Generate clusters in the sidebar to see the map of your library.</p>
  }
  const lit = focus ?? activeCluster
  const hp = hover != null ? points[hover] : null
  const hpPaper = hp && papersById[hp.id]

  return (
    <div className="map-view">
      <p className="hint">
        Each dot is a paper; papers close together talk about similar things. Colors are the clusters.
        Click a dot to open it, or a cluster in the legend to filter the library.
      </p>
      <div className="map-legend">
        {list.map((c, i) => (
          <button key={c.id} className={`legend-item${activeCluster === c.id ? ' active' : ''}`}
            onMouseEnter={() => setFocus(c.id)} onMouseLeave={() => setFocus(null)}
            onClick={() => onClusterSelect(activeCluster === c.id ? null : c.id)}>
            <span className="legend-swatch" style={{ background: clusterColor(i) }} />
            <span className="legend-num">{i + 1}</span>
            {c.label} <span className="pill-count">{c.paper_count}</span>
          </button>
        ))}
      </div>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg map-svg" role="img"
          aria-label="Map of papers by similarity" onMouseLeave={() => setHover(null)}>
          {points.map((p, i) => {
            const dim = lit != null && p.cluster !== lit
            const paper = papersById[p.id]
            return (
              <circle key={p.id} cx={px(p.x)} cy={py(p.y)} r={hover === i ? 6.5 : 4.5}
                fill={clusterColor(rank[p.cluster] ?? 99)}
                opacity={dim ? 0.15 : 0.9}
                stroke={paper?.starred ? 'var(--ink)' : 'var(--cream-light)'}
                strokeWidth={paper?.starred ? 1.6 : 1.2}
                onMouseEnter={() => setHover(i)}
                onClick={() => onOpen(p.id)} style={{ cursor: 'pointer' }} />
            )
          })}
          {centroids.map((c, i) => (
            <text key={c.id} x={px(c.x)} y={py(c.y)} className="map-centroid" textAnchor="middle"
              opacity={lit != null && lit !== c.id ? 0.25 : 1}>{i + 1}</text>
          ))}
        </svg>
        {hp && hpPaper && (
          <div className="chart-tooltip map-tooltip"
            style={{ left: `${(px(hp.x) / W) * 100}%`, top: `${(py(hp.y) / H) * 100}%` }}>
            <strong>{hpPaper.title}</strong>
            <span>{hpPaper.year || '—'} · {hpPaper.citationCount ?? 0} citations{hpPaper.is_review ? ' · review' : ''}</span>
          </div>
        )}
      </div>
      <p className="hint">★ Starred papers have a dark outline. Clusters past the 8th share a grey color — use the numbers.</p>
    </div>
  )
}

const avg = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0)
