import { useEffect, useState } from 'react'
import { createProject, getProjectSummaries } from '../api/client.js'

const STEPS = [
  ['Collect', 'Search OpenAlex, import Scopus / Web of Science exports, follow citations.'],
  ['Explore', 'Rank by your question, see trends, clusters and the map of topics.'],
  ['Read', 'Star papers, write notes, start with the surveys.'],
  ['Export', 'CSV / RIS / BibTeX for Zotero, ASReview or Rayyan, plus PRISMA counts.'],
]

function timeAgo(iso) {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days} days ago`
  return iso.slice(0, 10)
}

export default function WelcomeScreen({ onOpen, onProjectsReload, needsKey, onSettings }) {
  const [summaries, setSummaries] = useState(null)
  const [name, setName] = useState('')
  const [question, setQuestion] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { getProjectSummaries().then(setSummaries).catch(() => setSummaries([])) }, [])

  const create = async (e) => {
    e.preventDefault()
    if (!name.trim()) { setError('Give the project a name.'); return }
    setCreating(true); setError(null)
    try {
      const { name: created } = await createProject(name.trim(), question.trim())
      await onProjectsReload()
      onOpen(created)
    } catch (err) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  const hasProjects = summaries?.length > 0

  return (
    <div className="welcome">
      <section className="welcome-intro">
        <h1>{hasProjects ? 'Welcome back' : 'Start your literature review'}</h1>
        <p>Find papers, rank them against your research question and keep a record you can report.
          Everything stays on this computer.</p>
      </section>

      {needsKey && (
        <div className="welcome-notice">
          <span>Searches without a free OpenAlex API key can be rate-limited when OpenAlex is busy.</span>
          <button className="btn btn-outline btn-sm" onClick={onSettings}>Add API key</button>
        </div>
      )}

      <div className={`welcome-grid${hasProjects ? '' : ' single'}`}>
        <form className="welcome-card new-project" onSubmit={create}>
          <h2>New project</h2>
          <label className="field">
            <span className="field-label">Name</span>
            <input className="input" value={name} maxLength={50} placeholder="tesis-anomalias"
              onChange={(e) => { setName(e.target.value); setError(null) }} />
          </label>
          <label className="field">
            <span className="field-label">Research question <span className="hint">(Spanish or English, optional)</span></span>
            <textarea className="input context-input" rows={3} value={question}
              placeholder="Detección de anomalías en series temporales de sensores industriales con aprendizaje profundo"
              onChange={(e) => setQuestion(e.target.value)} />
          </label>
          <p className="hint">Every paper gets a relevance score against this question. You can change it later.</p>
          {error && <p className="error-inline">{error}</p>}
          <button className="btn btn-primary" disabled={creating}>{creating ? 'Creating…' : 'Create project'}</button>
        </form>

        {hasProjects && (
          <section className="welcome-projects">
            <h2>Your projects</h2>
            <div className="project-cards">
              {summaries.map((s) => (
                <button key={s.name} className="project-card" onClick={() => onOpen(s.name)}>
                  <span className="project-card-name">{s.name}</span>
                  {s.context && <span className="project-card-context">{s.context}</span>}
                  <span className="project-card-stats">
                    {s.papers.toLocaleString()} papers · {s.relevant.toLocaleString()} relevant
                    {s.starred > 0 && ` · ★ ${s.starred}`} · {s.searches} {s.searches === 1 ? 'search' : 'searches'}
                  </span>
                  <span className="project-card-date">Updated {timeAgo(s.updated_at)}</span>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>

      <ol className="welcome-steps">
        {STEPS.map(([title, text], i) => (
          <li key={title}>
            <span className="step-num">{i + 1}</span>
            <span><strong>{title}.</strong> {text}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** Shown in a project with no papers yet: what to do first. */
export function EmptyProject({ hasQuestion, needsKey, onEditQuestion, onFocusSearch, onImport, onSettings }) {
  const items = [
    { done: hasQuestion, title: 'Write your research question',
      text: 'Used to score every paper. Spanish or English.', action: ['Write it', onEditQuestion] },
    { done: !needsKey, title: 'Add a free OpenAlex API key',
      text: 'Optional, but searches without one can fail when OpenAlex is busy.', action: ['Settings', onSettings] },
    { done: false, title: 'Run your first search',
      text: 'English keywords work best, e.g. “anomaly detection time series”. Run several searches; duplicates are merged.',
      action: ['Go to search', onFocusSearch] },
    { done: false, title: 'Or import an export',
      text: 'CSV from Scopus or Zotero, or a Web of Science file.', action: ['Import CSV', onImport] },
  ]
  return (
    <div className="empty-project">
      <h2>Get this project started</h2>
      <ul className="checklist">
        {items.map((it) => (
          <li key={it.title} className={it.done ? 'done' : ''}>
            <span className="check" aria-hidden="true">{it.done ? '✓' : ''}</span>
            <div className="checklist-text">
              <strong>{it.title}</strong>
              <span className="hint">{it.text}</span>
            </div>
            {!it.done && <button className="btn btn-outline btn-sm" onClick={it.action[1]}>{it.action[0]}</button>}
          </li>
        ))}
      </ul>
    </div>
  )
}
