const BASE = '/api'
const enc = encodeURIComponent

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, opts)
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const d = await res.json(); msg = d.detail ?? JSON.stringify(d) } catch { msg = await res.text() || msg }
    throw new Error(msg)
  }
  return res.json()
}

export const getProjects = () => req('/projects')

export const createProject = (name) =>
  req('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })

export const renameProject = (name, newName) =>
  req(`/projects/${enc(name)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_name: newName }),
  })

export const deleteProject = (name) =>
  req(`/projects/${enc(name)}`, { method: 'DELETE' })

export const getPapers   = (project) => req(`/projects/${enc(project)}/papers`)
export const getStats    = (project) => req(`/projects/${enc(project)}/stats`)
export const getClusters = (project) => req(`/projects/${enc(project)}/clusters`)

export const queryPapers = (project, question, top = 5) =>
  req(`/projects/${enc(project)}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top }),
  })

/** POST SSE stream — yields parsed event objects */
export async function* streamSearch(project, params, signal) {
  const res = await fetch(`${BASE}/projects/${enc(project)}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
    signal,
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const d = await res.json(); msg = d.detail ?? JSON.stringify(d) } catch { msg = await res.text() || msg }
    throw new Error(msg)
  }
  yield* _readSSE(res.body, signal)
}

/** POST SSE stream for CSV import (multipart form) */
export async function* streamImport(project, file, context, signal) {
  const form = new FormData()
  form.append('file', file)
  if (context) form.append('context', context)
  const res = await fetch(`${BASE}/projects/${enc(project)}/import`, {
    method: 'POST',
    body: form,
    signal,
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const d = await res.json(); msg = d.detail ?? JSON.stringify(d) } catch { msg = await res.text() || msg }
    throw new Error(msg)
  }
  yield* _readSSE(res.body, signal)
}

/** POST SSE stream for cluster generation */
export async function* streamClusters(project, params, signal) {
  const res = await fetch(`${BASE}/projects/${enc(project)}/clusters`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
    signal,
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const d = await res.json(); msg = d.detail ?? JSON.stringify(d) } catch { msg = await res.text() || msg }
    throw new Error(msg)
  }
  yield* _readSSE(res.body, signal)
}

async function* _readSSE(body, signal) {
  const reader = body.getReader()
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

/** Generates a BibTeX entry client-side from a paper object */
export function paperToBibtex(paper) {
  const doi = (paper.externalIds?.DOI || '').trim()
  const year = paper.year || ''
  const rawKey = doi
    ? doi.replace(/[^a-zA-Z0-9]/g, '').slice(0, 20)
    : ((paper.title || 'unknown').replace(/\s+/g, '').slice(0, 12) + year)
  const authors = (paper.authors || []).map((a) => a.name).join(' and ')
  const venue = paper.venue || ''
  return `@article{${rawKey},
  title     = {${paper.title || ''}},
  author    = {${authors}},
  year      = {${year}},
  journal   = {${venue}},
  doi       = {${doi}},
}`
}
