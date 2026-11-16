// Per-viewer UI preferences in localStorage. Every access is guarded: storage can be
// unavailable (private window, blocked site data) and the app must work without it.
const PREFIX = 'lra:'

export function loadPref(key, fallback = null) {
  try {
    const raw = localStorage.getItem(PREFIX + key)
    return raw == null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}

export function savePref(key, value) {
  try {
    if (value == null) localStorage.removeItem(PREFIX + key)
    else localStorage.setItem(PREFIX + key, JSON.stringify(value))
  } catch {
    /* storage unavailable: preferences just won't persist */
  }
}
