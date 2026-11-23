import { useEffect, useRef } from 'react'

const SOURCE = { openalex: 'OpenAlex', references: 'References', citations: 'Citing papers' }
const src = (s) => SOURCE[s] || s
const FORMAT = { scopus: 'Scopus', wos: 'Web of Science', zotero: 'Zotero', bibtex: 'BibTeX' }

export function describe(event) {
  switch (event.type) {
    case 'stage':       return ['log-line', `▸ ${event.message}`]
    case 'fetch_start': return ['log-line fetch', `  Fetching from ${src(event.source)}…`]
    case 'fetch_progress': return ['log-line fetch', `  ${src(event.source)}: ${event.retrieved} records so far…`]
    case 'cancelled':   return ['log-line warn', '✗ Cancelled. Nothing from this run was added, unless it had already reached “Saving…”.']
    case 'fetch_done':  return ['log-line fetch', `  ${src(event.source)}: ${event.retrieved} records`]
    case 'wait':        return ['log-line warn', `  ${event.message}`]
    case 'parse':       return ['log-line', `  Read ${event.rows} ${event.file_type === 'bibtex' ? 'BibTeX entries' : 'rows'} (${FORMAT[event.format] || event.format}), ${event.records} records with a title`]
    case 'dedup':       return ['log-line', `  ${event.identified} identified → ${event.within} duplicates merged, ${event.already} already in library → ${event.new} new`]
    case 'context':     return ['log-line warn', `  Research context updated — rescoring all ${event.rescoring} papers`]
    case 'embed':       return ['log-line', `  Embedding ${event.count} new papers…`]
    case 'keywords':    return ['log-line', `  Extracting keywords for ${event.count} papers…`]
    case 'eval_done':   return ['log-line success', `  New papers: ${event.relevante || 0} relevant, ${event.potencialmente_relevante || 0} potential, ${event.no_relevante || 0} low`]
    case 'done':        return ['log-line success', `✓ Done — ${event.added} added, ${event.already} already present, library now ${event.total}`]
    case 'error':       return ['log-line error', `✗ Error${event.source ? ` (${src(event.source)})` : ''}: ${event.message}`]
    case 'result':      return null
    default:            return ['log-line', JSON.stringify(event)]
  }
}

export default function PipelineLog({ logs, isRunning, onCancel }) {
  const bottomRef = useRef(null)
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [logs])

  return (
    <div className="pipeline-log">
      <div className="pipeline-log-header">
        {isRunning && <span className="spinner" />}
        Pipeline
        {isRunning && onCancel && (
          <button className="btn btn-outline btn-sm log-cancel" onClick={onCancel}>Cancel</button>
        )}
      </div>
      <div className="pipeline-log-body">
        {logs.map((event, i) => {
          const d = describe(event)
          return d && <span key={i} className={d[0]}>{d[1]}</span>
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
