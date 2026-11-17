import { useState } from 'react'

// Categorical slots in fixed order (validated palette, light surface). Never cycled:
// clusters beyond 8 are folded into "Other" by the caller.
// Values live in index.css (--series-N) so light and dark mode each get their validated step.
export const SERIES = Array.from({ length: 8 }, (_, i) => `var(--series-${i + 1})`)
export const OTHER = 'var(--series-other)'

/**
 * Vertical bar chart of counts per year (single series → no legend).
 * Bars: 4px rounded top anchored to the baseline, 2px surface gap.
 * `partialYear` is drawn lighter and labelled, so an unfinished year
 * isn't read as a drop.
 */
export function YearBars({ data, height = 180, partialYear, color = SERIES[0], label = 'works' }) {
  const [hover, setHover] = useState(null)
  if (!data?.length) return <p className="hint">No data.</p>
  const W = 640
  const pad = { l: 44, r: 8, t: 10, b: 22 }
  const max = Math.max(...data.map((d) => d.count), 1)
  const innerW = W - pad.l - pad.r
  const innerH = height - pad.t - pad.b
  const slot = innerW / data.length
  const bw = Math.max(2, slot - 2)
  const y = (v) => pad.t + innerH - (v / max) * innerH
  const ticks = niceTicks(max)
  const every = Math.ceil(data.length / 10)

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${height}`} className="chart-svg" role="img"
        aria-label={`${label} per year`} onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className="chart-grid" />
            <text x={pad.l - 6} y={y(t) + 3} className="chart-axis" textAnchor="end">{fmt(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = pad.l + i * slot + 1
          const h = Math.max(0, (d.count / max) * innerH)
          const partial = d.year === partialYear
          return (
            <g key={d.year}>
              <path d={roundedTop(x, pad.t + innerH - h, bw, h, Math.min(4, bw / 2))}
                fill={color} opacity={partial ? 0.35 : hover === i ? 1 : 0.88} />
              {(i % every === 0 || i === data.length - 1) && (
                <text x={x + bw / 2} y={height - 6} className="chart-axis" textAnchor="middle">{d.year}</text>
              )}
              {/* hit target larger than the mark */}
              <rect x={pad.l + i * slot} y={pad.t} width={slot} height={innerH} fill="transparent"
                onMouseEnter={() => setHover(i)} />
            </g>
          )
        })}
        <line x1={pad.l} x2={W - pad.r} y1={pad.t + innerH} y2={pad.t + innerH} className="chart-baseline" />
      </svg>
      {hover != null && (
        <div className="chart-tooltip" style={{ left: `${((pad.l + hover * slot + slot / 2) / W) * 100}%` }}>
          <strong>{data[hover].year}</strong> · {data[hover].count.toLocaleString()} {label}
          {data[hover].year === partialYear && <em> (year in progress)</em>}
        </div>
      )}
    </div>
  )
}

/** Tiny per-year bars for table rows (sparkline). */
export function Spark({ counts, years, color = SERIES[0] }) {
  const max = Math.max(1, ...years.map((y) => counts[y] || 0))
  const w = 4, gap = 1, h = 22
  return (
    <svg width={years.length * (w + gap)} height={h} className="spark" aria-hidden="true">
      {years.map((yr, i) => {
        const bh = ((counts[yr] || 0) / max) * (h - 2)
        return <rect key={yr} x={i * (w + gap)} y={h - bh} width={w} height={bh} rx={1} fill={color}>
          <title>{yr}: {counts[yr] || 0}</title>
        </rect>
      })}
    </svg>
  )
}

function roundedTop(x, y, w, h, r) {
  if (h <= 0) return ''
  r = Math.min(r, h)
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`
}

function niceTicks(max) {
  const step = Math.pow(10, Math.floor(Math.log10(max)))
  const m = max / step
  const s = (m > 5 ? 2 : m > 2 ? 1 : 0.5) * step
  const out = []
  for (let v = 0; v <= max; v += s) out.push(Math.round(v))
  return out
}

export const fmt = (n) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : `${n}`)
