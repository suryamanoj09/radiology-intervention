import { Component } from 'react'
import { log } from '../logger.js'

// Top-level safety net: a thrown render error in any component shows a recoverable
// notice instead of a blank white screen (which would silently lose the clinician's
// viewer/report state). Not a substitute for handling errors locally — a last resort.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    log.error('React render error', { reason: String(error?.stack || error), component: info?.componentStack?.split('\n')[1]?.trim() })
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary" role="alert">
          <h2>Something went wrong in the interface.</h2>
          <p className="muted">
            The page hit an unexpected error. Your data was not sent anywhere. Reload to
            continue — if it recurs, note what you were doing and report it.
          </p>
          <button className="btn" onClick={() => window.location.reload()}>Reload</button>
        </div>
      )
    }
    return this.props.children
  }
}
