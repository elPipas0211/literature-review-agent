const BASE = '/api'
const enc = encodeURIComponent

async function errorMessage(res) {
  const text = await res.text()
  try {
    const d = JSON.parse(text)
    if (typeof d.detail === 'string') return d.detail
    if (Array.isArray(d.detail)) return d.detail.map((x) => x.msg).join('; ')
    return JSON.stringify(d)
  } catch {
    return text || `HTTP ${res.status}`
  }
}

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, opts)
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json()
}

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const getConfig     = () => req('/config')
export const saveOpenAlexSettings = (fields) => req('/settings/openalex', json('PUT', fields))
export const getProjects   = () => req('/projects')
export const createProject = (name, context = '') => req('/projects', json('POST', { name, context }))
export const getProjectSummaries = () => req('/projects/summary')
export const renameProject = (name, newName) => req(`/projects/${enc(name)}`, json('PATCH', { new_name: newName }))
export const deleteProject = (name) => req(`/projects/${enc(name)}`, { method: 'DELETE' })
export const getMeta       = (project) => req(`/projects/${enc(project)}/meta`)
export const setContext    = (project, context) => req(`/projects/${enc(project)}/context`, json('PUT', { context }))
export const getPapers     = (project) => req(`/projects/${enc(project)}/papers`)
export const getPrisma     = (project) => req(`/projects/${enc(project)}/prisma`)
export const getClusters   = (project) => req(`/projects/${enc(project)}/clusters`)
export const queryPapers   = (project, question, top = 10) =>
  req(`/projects/${enc(project)}/query`, json('POST', { question, top }))

/** Download an export (csv | ris | bib). `ids` = null exports the whole library. */
export async function downloadExport(project, format, ids = null) {
  const res = await fetch(`${BASE}/projects/${enc(project)}/export`, json('POST', { format, ids }))
  if (!res.ok) throw new Error(await errorMessage(res))
  const blob = await res.blob()
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1]
    || `${project}.${format}`
  const url = URL.createObjectURL(blob)
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

async function* sse(path, opts) {
  const res = await fetch(`${BASE}${path}`, opts)
  if (!res.ok) throw new Error(await errorMessage(res))
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() ?? ''
      for (const part of parts) {
        for (const line of part.split('\n')) {
          if (line.startsWith('data: ')) {
            try { yield JSON.parse(line.slice(6)) } catch { /* skip malformed */ }
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export const streamSearch = (project, params, signal) =>
  sse(`/projects/${enc(project)}/search`, { ...json('POST', params), signal })

export function streamImport(project, file, context, signal) {
  const form = new FormData()
  form.append('file', file)
  if (context) form.append('context', context)
  return sse(`/projects/${enc(project)}/import`, { method: 'POST', body: form, signal })
}

export const streamClusters = (project, params, signal) =>
  sse(`/projects/${enc(project)}/clusters`, { ...json('POST', params), signal })

export const annotatePaper = (project, id, fields) =>
  req(`/projects/${enc(project)}/annotate`, json('POST', { id, ...fields }))

export const getTrend = (q, yearFrom = 2000) =>
  req(`/trend?q=${enc(q)}&year_from=${yearFrom}`)

export const streamSnowball = (project, params, signal) =>
  sse(`/projects/${enc(project)}/snowball`, { ...json('POST', params), signal })
