import { useEffect, useRef } from 'react'

function logLine(event) {
  switch (event.type) {
    case 'stage':       return { cls: 'log-line', text: `▸ ${event.message}` }
    case 'fetch_start': return { cls: 'log-line fetch', text: `  Fetching from ${event.source}…` }
    case 'fetch_done':
      return {
        cls: 'log-line fetch',
        text: `  ${event.source}: ${event.retrieved} retrieved, ${event.passed} passed filter`,
      }
    case 'dedup':
      return {
        cls: 'log-line',
        text: `  Dedup — DOI: ${event.doi}, title: ${event.title}, master: ${event.master} → ${event.remaining} remain`,
      }
    case 'floor':
      return {
        cls: event.remaining === 0 ? 'log-line warn' : 'log-line',
        text: `  Citation floor: ${event.discarded} discarded, ${event.remaining} proceed`,
      }
    case 'eval_start':  return { cls: 'log-line', text: `  Evaluating ${event.count} papers semantically…` }
    case 'eval_done': {
      const rel = event.relevante || 0
      const pot = event.potencialmente_relevante || 0
      const disc = event.descartado_semantica || 0
      return {
        cls: 'log-line success',
        text: `  Evaluation: ${rel} relevant, ${pot} potential, ${disc} discarded`,
      }
    }
    case 'insert':
      return {
        cls: 'log-line success',
        text: `  Inserted ${event.added} new papers (${event.skipped} already in DB)`,
      }
    case 'done':
      return {
        cls: 'log-line success',
        text: `✓ Done — ${event.inserted} new papers added to master database`,
      }
    case 'error':
      return { cls: 'log-line error', text: `✗ Error${event.source ? ` (${event.source})` : ''}: ${event.message}` }
    default:
      return { cls: 'log-line', text: JSON.stringify(event) }
  }
}

export default function PipelineLog({ logs, isRunning }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="pipeline-log">
      <div className="pipeline-log-header">
        {isRunning && <span className="spinner" />}
        Pipeline
      </div>
      <div className="pipeline-log-body">
        {logs.map((event, i) => {
          const { cls, text } = logLine(event)
          return <span key={i} className={cls}>{text}</span>
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
