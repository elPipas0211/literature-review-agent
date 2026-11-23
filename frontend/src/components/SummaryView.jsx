import { useMemo, useRef, useState } from 'react'
import { streamSummary } from '../api/client.js'
import { YearBars } from './charts.jsx'

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))

/** Plain-text / Markdown version (to paste into a document or an AI chat for a written synthesis). */
export function summaryToMarkdown(r) {
  const o = r.overview
  const L = []
  L.push(`# Literature summary — ${r.project}`, '')
  if (r.context) L.push(`Research question: ${r.context}`, '')
  L.push(`${o.papers} papers (${o.year_min ?? '?'}–${o.year_max ?? '?'}), ${o.reviews} surveys/reviews, ${o.starred} in the reading list.`, '')
  if (o.top_venues.length) L.push(`Main venues: ${o.top_venues.map((v) => `${v.name} (${v.count})`).join('; ')}.`, '')
  if (o.top_authors.length) L.push(`Most frequent authors: ${o.top_authors.map((a) => `${a.name} (${a.count})`).join('; ')}.`, '')
  L.push('## Most cited', ...o.most_cited.map((p) => `- ${p.title} ${p.cite} — ${p.citations.toLocaleString()} citations`), '')
  L.push('## Topics')
  for (const t of r.topics) {
    L.push('', `### ${t.label} (${t.papers} papers${t.years ? `, ${t.years[0]}–${t.years[1]}` : ''})`)
    if (t.keywords.length) L.push(`Keywords: ${t.keywords.join(', ')}`)
    if (t.key_sentences.length) L.push('What these papers say:', ...t.key_sentences.map((s) => `- “${s.text}” ${s.cite}`))
    if (t.top_papers.length) L.push('Start with:', ...t.top_papers.map((p) => `- ${p.title} ${p.cite}`))
  }
  if (r.surveys.length) L.push('', '## Surveys to read first', ...r.surveys.map((p) => `- ${p.title} ${p.cite}`))
  if (r.reading_list.length) {
    L.push('', '## Reading list', ...r.reading_list.map((p) => `- ${p.title} ${p.cite}${p.note ? ` — Note: ${p.note}` : ''}`))
  }
  L.push('', '## Paper by paper (sentence closest to the research question)',
    ...r.per_paper.map((p) => `- ${p.cite} ${p.title}${p.sentence ? ` — “${p.sentence}”` : ''}`))
  L.push('', `_${r.method}_`)
  return L.join('\n')
}

function summaryToHtml(r) {
  const o = r.overview
  const li = (items) => `<ul>${items.join('')}</ul>`
  const parts = [
    `<h1>Literature summary — ${esc(r.project)}</h1>`,
    r.context ? `<p><b>Research question:</b> ${esc(r.context)}</p>` : '',
    `<p>${o.papers} papers (${o.year_min ?? '?'}–${o.year_max ?? '?'}), ${o.reviews} surveys/reviews, ${o.starred} in the reading list. Generated ${esc(r.generated_at.replace('T', ' '))}.</p>`,
    o.top_venues.length ? `<p><b>Main venues:</b> ${o.top_venues.map((v) => `${esc(v.name)} (${v.count})`).join('; ')}.</p>` : '',
    o.top_authors.length ? `<p><b>Most frequent authors:</b> ${o.top_authors.map((a) => `${esc(a.name)} (${a.count})`).join('; ')}.</p>` : '',
    '<h2>Most cited</h2>', li(o.most_cited.map((p) => `<li>${esc(p.title)} ${esc(p.cite)} — ${p.citations.toLocaleString()} citations</li>`)),
    '<h2>Topics</h2>',
    ...r.topics.map((t) => [
      `<h3>${esc(t.label)} <small>(${t.papers} papers${t.years ? `, ${t.years[0]}–${t.years[1]}` : ''})</small></h3>`,
      t.keywords.length ? `<p><i>Keywords:</i> ${esc(t.keywords.join(', '))}</p>` : '',
      t.key_sentences.length ? `<p><b>What these papers say</b></p>${li(t.key_sentences.map((s) => `<li>“${esc(s.text)}” ${esc(s.cite)}</li>`))}` : '',
      t.top_papers.length ? `<p><b>Start with</b></p>${li(t.top_papers.map((p) => `<li>${esc(p.title)} ${esc(p.cite)}</li>`))}` : '',
    ].join('')),
    r.surveys.length ? `<h2>Surveys to read first</h2>${li(r.surveys.map((p) => `<li>${esc(p.title)} ${esc(p.cite)}</li>`))}` : '',
    r.reading_list.length ? `<h2>Reading list</h2>${li(r.reading_list.map((p) => `<li>${esc(p.title)} ${esc(p.cite)}${p.note ? `<br><i>Note:</i> ${esc(p.note)}` : ''}</li>`))}` : '',
    '<h2>Paper by paper</h2><p><i>Sentence from each abstract closest to the research question.</i></p>',
    li(r.per_paper.map((p) => `<li><b>${esc(p.cite)}</b> ${esc(p.title)}${p.sentence ? `<br>“${esc(p.sentence)}”` : ''}</li>`)),
    `<p><small>${esc(r.method)}</small></p>`,
  ]
  return `<!doctype html><html><head><meta charset="utf-8"><title>Literature summary — ${esc(r.project)}</title>
<style>body{font-family:Georgia,'Times New Roman',serif;max-width:46em;margin:2em auto;padding:0 1em;line-height:1.55;color:#1a1814}
h1,h2,h3{line-height:1.25}h2{margin-top:1.6em;border-bottom:1px solid #ccc;padding-bottom:.2em}li{margin:.35em 0}small{color:#666}</style>
</head><body>${parts.join('\n')}</body></html>`
}

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
}

function Cite({ item, onOpen }) {
  return <a className="link cite-link" onClick={() => onOpen(item.id)} title={item.title}>{item.cite}</a>
}

function Report({ r, onOpen }) {
  const o = r.overview
  return (
    <div className="summary-report">
      <section className="trend-section">
        <div className="trend-stats">
          <div className="stat-card"><span className="stat-card-label">Papers</span><span className="stat-card-number">{o.papers}</span></div>
          <div className="stat-card"><span className="stat-card-label">Years</span>
            <span className="stat-card-number">{o.year_min ?? '—'}–{o.year_max ?? '—'}</span></div>
          <div className="stat-card"><span className="stat-card-label">Surveys / reviews</span><span className="stat-card-number">{o.reviews}</span></div>
        </div>
        {o.per_year.length > 1 && <YearBars data={o.per_year} label="papers" height={150} />}
        <div className="two-col">
          <div>
            <h3>Main venues</h3>
            <ol className="rank-list">{o.top_venues.map((v) => <li key={v.name}><span>{v.name}</span><span className="num">{v.count}</span></li>)}</ol>
          </div>
          <div>
            <h3>Most frequent authors</h3>
            <ol className="rank-list">{o.top_authors.map((a) => <li key={a.name}><span>{a.name}</span><span className="num">{a.count}</span></li>)}</ol>
          </div>
        </div>
        <h3>Most cited</h3>
        <ul className="read-list">
          {o.most_cited.map((p) => (
            <li key={p.id}><a className="link" onClick={() => onOpen(p.id)}>{p.title}</a>
              <span className="hint"> {p.cite} · {p.citations.toLocaleString()} citations</span></li>
          ))}
        </ul>
      </section>

      <section className="trend-section">
        <h3>Topics</h3>
        {r.topics.map((t) => (
          <article key={t.label} className="topic-summary">
            <h4>{t.label}</h4>
            <p className="hint">{t.papers} papers{t.years ? ` · ${t.years[0]}–${t.years[1]}` : ''}</p>
            {t.keywords.length > 0 && <div className="kw-row">{t.keywords.map((k) => <span key={k} className="kw-chip">{k}</span>)}</div>}
            {t.key_sentences.length > 0 && (
              <>
                <div className="detail-section-label">What these papers say</div>
                <ul className="quote-list">
                  {t.key_sentences.map((s) => <li key={s.id}>“{s.text}” <Cite item={s} onOpen={onOpen} /></li>)}
                </ul>
              </>
            )}
            {t.top_papers.length > 0 && (
              <>
                <div className="detail-section-label">Start with</div>
                <ul className="read-list">
                  {t.top_papers.map((p) => <li key={p.id}><a className="link" onClick={() => onOpen(p.id)}>{p.title}</a> <span className="hint">{p.cite}</span></li>)}
                </ul>
              </>
            )}
          </article>
        ))}
      </section>

      {(r.surveys.length > 0 || r.reading_list.length > 0) && (
        <section className="trend-section two-col">
          <div>
            <h3>Surveys to read first</h3>
            {r.surveys.length ? (
              <ul className="read-list">{r.surveys.map((p) => <li key={p.id}><a className="link" onClick={() => onOpen(p.id)}>{p.title}</a> <span className="hint">{p.cite}</span></li>)}</ul>
            ) : <p className="hint">None in this selection.</p>}
          </div>
          <div>
            <h3>Reading list</h3>
            {r.reading_list.length ? (
              <ul className="read-list">{r.reading_list.map((p) => (
                <li key={p.id}><a className="link" onClick={() => onOpen(p.id)}>{p.title}</a> <span className="hint">{p.cite}</span>
                  {p.note && <div className="hint">✎ {p.note}</div>}</li>
              ))}</ul>
            ) : <p className="hint">Star papers to build it.</p>}
          </div>
        </section>
      )}

      <section className="trend-section">
        <details>
          <summary><h3 className="inline-h3">Paper by paper ({r.per_paper.length}{r.per_paper_truncated ? ', highest scores' : ''})</h3></summary>
          <p className="hint">The sentence of each abstract closest to your research question.</p>
          <ul className="quote-list per-paper">
            {r.per_paper.map((p) => (
              <li key={p.id}>
                <strong>{p.starred ? '★ ' : ''}<a className="link" onClick={() => onOpen(p.id)}>{p.title}</a></strong> <span className="hint">{p.cite}</span>
                {p.sentence && <div>“{p.sentence}”</div>}
              </li>
            ))}
          </ul>
        </details>
      </section>
      <p className="hint">{r.method}</p>
    </div>
  )
}

export default function SummaryView({ project, papers, visibleIds, onOpen }) {
  const [scope, setScope] = useState('relevant')
  const [report, setReport] = useState(null)
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)
  const ctrl = useRef(null)

  const scopes = useMemo(() => {
    const rel = papers.filter((p) => ['relevante', 'potencialmente_relevante'].includes(p.evaluation?.category)).map((p) => p.id)
    return [
      { key: 'relevant', label: 'Relevant + potential', ids: rel },
      { key: 'all', label: 'Whole library', ids: null, count: papers.length },
      { key: 'starred', label: '★ Reading list', ids: papers.filter((p) => p.starred).map((p) => p.id) },
      { key: 'starred_relevant', label: '★ Reading list + relevant',
        ids: papers.filter((p) => p.starred || p.evaluation?.category === 'relevante').map((p) => p.id) },
      { key: 'view', label: 'Current view in Papers', ids: visibleIds },
    ]
  }, [papers, visibleIds])
  const current = scopes.find((s) => s.key === scope)
  const count = current.ids ? current.ids.length : current.count
  const running = progress != null

  const generate = async () => {
    ctrl.current?.abort()
    ctrl.current = new AbortController()
    setError(null); setProgress('Starting…')
    try {
      for await (const ev of streamSummary(project, current.ids, ctrl.current.signal)) {
        if (ev.type === 'summary_start') setProgress(`Reading ${ev.sentences.toLocaleString()} sentences from ${ev.papers} abstracts…`)
        if (ev.type === 'summary_progress') setProgress(`Reading abstracts… ${ev.done.toLocaleString()} / ${ev.total.toLocaleString()} sentences`)
        if (ev.type === 'error') setError(ev.message)
        if (ev.type === 'result') setReport(ev.result)
      }
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
    } finally {
      setProgress(null)
    }
  }

  const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  return (
    <div className="trends-view">
      <section className="trend-section">
        <h3>Summary of your papers</h3>
        <p className="hint">
          An overview you can read in a few minutes: what each topic is about, in sentences taken from the abstracts
          (with their APA citation), the most cited papers, venues, authors, surveys and your reading list. It runs on
          this computer and nothing is invented: every sentence is quoted from a paper.
        </p>
        <div className="settings-row summary-controls">
          <select className="input select" value={scope} onChange={(e) => setScope(e.target.value)} disabled={running}>
            {scopes.map((s) => <option key={s.key} value={s.key}>{s.label} ({(s.ids ? s.ids.length : s.count).toLocaleString()})</option>)}
          </select>
          {running
            ? <button className="btn btn-outline btn-sm" onClick={() => ctrl.current?.abort()}>Cancel</button>
            : <button className="btn btn-primary btn-sm" disabled={!count} onClick={generate}>{report ? 'Generate again' : 'Generate summary'}</button>}
          {running && <span className="hint"><span className="spinner" /> {progress}</span>}
        </div>
        {!count && <p className="hint">This selection is empty.</p>}
        {error && <p className="error-inline">{error}</p>}
        {report && !running && (
          <div className="settings-row">
            <button className="btn btn-outline btn-sm" onClick={() => download(`${project}_summary_${stamp}.html`, summaryToHtml(report), 'text/html')}>
              Download (.html, opens in Word)</button>
            <button className="btn btn-outline btn-sm" onClick={async () => {
              await navigator.clipboard.writeText(summaryToMarkdown(report)); setCopied(true); setTimeout(() => setCopied(false), 2000)
            }}>{copied ? 'Copied!' : 'Copy as text'}</button>
            <span className="hint">Tip: paste the text into a chat assistant to get a written synthesis.</span>
          </div>
        )}
      </section>
      {report && <Report r={report} onOpen={onOpen} />}
    </div>
  )
}
