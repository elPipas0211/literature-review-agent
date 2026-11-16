import { useState } from 'react'
import { saveOpenAlexSettings } from '../api/client.js'

const KEY_URL = 'https://openalex.org/rest-api'

export default function SettingsModal({ status, onClose, onSaved }) {
  const [key, setKey] = useState('')
  const [email, setEmail] = useState(status?.email || '')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)

  const save = async (fields, done) => {
    setSaving(true); setError(null); setMessage(null)
    try {
      const next = await saveOpenAlexSettings(fields)
      onSaved(next)
      setKey('')
      setMessage(done)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const emailChanged = email.trim() !== (status?.email || '')

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal settings-modal" role="dialog" aria-labelledby="settings-title">
        <div className="modal-header">
          <h2 id="settings-title">Settings</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <section className="settings-section">
          <div className="detail-section-label">OpenAlex API key</div>
          <p className={`key-status ${status?.has_key ? 'ok' : 'missing'}`}>
            {status?.has_key
              ? '✓ A key is saved. Searches use it.'
              : 'No key saved. When OpenAlex is busy it limits searches without a key, so they can fail.'}
          </p>
          <p className="hint">
            The key is free. Sign up at <a href={KEY_URL} target="_blank" rel="noreferrer" className="link">openalex.org</a>,
            copy your API key and paste it here. It is stored only on this computer, in the project's
            <code> .env</code> file, which is never committed to git.
          </p>
          <form className="settings-row" onSubmit={(e) => { e.preventDefault(); if (key.trim()) save({ api_key: key.trim() }, 'Key saved.') }}>
            <input className="input input-grow" type="password" autoComplete="off" spellCheck={false}
              placeholder={status?.has_key ? 'Paste a new key to replace it' : 'Paste your API key'}
              value={key} onChange={(e) => setKey(e.target.value)} />
            <button className="btn btn-primary btn-sm" disabled={saving || !key.trim()}>Save key</button>
          </form>
          {status?.has_key && (
            <button className="btn-text" disabled={saving} onClick={() => save({ api_key: '' }, 'Key removed.')}>
              Remove saved key
            </button>
          )}
        </section>

        <section className="settings-section">
          <div className="detail-section-label">Contact email (optional)</div>
          <p className="hint">Sent with each request so OpenAlex can contact you if something goes wrong.</p>
          <form className="settings-row" onSubmit={(e) => { e.preventDefault(); save({ email: email.trim() }, 'Email saved.') }}>
            <input className="input input-grow" type="email" placeholder="you@university.edu"
              value={email} onChange={(e) => setEmail(e.target.value)} />
            <button className="btn btn-outline btn-sm" disabled={saving || !emailChanged}>Save email</button>
          </form>
        </section>

        {message && <p className="hint settings-ok">{message}</p>}
        {error && <p className="error-inline">{error}</p>}
      </div>
    </div>
  )
}
