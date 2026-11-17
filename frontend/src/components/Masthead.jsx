import { useEffect, useRef, useState } from 'react'
import { createProject, deleteProject, renameProject } from '../api/client.js'

function ProjectSelector({ projects, currentProject, onProjectChange, onProjectsReload }) {
  const [open, setOpen]         = useState(false)
  const [showNew, setShowNew]   = useState(false)
  const [newName, setNewName]   = useState('')
  const [creating, setCreating] = useState(false)
  const [renaming, setRenaming] = useState(null)
  const [renameName, setRename] = useState('')
  const [deleting, setDeleting] = useState(null)   // project name awaiting confirm
  const [error, setError]       = useState(null)
  const containerRef            = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (!containerRef.current?.contains(e.target)) closeAll()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  function closeAll() {
    setOpen(false); setShowNew(false); setNewName('')
    setRenaming(null); setDeleting(null); setError(null)
  }

  async function handleCreate(e) {
    e.preventDefault()
    const name = newName.trim()
    if (!name || creating) return
    setCreating(true); setError(null)
    try {
      await createProject(name)
      await onProjectsReload()
      onProjectChange(name)
      closeAll()
    } catch (err) { setError(err.message) }
    finally { setCreating(false) }
  }

  async function handleRename(e, oldName) {
    e.preventDefault()
    const name = renameName.trim()
    if (!name || name === oldName) { setRenaming(null); return }
    setError(null)
    try {
      await renameProject(oldName, name)
      await onProjectsReload()
      if (currentProject === oldName) onProjectChange(name)
      setRenaming(null)
    } catch (err) { setError(err.message) }
  }

  async function handleDelete(name) {
    setError(null)
    try {
      await deleteProject(name)
      await onProjectsReload()
      if (currentProject === name) onProjectChange('')
      setDeleting(null)
    } catch (err) { setError(err.message) }
  }

  return (
    <div ref={containerRef} className="project-selector">
      <button className="project-trigger" onClick={() => setOpen((v) => !v)}>
        <span className="trigger-label">{currentProject || 'Select project…'}</span>
        <span className="trigger-arrow">{open ? '▴' : '▾'}</span>
      </button>

      {open && (
        <div className="project-dropdown">
          {projects.length === 0 && (
            <div className="dropdown-empty">No projects yet</div>
          )}

          {projects.map((p) => (
            <div key={p} className={`project-item${currentProject === p ? ' selected' : ''}`}>
              {renaming === p ? (
                /* ── rename mode ── */
                <form className="rename-form" onSubmit={(e) => handleRename(e, p)}>
                  <input
                    autoFocus
                    className="input rename-input"
                    value={renameName}
                    onChange={(e) => setRename(e.target.value)}
                    onKeyDown={(e) => e.key === 'Escape' && setRenaming(null)}
                  />
                  <button type="submit" className="btn btn-sm btn-primary"
                    disabled={!renameName.trim() || renameName.trim() === p}>✓</button>
                  <button type="button" className="btn btn-sm btn-outline"
                    onClick={() => setRenaming(null)}>✕</button>
                </form>
              ) : deleting === p ? (
                /* ── delete confirm mode ── */
                <div className="delete-confirm">
                  <span className="delete-confirm-label">Delete <strong>{p}</strong>?</span>
                  <button
                    className="btn btn-sm"
                    style={{ background: 'var(--error)', color: 'var(--cream-light)', border: 'none' }}
                    onClick={() => handleDelete(p)}
                  >Delete</button>
                  <button className="btn btn-sm btn-outline"
                    onClick={() => setDeleting(null)}>Cancel</button>
                </div>
              ) : (
                /* ── normal mode ── */
                <>
                  <button className="project-name-btn"
                    onClick={() => { onProjectChange(p); closeAll() }}>
                    {p}
                  </button>
                  <button className="project-rename-btn" title="Rename"
                    onClick={(e) => { e.stopPropagation(); setRenaming(p); setRename(p); setDeleting(null); setError(null) }}>
                    ✎
                  </button>
                  <button className="project-delete-btn" title="Delete project"
                    onClick={(e) => { e.stopPropagation(); setDeleting(p); setRenaming(null); setError(null) }}>
                    🗑
                  </button>
                </>
              )}
            </div>
          ))}

          {error && <div className="dropdown-error">{error}</div>}

          <div className="dropdown-divider" />

          {showNew ? (
            <form className="new-project-form" onSubmit={handleCreate}>
              <input autoFocus className="input new-project-input"
                placeholder="Project name…" value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === 'Escape' && setShowNew(false)} />
              <button type="submit" className="btn btn-sm btn-primary"
                disabled={!newName.trim() || creating}>
                {creating ? '…' : 'Create'}
              </button>
            </form>
          ) : (
            <button className="new-project-btn"
              onClick={() => { setShowNew(true); setRenaming(null); setDeleting(null); setError(null) }}>
              + New project
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default function Masthead({ projects, currentProject, onProjectChange, onProjectsReload, onImport, onSettings, needsKey, onHome }) {
  return (
    <header className="masthead">
      <button className="masthead-left" onClick={onHome} title="All projects">
        <span className="masthead-title">The Literature Review</span>
        <span className="masthead-tagline">Find, rank and organize papers for your review</span>
      </button>
      <div className="masthead-right">
        <ProjectSelector
          projects={projects}
          currentProject={currentProject}
          onProjectChange={onProjectChange}
          onProjectsReload={onProjectsReload}
        />
        {currentProject && (
          <button className="btn btn-ghost btn-sm" onClick={onImport}>Import CSV</button>
        )}
        <button className="btn btn-ghost btn-sm settings-btn" onClick={onSettings}
          title={needsKey ? 'No OpenAlex API key: searches may be rate-limited' : 'Settings'}>
          Settings{needsKey && <span className="attention-dot" aria-label="needs attention" />}
        </button>
      </div>
    </header>
  )
}
