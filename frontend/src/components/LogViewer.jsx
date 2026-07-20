import { useEffect, useMemo, useState } from 'react'
import { getLogs, clearLogs, subscribe } from '../logger.js'

// In-app diagnostics: shows the client log ring buffer (API calls, errors + reasons,
// uncaught exceptions). Live-updates via the logger's subscribe(). No PHI is captured
// (bodies are never logged), so it's safe to copy/download when reporting an issue.
const LEVELS = ['all', 'info', 'warn', 'error']

export default function LogViewer() {
  const [entries, setEntries] = useState(() => getLogs())
  const [filter, setFilter] = useState('all')

  useEffect(() => subscribe(() => setEntries(getLogs())), [])

  const shown = useMemo(
    () => (filter === 'all' ? entries : entries.filter((e) => e.level === filter)).slice().reverse(),
    [entries, filter],
  )
  const counts = useMemo(() => ({
    error: entries.filter((e) => e.level === 'error').length,
    warn: entries.filter((e) => e.level === 'warn').length,
    info: entries.filter((e) => e.level === 'info').length,
  }), [entries])

  function copyAll() {
    const text = entries.map((e) => `${e.t} [${e.level}] ${e.message}${e.meta ? ' ' + JSON.stringify(e.meta) : ''}`).join('\n')
    navigator.clipboard?.writeText(text).catch(() => { /* ignore */ })
  }

  function download() {
    const text = entries.map((e) => JSON.stringify(e)).join('\n')
    const url = URL.createObjectURL(new Blob([text], { type: 'application/x-ndjson' }))
    const a = document.createElement('a')
    a.href = url; a.download = 'radassist-log.ndjson'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="logviewer">
      <div className="lv-bar">
        <div className="seg lv-filter" role="group" aria-label="Log level filter">
          {LEVELS.map((l) => (
            <button key={l} className={filter === l ? 'active' : ''} aria-pressed={filter === l} onClick={() => setFilter(l)}>
              {l}{l === 'error' && counts.error ? ` (${counts.error})` : ''}
              {l === 'warn' && counts.warn ? ` (${counts.warn})` : ''}
            </button>
          ))}
        </div>
        <span className="lv-count muted small">{entries.length} events</span>
        <button className="btn btn-small" onClick={copyAll} disabled={!entries.length}>Copy</button>
        <button className="btn btn-small" onClick={download} disabled={!entries.length}>Download</button>
        <button className="btn btn-small" onClick={() => { clearLogs(); setEntries([]) }} disabled={!entries.length}>Clear</button>
      </div>
      <div className="lv-list" role="log" aria-live="polite">
        {shown.length === 0 && <p className="muted small">No log events yet.</p>}
        {shown.map((e) => (
          <div key={e.id} className={`lv-row lv-${e.level}`}>
            <span className="lv-time">{e.t.slice(11, 19)}</span>
            <span className="lv-level">{e.level}</span>
            <span className="lv-msg">{e.message}
              {e.meta?.reason && <span className="lv-reason"> — {String(e.meta.reason).slice(0, 220)}</span>}
              {e.meta?.ms != null && <span className="muted"> · {e.meta.ms}ms</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
