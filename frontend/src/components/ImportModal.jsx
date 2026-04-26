import { useRef, useState } from 'react'
import { streamImport } from '../api/client.js'

function logLine(event) {
  switch (event.type) {
    case 'parse':   return `Parsed ${event.rows} rows — format: ${event.format?.toUpperCase()}`
    case 'dedup':   return `Dedup — intra: ${(event.doi_intra||0)+(event.title_intra||0)}, master: ${(event.doi_master||0)+(event.title_master||0)} → ${event.remaining} new`
    case 'filter':  return `Mechanical filter: ${event.passed} passed, ${event.rejected} rejected`
    case 'floor':   return `Citation floor: ${event.discarded} discarded, ${event.remaining} proceed`
    case 'eval_start': return `Evaluating ${event.count} papers…`
    case 'eval_done': return `Evaluation: ${event.relevante||0} relevant, ${event.potencialmente_relevante||0} potential`
    case 'insert':  return `Inserted ${event.added} new papers`
    case 'done':    return `✓ Done — ${event.inserted} papers added`
    case 'error':   return `✗ ${event.message}`
    case 'result':  return null
    default:        return JSON.stringify(event)
  }
}

export default function ImportModal({ project, onClose, onDone }) {
  const [file, setFile] = useState(null)
  const [context, setContext] = useState('')
  const [log, setLog] = useState([])
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const fileRef = useRef(null)
  const ctrl = useRef(null)

  const handleFile = (e) => {
    const f = e.target.files?.[0]
    if (f) setFile(f)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    if (f) setFile(f)
  }

  const canImport = file && context.trim().length > 0 && !running

  const handleImport = async () => {
    if (!canImport) return
    setRunning(true)
    setLog([])
    setResult(null)
    ctrl.current = new AbortController()
    try {
      for await (const ev of streamImport(project, file, context.trim(), ctrl.current.signal)) {
        const line = logLine(ev)
        if (line) setLog((l) => [...l, line])
        if (ev.type === 'result') {
          setResult(ev)
          onDone()
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError')
        setLog((l) => [...l, `Error: ${err.message}`])
    } finally {
      setRunning(false)
    }
  }

  const handleClose = () => {
    ctrl.current?.abort()
    onClose()
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && handleClose()}>
      <div className="modal">
        <div className="modal-header">
          <h2>Import CSV</h2>
          <button className="modal-close" onClick={handleClose}>×</button>
        </div>

        <div
          className={`file-drop ${file ? 'has-file' : ''}`}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          {file ? `📄 ${file.name}` : 'Drop a Scopus or WoS CSV here, or click to browse'}
          <input ref={fileRef} type="file" accept=".csv,.txt,.tsv" onChange={handleFile} />
        </div>

        <div>
          <input
            className="input"
            style={{ width: '100%' }}
            placeholder="Research context for semantic evaluation — required"
            value={context}
            onChange={(e) => setContext(e.target.value)}
            disabled={running}
          />
          <p style={{ fontSize: 11, color: 'var(--ink-faint)', marginTop: 4 }}>
            Papers are classified by semantic similarity to this context. Required for categorization.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn btn-primary"
            onClick={handleImport}
            disabled={!canImport}
            title={!file ? 'Select a CSV file first' : !context.trim() ? 'Enter a research context' : ''}
            style={{ flex: 1 }}
          >
            {running ? 'Importing…' : 'Import'}
          </button>
          <button className="btn btn-outline" onClick={handleClose} disabled={running}>
            Cancel
          </button>
        </div>

        {log.length > 0 && (
          <div className="import-log">
            {log.map((l, i) => (
              <span key={i} style={{ color: l.startsWith('✗') ? 'var(--error)' : l.startsWith('✓') ? 'var(--relevant)' : 'inherit' }}>
                {l}
              </span>
            ))}
          </div>
        )}

        {result && (
          <div className="import-result">
            ✓ {result.inserted ?? 0} new papers added to <strong>{project}</strong>
          </div>
        )}
      </div>
    </div>
  )
}
