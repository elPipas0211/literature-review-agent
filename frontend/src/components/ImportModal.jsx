import { useRef, useState } from 'react'
import { streamImport } from '../api/client.js'
import { describe } from './PipelineLog.jsx'

export default function ImportModal({ project, projectContext, onClose, onDone }) {
  const [file, setFile] = useState(null)
  const [context, setContext] = useState(projectContext)
  const [log, setLog] = useState([])
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [failed, setFailed] = useState(false)
  const fileRef = useRef(null)
  const ctrl = useRef(null)

  const pick = (f) => { if (f) { setFile(f); setResult(null); setLog([]); setFailed(false) } }
  const canImport = file && !running

  const handleImport = async () => {
    if (!canImport) return
    setRunning(true); setLog([]); setResult(null); setFailed(false)
    ctrl.current = new AbortController()
    try {
      for await (const ev of streamImport(project, file, context.trim(), ctrl.current.signal)) {
        const d = describe(ev)
        if (d) setLog((l) => [...l, d])
        if (ev.type === 'error') setFailed(true)
        if (ev.type === 'result') { setResult(ev.result); onDone() }
      }
    } catch (err) {
      if (err.name !== 'AbortError') { setLog((l) => [...l, ['log-line error', `✗ ${err.message}`]]); setFailed(true) }
    } finally {
      setRunning(false)
    }
  }

  const handleClose = () => { ctrl.current?.abort(); onClose() }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && !running && handleClose()}>
      <div className="modal">
        <div className="modal-header">
          <h2>Import a file</h2>
          <button className="modal-close" onClick={handleClose}>×</button>
        </div>

        <div className={`file-drop ${file ? 'has-file' : ''}`}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files?.[0]) }}
          onClick={() => fileRef.current?.click()}>
          {file ? `📄 ${file.name}` : 'Drop an export here, or click to browse'}
          <input ref={fileRef} type="file" accept=".csv,.txt,.tsv,.bib,.bibtex" onChange={(e) => pick(e.target.files?.[0])} />
        </div>
        <p className="hint">
          Accepted: Scopus CSV or BibTeX · Web of Science BibTeX, tab-delimited or Excel-saved CSV · Zotero CSV or
          BibTeX · any other BibTeX file. Abstracts and citation counts are kept when the export includes them
          (in Web of Science choose “Full Record”).
        </p>

        <div>
          <textarea className="input context-input" rows={2} style={{ width: '100%' }}
            placeholder="Research context (optional — the project's context is used if empty)"
            value={context} onChange={(e) => setContext(e.target.value)} disabled={running} />
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleImport} disabled={!canImport} style={{ flex: 1 }}>
            {running ? 'Importing…' : 'Import'}
          </button>
          <button className="btn btn-outline" onClick={handleClose} disabled={running}>
            {result ? 'Close' : 'Cancel'}
          </button>
        </div>

        {log.length > 0 && (
          <div className="import-log">
            {log.map(([cls, text], i) => <span key={i} className={cls}>{text}</span>)}
          </div>
        )}

        {result && !failed && (
          <div className="import-result">
            ✓ {result.added} new papers added to <strong>{project}</strong>
            {result.already_in_library > 0 && ` (${result.already_in_library} were already there)`}
          </div>
        )}
      </div>
    </div>
  )
}
