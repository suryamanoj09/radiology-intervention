// Lightweight in-browser logger: a bounded ring buffer of {info|warn|error} events
// with subscribers, plus global capture of uncaught errors, unhandled promise
// rejections, and every fetch (method/url/status/timing + failure reason). Nothing
// here is sent to the server; it's a client-side diagnostics aid surfaced in Settings.
// It never logs response BODIES, so no PHI/finding data is captured.

const MAX = 600
const _entries = []
const _subs = new Set()
let _seq = 0

function _emit(level, message, meta) {
  const entry = {
    id: ++_seq,
    t: new Date().toISOString(),
    level,
    message: String(message),
    meta: meta && Object.keys(meta).length ? meta : undefined,
  }
  _entries.push(entry)
  if (_entries.length > MAX) _entries.shift()
  _subs.forEach((fn) => { try { fn(entry) } catch { /* subscriber error must not loop */ } })
  const c = level === 'error' ? console.error : level === 'warn' ? console.warn : console.info
  c(`[radassist:${level}] ${message}`, meta || '')
  return entry
}

export const log = {
  info: (m, meta) => _emit('info', m, meta),
  warn: (m, meta) => _emit('warn', m, meta),
  error: (m, meta) => _emit('error', m, meta),
}

export function getLogs() { return _entries.slice() }
export function clearLogs() { _entries.length = 0; _subs.forEach((fn) => { try { fn(null) } catch { /* */ } }) }
export function subscribe(fn) { _subs.add(fn); return () => _subs.delete(fn) }

// A short, human label for what an /api path does — so a log line reads meaningfully.
function _label(url = '') {
  const p = String(url)
  if (p.includes('/api/analyze-study')) return 'analyze study'
  if (p.includes('/api/analyze')) return 'analyze X-ray'
  if (p.includes('/api/dicom-view-series')) return 'load MR series'
  if (p.includes('/api/dicom-view')) return 'load CT/MR viewer'
  if (p.includes('/api/dicom-raw')) return 'raw intensity'
  if (p.includes('/api/dicom-roi')) return 'ROI stats'
  if (p.includes('/api/mr-segment') || p.includes('/api/segment')) return 'anatomy segmentation'
  if (p.includes('/api/mr-detect') || p.includes('/api/ct-detect')) return 'candidate detection'
  if (p.includes('/api/generate-report')) return 'generate report'
  if (p.includes('/api/compare')) return 'compare studies'
  if (p.includes('/api/feedback')) return 'feedback'
  return ''
}

export function initLogging() {
  if (typeof window === 'undefined' || window.__radlog_init) return
  window.__radlog_init = true

  window.addEventListener('error', (e) => {
    log.error(`Uncaught error: ${e.message || e.type}`,
      { source: e.filename, line: e.lineno, reason: String(e.error?.stack || e.error || e.message || e) })
  })
  window.addEventListener('unhandledrejection', (e) => {
    log.error('Unhandled promise rejection', { reason: String(e.reason?.stack || e.reason) })
  })

  const orig = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : (input && input.url) || ''
    const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase()
    const label = _label(url)
    const t0 = performance.now()
    try {
      const res = await orig(input, init)
      const ms = Math.round(performance.now() - t0)
      const tag = label ? `${label} (${method})` : `${method} ${url}`
      if (res.ok) log.info(`${tag} → ${res.status}`, { ms })
      else log.error(`${tag} → ${res.status} ${res.statusText || ''}`.trim(), { ms, status: res.status, reason: res.statusText })
      return res
    } catch (err) {
      const ms = Math.round(performance.now() - t0)
      log.error(`${label || method + ' ' + url} → network error`, { ms, reason: String(err) })
      throw err
    }
  }

  log.info('App started', { ua: navigator.userAgent })
}
