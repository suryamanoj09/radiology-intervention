import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import { initTheme } from './components/ThemeToggle.jsx'
import { initLogging } from './logger.js'
import './styles.css'

initTheme()     // re-sync data-theme; the flash-free stamp runs earlier via the
                // render-blocking inline script in index.html <head>.
initLogging()   // capture uncaught errors, rejections, and every API call into the
                // in-app log (viewable in Settings).

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
