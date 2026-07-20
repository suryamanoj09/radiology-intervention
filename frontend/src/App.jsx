import { useEffect, useState } from 'react'
import { emptyPatient } from './components/PatientIntake.jsx'
import WorkspaceLayout from './components/workspace/WorkspaceLayout.jsx'
import InfoPage from './components/InfoPage.jsx'
import KnownLimitations from './components/KnownLimitations.jsx'
import FailureGallery from './components/FailureGallery.jsx'
import ThemeToggle from './components/ThemeToggle.jsx'
import FeedbackAdmin from './components/FeedbackAdmin.jsx'
import HomePage from './components/HomePage.jsx'
import AboutPage from './components/AboutPage.jsx'
import EvidencePage from './components/EvidencePage.jsx'
import HelpPage from './components/HelpPage.jsx'
import UploadScreen from './components/UploadScreen.jsx'
import Dashboard from './components/dashboard/Dashboard.jsx'
import PrivacyPolicy from './components/PrivacyPolicy.jsx'
import SettingsPage from './components/SettingsPage.jsx'
import ProfilePage from './components/ProfilePage.jsx'
import MarketingHeader from './components/shell/MarketingHeader.jsx'
import MarketingFooter from './components/shell/MarketingFooter.jsx'
import AppShell from './components/shell/AppShell.jsx'
import Login from './components/Login.jsx'
import { shellFor, titleFor } from './routes/pageRegistry.js'
import { analyzeImage, compareStudies, getBehaviorCard, me } from './api.js'
import { aiSuggestions, emptyStructured } from './labelMap.js'
import { log } from './logger.js'

export default function App() {
  const [page, setPage] = useState('home')   // see routes/pageRegistry.js for the full set
  const [tab, setTab] = useState('xray')
  const [infoOpen, setInfoOpen] = useState(false)
  const [limitsOpen, setLimitsOpen] = useState(false)
  const [failuresOpen, setFailuresOpen] = useState(false)
  const [adminOpen, setAdminOpen] = useState(false)
  const [railsCollapsed, setRailsCollapsed] = useState(false)
  const [analysis, setAnalysis] = useState(null)
  const [prior, setPrior] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [comparisonError, setComparisonError] = useState(null)
  // structured = CLINICIAN-CONFIRMED findings only; starts empty every study.
  const [structured, setStructured] = useState(emptyStructured())
  const [history, setHistory] = useState('')
  const [busySlot, setBusySlot] = useState(null) // 'current' | 'prior' | null
  const [error, setError] = useState(null)
  const [behaviorCard, setBehaviorCard] = useState(null)
  // BUG2: session search text from the TopBar; filters the Dashboard worklist/activity.
  const [studyQuery, setStudyQuery] = useState('')
  // BUG5: was a patient name explicitly typed at the Upload intake for THIS study?
  // Lives for one analysis so a typed name survives into the workspace/PDF without
  // a stale name bleeding across a later study.
  const [intakeEntered, setIntakeEntered] = useState(false)
  // Current user, fetched once for the console TopBar/Sidebar. Tolerates auth
  // being disabled: me() resolves to { auth_enabled:false, authenticated:false,
  // user:null } on any failure, so we degrade to a guest.
  const [meInfo, setMeInfo] = useState(null)
  // Grounded hover: label of the finding whose region should be highlighted in the Viewer.
  const [focusedFinding, setFocusedFinding] = useState(null)
  // Patient identifiers: OPTIONAL, client-side ONLY. Kept in React state + sessionStorage
  // (ephemeral — gone when the tab closes). NEVER sent to any /api endpoint, never
  // persisted server-side. Rendered only into the locally-exported PDF header.
  const [patient, setPatient] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('radassist_patient') || 'null') || emptyPatient() }
    catch { return emptyPatient() }
  })
  useEffect(() => {
    try { sessionStorage.setItem('radassist_patient', JSON.stringify(patient)) } catch { /* ignore */ }
  }, [patient])

  // On page navigation: scroll to top (a single-page app has no browser scroll reset)
  // and dismiss any analyzer utility modal so it can't stack over another page.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
    setInfoOpen(false); setLimitsOpen(false); setFailuresOpen(false); setAdminOpen(false)
  }, [page])

  useEffect(() => {
    getBehaviorCard().then(setBehaviorCard).catch(() => setBehaviorCard({ available: false }))
  }, [])

  // Fetch the current user once for the console chrome. me() never rejects.
  useEffect(() => {
    me().then(setMeInfo).catch(() => setMeInfo({ auth_enabled: false, authenticated: false, user: null }))
  }, [])

  // Called by <Login> after a full sign-in (2FA satisfied when enrolled). Flip the
  // session locally so the gate lifts; the intended console route re-renders in place.
  // If the user reached Login via the explicit /login route, send them to the console.
  function handleAuthed(user) {
    setMeInfo((prev) => ({ ...(prev || {}), auth_enabled: true, authenticated: true, user }))
    if (page === 'login') setPage('dashboard')
  }

  // Autosave/draft recovery: radiologists get interrupted constantly, and a
  // half-written report + a tab crash = lost work. We persist the current analysis
  // + the report draft (history + confirmed findings) to localStorage and restore
  // it on load. Patient identifiers are NOT included (they stay in sessionStorage).
  const [draftRestored, setDraftRestored] = useState(false)
  useEffect(() => {
    try {
      const raw = localStorage.getItem('radassist_report_session')
      if (raw) {
        const d = JSON.parse(raw)
        if (d && d.analysis) {
          setAnalysis(d.analysis)
          setStructured(d.structured || emptyStructured())
          setHistory(d.history || '')
          setDraftRestored(true)
        }
      }
    } catch { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    try {
      if (analysis) {
        localStorage.setItem('radassist_report_session',
          JSON.stringify({ analysis, history, structured, ts: Date.now() }))
      }
    } catch { /* ignore (quota) */ }
  }, [analysis, history, structured])

  async function handleUpload(file) {
    setBusySlot('current')
    setError(null)
    setComparison(null)
    setComparisonError(null)
    try {
      const result = await analyzeImage(file)
      setAnalysis(result)
      setStructured(emptyStructured()) // never auto-confirm AI flags
      setHistory('')
      setFocusedFinding(null)
      // BUG5: preserve identifiers explicitly typed at the Upload intake for THIS
      // study (so a name survives into the Report header + PDF filename); otherwise
      // clear to avoid cross-patient bleed. The intake flag is good for one analysis.
      if (!(intakeEntered && patient?.name?.trim())) setPatient(emptyPatient())
      setIntakeEntered(false)
      if (prior) {
        try {
          setComparison(await compareStudies(prior.image_id, result.image_id))
        } catch (e) {
          setComparisonError(e.message)
        }
      }
      setPage('app') // navigate to the workspace ONLY after a successful analyze
    } catch (e) {
      setError(e.message)
      log.error('Analyze failed', { reason: e.message })
      // BUG1 (SAFETY): a failed analyze must not leave a stale study/report on screen.
      setAnalysis(null)
      setStructured(emptyStructured())
      setHistory('')
      setFocusedFinding(null)
      setComparison(null)
      setComparisonError(null)
      try { localStorage.removeItem('radassist_report_session') } catch { /* ignore */ }
      throw e // let an awaiting UploadScreen render the failure/abstain state
    } finally {
      setBusySlot(null)
    }
  }

  async function handlePriorUpload(file) {
    setBusySlot('prior')
    setError(null)
    setComparisonError(null)
    try {
      const result = await analyzeImage(file)
      setPrior(result)
      if (analysis) {
        try {
          setComparison(await compareStudies(result.image_id, analysis.image_id))
        } catch (e) {
          setComparisonError(e.message)
        }
      }
    } catch (e) {
      setError(e.message)
      log.error('Prior analyze failed', { reason: e.message })
      // BUG1 (SAFETY): drop the stale prior + any comparison on failure.
      setPrior(null)
      setComparison(null)
      setComparisonError(null)
    } finally {
      setBusySlot(null)
    }
  }

  // Shared draft-dismiss used by the workspace note AND the TopBar 'draft' alert.
  function onDismissDraft() {
    try { localStorage.removeItem('radassist_report_session') } catch { /* ignore */ }
    setDraftRestored(false)
  }

  // Clear the CURRENT study so a fresh image can be uploaded (X-ray). Resets the
  // analysis, confirmed findings, report draft, identifiers, and comparison; keeps
  // the prior study so a fresh current can still be compared against it.
  function clearStudy() {
    setAnalysis(null)
    setStructured(emptyStructured())
    setHistory('')
    setFocusedFinding(null)
    setComparison(null)
    setComparisonError(null)
    setError(null)
    setPatient(emptyPatient())
    setIntakeEntered(false)
    setDraftRestored(false)
    try { localStorage.removeItem('radassist_report_session') } catch { /* ignore */ }
  }

  // Clear the prior/comparison slot.
  function clearPrior() {
    setPrior(null)
    setComparison(null)
    setComparisonError(null)
  }

  // BUG3: derive REAL session alerts for the TopBar bell (no fabricated notices).
  const alerts = []
  if (analysis?.competence === 'abstain') {
    alerts.push({ id: 'abstain', kind: 'abstain', text: 'Model abstained - out-of-distribution / not a readable chest X-ray' })
  }
  if (analysis?.triage === 'urgent') {
    alerts.push({ id: 'urgent', kind: 'urgent', text: 'This study was triaged URGENT - review promptly' })
  }
  if (draftRestored) {
    alerts.push({ id: 'draft', kind: 'draft', text: 'A report draft was restored from your last session', onDismiss: onDismissDraft })
  }

  const suggestions = analysis ? aiSuggestions(analysis.findings) : []

  // Session worklist for the console Dashboard. HONESTY: there is no server PHI
  // worklist — this is only the study analysed in THIS browser session (or empty).
  const sessionStudies = analysis ? [analysis] : []

  // ---- Console chrome props -------------------------------------------------
  // meInfo.user is a username string (or null when auth is off / guest).
  const consoleUser = { name: meInfo?.user || 'Guest' }
  // Sidebar CLINICAL nav — overrides the default so "New analysis" routes to the
  // analyzer workspace page key ('app'), not the default 'workspace'.
  const clinicalNav = [
    { icon: 'dashboard', label: 'Dashboard', route: 'dashboard', onClick: () => setPage('dashboard') },
    { icon: 'workspace', label: 'New analysis', route: 'app', onClick: () => setPage('app') },
    { icon: 'upload', label: 'Upload', route: 'upload', onClick: () => setPage('upload') },
  ]

  // ---- Routed page content --------------------------------------------------
  function renderPage() {
    switch (page) {
      case 'home':
        return <HomePage onLaunch={() => setPage('app')} onNav={setPage} behaviorCard={behaviorCard} />
      case 'about':
        return <AboutPage onLaunch={() => setPage('app')} onNav={setPage} behaviorCard={behaviorCard} />
      case 'privacy':
        return <PrivacyPolicy onNav={setPage} />
      case 'settings':
        return <SettingsPage behaviorCard={behaviorCard} />
      case 'profile':
        return <ProfilePage meInfo={meInfo} onNav={setPage} onSignedOut={setMeInfo} />
      case 'dashboard':
        return (
          <Dashboard
            behaviorCard={behaviorCard}
            sessionStudies={sessionStudies}
            studyQuery={studyQuery}
            onNav={setPage}
            onOpenStudy={(study) => {
              // Honor the study argument (single-study session model): re-select the
              // clicked row, then open the workspace.
              if (study && study.image_id) setAnalysis(study)
              setPage('app')
            }}
          />
        )
      case 'upload':
        return (
          <UploadScreen
            onAnalyze={handleUpload}
            patient={patient}
            setPatient={(p) => { setIntakeEntered(true); setPatient(p) }}
            onNav={setPage}
          />
        )
      case 'evidence':
        return <EvidencePage behaviorCard={behaviorCard} onNav={setPage} />
      case 'help':
        return (
          <HelpPage
            onNav={setPage}
            onOpenInfo={() => setInfoOpen(true)}
            onOpenLimitations={() => setLimitsOpen(true)}
            onOpenFailures={() => setFailuresOpen(true)}
            behaviorCard={behaviorCard}
          />
        )
      case 'app':
        return renderWorkspace()
      default:
        return <HomePage onLaunch={() => setPage('app')} onNav={setPage} behaviorCard={behaviorCard} />
    }
  }

  // ---- Analyzer workspace (WF5 redesign) ------------------------------------
  // The polished 3-pane layout is composed in <WorkspaceLayout>; every prop maps
  // 1:1 to the analyzer state/handlers above. The four utility modals stay lifted
  // to the App root (rendered via {modals}); WorkspaceLayout only opens them.
  function renderWorkspace() {
    return (
      <WorkspaceLayout
        tab={tab}
        setTab={setTab}
        analysis={analysis}
        suggestions={suggestions}
        structured={structured}
        setStructured={setStructured}
        history={history}
        setHistory={setHistory}
        patient={patient}
        setPatient={setPatient}
        behaviorCard={behaviorCard}
        focusedFinding={focusedFinding}
        setFocusedFinding={setFocusedFinding}
        busySlot={busySlot}
        error={error}
        prior={prior}
        comparison={comparison}
        comparisonError={comparisonError}
        onUpload={(f) => handleUpload(f).catch(() => { /* error surfaced via error state */ })}
        onPriorUpload={handlePriorUpload}
        onClearStudy={clearStudy}
        onClearPrior={clearPrior}
        draftRestored={draftRestored}
        onDismissDraft={onDismissDraft}
        railsCollapsed={railsCollapsed}
        setRailsCollapsed={setRailsCollapsed}
        onOpenInfo={() => setInfoOpen(true)}
        onOpenLimitations={() => setLimitsOpen(true)}
        onOpenFailures={() => setFailuresOpen(true)}
        onOpenAdmin={() => setAdminOpen(true)}
      />
    )
  }

  // ---- Shell selection ------------------------------------------------------
  const shell = shellFor(page)
  const content = renderPage()

  // Utility modals rendered at the App root so they overlay ANY shell — the
  // analyzer opens them from its toolbar, and HelpPage opens them from the
  // marketing shell (onOpenInfo/onOpenLimitations/onOpenFailures). Navigating to
  // another page dismisses them via the [page] effect above.
  const modals = (
    <>
      {infoOpen && <InfoPage onClose={() => setInfoOpen(false)} />}
      {limitsOpen && <KnownLimitations onClose={() => setLimitsOpen(false)} />}
      {failuresOpen && <FailureGallery onClose={() => setFailuresOpen(false)} />}
      {adminOpen && <FeedbackAdmin onClose={() => setAdminOpen(false)} />}
    </>
  )

  // ---- Optional auth gate ---------------------------------------------------
  // Only bites when the backend reports AUTH_ENABLED and the visitor is not fully
  // authenticated (2FA satisfied when enrolled). It gates the CONSOLE surface only;
  // the marketing site stays public. When AUTH_ENABLED is off (the default open
  // demo) meInfo.auth_enabled is false, so this is a pure no-op and behaviour is
  // exactly as before. The explicit /login route always shows the sign-in screen.
  const authGateActive = !!(meInfo && meInfo.auth_enabled && !meInfo.authenticated)
  const needsLogin = page === 'login' || (authGateActive && shell === 'console')
  if (needsLogin) {
    // Full-bleed sign-in screen (its own 100vh layout — no marketing/console chrome).
    return <Login onAuthed={handleAuthed} onNav={setPage} />
  }

  if (shell === 'bare') {
    // Full-bleed, no chrome. The only bare route today is 'login', which the auth
    // gate above already intercepts; any other bare route falls back to the
    // sign-in screen rather than a placeholder stub.
    return <Login onAuthed={handleAuthed} onNav={setPage} />
  }

  if (shell === 'console') {
    return (
      <AppShell
        route={page}
        title={titleFor(page)}
        user={consoleUser}
        onNav={setPage}
        onSearch={setStudyQuery}
        alerts={alerts}
        items={clinicalNav}
        themeSlot={<ThemeToggle />}
      >
        {modals}
        {content}
      </AppShell>
    )
  }

  // Default: marketing shell.
  return (
    <div className="app">
      {modals}
      <MarketingHeader route={page} onNav={setPage}>
        <ThemeToggle />
      </MarketingHeader>
      {content}
      <MarketingFooter onNav={setPage} />
    </div>
  )
}
