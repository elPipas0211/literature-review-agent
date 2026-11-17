import { useEffect, useMemo, useState } from 'react'
import { drawValidationSample } from '../api/client.js'
import { atThreshold, auc, labeledPoints, pct, thresholdForRecall, wilson } from '../validation.js'
import { SERIES } from './charts.jsx'

const REL = SERIES[0]
const IRR = SERIES[1]

/* ── Labeling: one paper at a time, blind to the score ─────────────────────── */
function Labeler({ queue, total, done, onLabel, onUndo, canUndo }) {
  const paper = queue[0]

  useEffect(() => {
    const onKey = (e) => {
      if (!paper || e.ctrlKey || e.metaKey || e.altKey) return
      if (e.target?.closest?.('input, textarea, select, .detail-overlay, .modal-overlay')) return
      const k = e.key.toLowerCase()
      if (k === 'r') onLabel(paper.id, 'relevant')
      if (k === 'n') onLabel(paper.id, 'irrelevant')
      if (k === 'u') onLabel(paper.id, 'unsure')
      if (k === 'z' && canUndo) onUndo()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (!paper) return null
  return (
    <section className="labeler">
      <div className="labeler-progress">
        <span>Paper {done + 1} of {total}</span>
        <div className="progress-bar"><div style={{ width: `${(done / total) * 100}%` }} /></div>
      </div>
      <article className="labeler-card">
        <p className="paper-year">{paper.year || '—'}{paper.venue ? ` · ${paper.venue}` : ''}</p>
        <h2 className="detail-title">{paper.title}</h2>
        {paper.abstract
          ? <p className="detail-abstract">{paper.abstract}</p>
          : <p className="hint">No abstract — decide from the title, or mark it unsure.</p>}
      </article>
      <div className="labeler-actions">
        <button className="btn btn-primary" onClick={() => onLabel(paper.id, 'relevant')}>Relevant <kbd>R</kbd></button>
        <button className="btn btn-outline" onClick={() => onLabel(paper.id, 'irrelevant')}>Not relevant <kbd>N</kbd></button>
        <button className="btn btn-ghost" onClick={() => onLabel(paper.id, 'unsure')}>Unsure <kbd>U</kbd></button>
        {canUndo && <button className="btn-text" onClick={onUndo}>Undo <kbd>Z</kbd></button>}
      </div>
      <p className="hint">Judge it as you would in title–abstract screening: would you read the full text?
        The score is hidden on purpose so it can't influence you.</p>
    </section>
  )
}

/* ── Strip plot: score of each labeled paper, one row per label ────────────── */
function ScoreStrip({ points, thresholds }) {
  const [hover, setHover] = useState(null)
  const W = 640, H = 128, L = 92, R = 12, rowY = { true: 34, false: 82 }
  const x = (s) => L + Math.min(1, Math.max(0, s)) * (W - L - R)
  // Deterministic jitter so dots don't sit exactly on top of each other.
  const jitter = (id) => ((parseInt(id.slice(-4), 16) || 0) % 17) - 8

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img"
        aria-label="Relevance score of each labeled paper, relevant versus not relevant"
        onMouseLeave={() => setHover(null)}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={14} y2={H - 22} className="chart-grid" />
            <text x={x(t)} y={H - 6} className="chart-axis" textAnchor="middle">{t.toFixed(2)}</text>
          </g>
        ))}
        {thresholds.map(({ value, label }) => (
          <g key={label}>
            <line x1={x(value)} x2={x(value)} y1={10} y2={H - 22} stroke="var(--ink-muted)" strokeDasharray="3 3" />
            <text x={x(value) + 4} y={12} className="chart-axis">{label}</text>
          </g>
        ))}
        <text x={L - 10} y={rowY.true + 4} className="chart-label" textAnchor="end">Relevant</text>
        <text x={L - 10} y={rowY.false + 4} className="chart-label" textAnchor="end">Not relevant</text>
        {points.map((p, i) => (
          <circle key={p.id} cx={x(p.score)} cy={rowY[p.relevant] + jitter(p.id)} r={hover === i ? 6.5 : 5}
            fill={p.relevant ? REL : IRR} stroke="var(--cream-light)" strokeWidth={1.5}
            onMouseEnter={() => setHover(i)} />
        ))}
      </svg>
      {hover != null && points[hover] && (
        <div className="chart-tooltip map-tooltip"
          style={{ left: `${(x(points[hover].score) / W) * 100}%`,
                   top: `${((rowY[points[hover].relevant] - 6) / H) * 100}%` }}>
          <strong>{points[hover].title}</strong>
          <span>score {points[hover].score.toFixed(2)} · labeled {points[hover].relevant ? 'relevant' : 'not relevant'}</span>
        </div>
      )}
    </div>
  )
}

function Metrics({ points, papers, settings, sampleSize, unsure }) {
  const rel = points.filter((p) => p.relevant).length
  const a = auc(points)
  const cuts = [
    { key: 'rel', label: `Relevant (≥ ${settings.thresholdRelevant.toFixed(2)})`, value: settings.thresholdRelevant },
    { key: 'pot', label: `Relevant + potential (≥ ${settings.thresholdPotential.toFixed(2)})`, value: settings.thresholdPotential },
  ]
  const t95 = thresholdForRecall(points, 0.95)
  const libKept = (t) => papers.filter((p) => (p.evaluation?.score ?? -1) >= t).length
  const [copied, setCopied] = useState(false)

  if (points.length < 10 || !rel || rel === points.length) {
    return (
      <p className="hint">
        Results appear once at least 10 papers are labeled and the sample has both relevant and
        not-relevant papers ({points.length} labeled so far, {rel} relevant).
        {rel === 0 && points.length >= 10 && ' No relevant papers yet: draw a larger sample.'}
      </p>
    )
  }

  const potCut = atThreshold(points, settings.thresholdPotential)
  const ci = wilson(potCut.tp, potCut.tp + potCut.fn)
  const methods =
    `To check the relevance ranking, a simple random sample of ${sampleSize} records was screened on title ` +
    `and abstract without seeing the score; ${points.length} were judged (${rel} relevant` +
    `${unsure ? `, ${unsure} unsure and excluded` : ''}). The score separated relevant from non-relevant ` +
    `records with an AUC of ${a.toFixed(2)}. Keeping records with a score of at least ` +
    `${settings.thresholdPotential.toFixed(2)} retained ${potCut.tp} of ${potCut.tp + potCut.fn} relevant records ` +
    `in the sample (recall ${pct(potCut.recall)}, 95% CI ${pct(ci[0])}–${pct(ci[1])}).`

  return (
    <>
      <div className="trend-stats">
        <div className="stat-card"><span className="stat-card-label">Labeled</span>
          <span className="stat-card-number">{points.length}</span></div>
        <div className="stat-card"><span className="stat-card-label">Judged relevant</span>
          <span className="stat-card-number">{rel} <small>({pct(rel / points.length)})</small></span></div>
        <div className="stat-card" title="Chance that a relevant paper scores higher than a non-relevant one. 0.5 = random, 1 = perfect.">
          <span className="stat-card-label">AUC</span>
          <span className="stat-card-number">{a.toFixed(2)}</span></div>
      </div>
      <p className="hint">AUC: 0.5 is no better than chance, above 0.8 is good, above 0.9 excellent.</p>

      <ScoreStrip points={points} thresholds={[
        { value: settings.thresholdPotential, label: 'potential' },
        { value: settings.thresholdRelevant, label: 'relevant' },
      ]} />

      <table className="topic-table">
        <thead><tr><th>If you only screen…</th><th>Papers in library</th><th>Recall (sample)</th><th>Precision (sample)</th><th>Relevant missed</th></tr></thead>
        <tbody>
          {cuts.map(({ key, label, value }) => {
            const m = atThreshold(points, value)
            const c = wilson(m.tp, m.tp + m.fn)
            return (
              <tr key={key}>
                <td>{label}</td>
                <td className="num">{libKept(value).toLocaleString()} of {papers.length.toLocaleString()}</td>
                <td className="num" title={c ? `95% CI ${pct(c[0])}–${pct(c[1])}` : ''}>{pct(m.recall)}</td>
                <td className="num">{pct(m.precision)}</td>
                <td className="num">{m.fn} of {m.tp + m.fn}</td>
              </tr>
            )
          })}
          {t95 != null && (
            <tr>
              <td>Score ≥ {t95.toFixed(2)} <span className="hint">(keeps ≥ 95% of relevant in sample)</span></td>
              <td className="num">{libKept(t95).toLocaleString()} of {papers.length.toLocaleString()}</td>
              <td className="num">{pct(atThreshold(points, t95).recall)}</td>
              <td className="num">{pct(atThreshold(points, t95).precision)}</td>
              <td className="num">{atThreshold(points, t95).fn} of {rel}</td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="hint">
        Recall = share of the relevant papers you would still screen. With small samples the uncertainty is large
        (hover a recall value for its 95% interval); label more papers to narrow it. Move the threshold sliders in the
        sidebar and these numbers update.
      </p>

      <div>
        <div className="detail-section-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>For your methods section</span>
          <button className="btn btn-outline btn-sm" onClick={async () => {
            await navigator.clipboard.writeText(methods); setCopied(true); setTimeout(() => setCopied(false), 2000)
          }}>{copied ? 'Copied!' : 'Copy'}</button>
        </div>
        <p className="methods-text">{methods}</p>
      </div>
    </>
  )
}

export default function ValidationView({ project, papers, meta, settings, onAnnotate, onReload }) {
  const [size, setSize] = useState(50)
  const [drawing, setDrawing] = useState(false)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])   // ids labeled in this visit, for Undo
  const sampleIds = meta?.validation_sample || []
  const byId = useMemo(() => Object.fromEntries(papers.map((p) => [p.id, p])), [papers])
  const sample = sampleIds.map((id) => byId[id]).filter(Boolean)
  const queue = sample.filter((p) => !p.validation)
  const unsure = sample.filter((p) => p.validation === 'unsure').length
  const points = useMemo(() => labeledPoints(papers, sampleIds), [papers, sampleIds])

  const draw = async (n) => {
    setDrawing(true); setError(null)
    try { await drawValidationSample(project, n); await onReload() } catch (e) { setError(e.message) } finally { setDrawing(false) }
  }
  const label = (id, value) => { setHistory((h) => [...h, id]); onAnnotate(id, { validation: value }) }
  const undo = () => {
    const id = history.at(-1)
    if (!id) return
    setHistory((h) => h.slice(0, -1))
    onAnnotate(id, { validation: '' })
  }

  return (
    <div className="trends-view">
      <section className="trend-section">
        <h3>How good is the ranking?</h3>
        <p className="hint">
          Label a random sample of papers as relevant or not, the way you would screen them. The app then measures how
          well the score separates the two groups and how many relevant papers each threshold would miss. Use it to
          choose a cut-off and to justify it in your thesis.
        </p>
        {sampleIds.length === 0 ? (
          <div className="settings-row">
            <span className="search-meta-label">Sample size</span>
            <input type="number" className="input-number" min={10} max={500} value={size}
              onChange={(e) => setSize(Math.min(500, Math.max(10, Number(e.target.value) || 50)))} />
            <button className="btn btn-primary btn-sm" disabled={drawing || papers.length < 10} onClick={() => draw(size)}>
              {drawing ? 'Drawing…' : 'Draw random sample'}
            </button>
            {papers.length < 10 && <span className="hint">Needs at least 10 papers.</span>}
          </div>
        ) : (
          <p className="hint">
            Sample: {sampleIds.length} papers · {sampleIds.length - queue.length} labeled{unsure ? ` (${unsure} unsure)` : ''}.{' '}
            <button className="btn-text" disabled={drawing} onClick={() => draw(25)}>
              {drawing ? 'adding…' : 'Add 25 more'}
            </button>
          </p>
        )}
        {error && <p className="error-inline">{error}</p>}
      </section>

      {queue.length > 0 && (
        <Labeler queue={queue} total={sample.length} done={sample.length - queue.length}
          onLabel={label} onUndo={undo} canUndo={history.length > 0} />
      )}

      {sampleIds.length > 0 && (
        <section className="trend-section">
          <h3>Results</h3>
          <Metrics points={points} papers={papers} settings={settings} sampleSize={sampleIds.length} unsure={unsure} />
        </section>
      )}

      {sample.length - queue.length > 0 && (
        <details className="trend-section">
          <summary className="hint">Review or change labels ({sample.length - queue.length})</summary>
          <table className="topic-table">
            <tbody>
              {sample.filter((p) => p.validation).map((p) => (
                <tr key={p.id}>
                  <td>{p.title}</td>
                  <td className="num">{(p.evaluation?.score ?? 0).toFixed(2)}</td>
                  <td>
                    <select className="input select" value={p.validation}
                      onChange={(e) => onAnnotate(p.id, { validation: e.target.value })}>
                      <option value="relevant">Relevant</option>
                      <option value="irrelevant">Not relevant</option>
                      <option value="unsure">Unsure</option>
                      <option value="">Unlabeled</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  )
}
