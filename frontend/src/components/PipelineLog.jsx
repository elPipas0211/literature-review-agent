import { useEffect, useRef } from 'react'

const SOURCE = { semantic_scholar: 'Semantic Scholar', openalex: 'OpenAlex' }
const src = (s) => SOURCE[s] || s

export function describe(event) {
  switch (event.type) {
    case 'stage':       return ['log-line', `▸ ${event.message}`]
    case 'fetch_start': return ['log-line fetch', `  Fetching from ${src(event.source)}…`]
    case 'fetch_done':  return ['log-line fetch', `  ${src(event.source)}: ${event.retrieved} records`]
    case 'wait':        return ['log-line warn', `  ${event.message}`]
    case 'parse':       return ['log-line', `  Parsed ${event.rows} rows (${event.format?.toUpperCase()}), ${event.records} records with title`]
    case 'dedup':       return ['log-line', `  ${event.identified} identified → ${event.within} duplicates merged, ${event.already} already in library → ${event.new} new`]
    case 'context':     return ['log-line warn', `  Research context updated — rescoring all ${event.rescoring} papers`]
    case 'embed':       return ['log-line', `  Embedding ${event.count} new papers…`]
    case 'eval_done':   return ['log-line success', `  New papers: ${event.relevante || 0} relevant, ${event.potencialmente_relevante || 0} potential, ${event.no_relevante || 0} low`]
    case 'done':        return ['log-line success', `✓ Done — ${event.added} added, ${event.already} already present, library now ${event.total}`]
    case 'error':       return ['log-line error', `✗ Error${event.source ? ` (${src(event.source)})` : ''}: ${event.message}`]
    case 'result':      return null
    default:            return ['log-line', JSON.stringify(event)]
  }
}

export default function PipelineLog({ logs, isRunning }) {
  const bottomRef = useRef(null)
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [logs])

  return (
    <div className="pipeline-log">
      <div className="pipeline-log-header">
        {isRunning && <span className="spinner" />}
        Pipeline
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
