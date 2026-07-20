import { useRef, useState } from 'react'
import PatientIntake from './PatientIntake.jsx'

/**
 * UploadScreen — full-page upload / intake for the console shell (route 'upload').
 *
 * Matches the design (RadAssist.dc.html lines 862-894): a large drag-and-drop
 * intake zone, a live upload queue, plus a short "what happens to your data"
 * explainer and the OPTIONAL client-only PatientIntake.
 *
 * Reuses:
 *  - the file-select / drag logic pattern from UploadPanel.jsx (same `accept`)
 *  - the PatientIntake component verbatim, so its privacy contract is preserved:
 *    identifiers live only in App state + sessionStorage and are NEVER sent to
 *    the server. We just wire patient/setPatient through.
 *
 * Honesty: no fabricated queue of demo files. The queue shows only the real file
 * the user actually picked, in its true "analysing" state. Navigation to the
 * workspace is owned by App (onAnalyze -> handleUpload).
 *
 * Props:
 *   onAnalyze  (file) => void   — App wires this to handleUpload -> navigates to workspace
 *   patient    object           — current client-only identifiers (App state)
 *   setPatient (patient) => void — updates identifiers (mirrored to sessionStorage by App)
 *   onNav      (routeKey) => void — console navigation (e.g. back to workspace)
 */

// Same file types UploadPanel accepts — chest X-ray images only.
const ACCEPT = '.png,.jpg,.jpeg,.dcm,.dicom,image/png,image/jpeg'

function fmtSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function modalityOf(name) {
  return /\.(dcm|dicom)$/i.test(name || '') ? 'DICOM' : 'Image'
}

export default function UploadScreen({ onAnalyze, patient, setPatient, onNav }) {
  const inputRef = useRef(null)
  const [drag, setDrag] = useState(false)
  // The single real file the user picked (drives the live queue row).
  const [picked, setPicked] = useState(null)
  // Real state of the awaited analyze: 'analysing' while onAnalyze is pending,
  // 'error' if it rejects (abstain/failure). On success App navigates to the
  // workspace and unmounts this screen — we do NOT assume navigation ourselves.
  const [status, setStatus] = useState(null) // 'analysing' | 'error' | null
  const [errMsg, setErrMsg] = useState('')

  async function pick(file) {
    if (!file) return
    setPicked({ name: file.name, size: file.size, modality: modalityOf(file.name) })
    setErrMsg('')
    if (!onAnalyze) return
    setStatus('analysing')
    try {
      await onAnalyze(file)
      // Resolved: App is navigating to the workspace; leave the row in its pending
      // look until this screen unmounts (no fabricated 'done' claim needed).
      setStatus(null)
    } catch (e) {
      setStatus('error')
      setErrMsg(e?.message || 'Analysis failed — the image could not be read or was out-of-distribution.')
    }
  }

  function onInput(e) {
    if (e.target.files && e.target.files[0]) pick(e.target.files[0])
    e.target.value = ''
  }

  function openPicker() { inputRef.current?.click() }

  function onDrop(e) {
    e.preventDefault()
    setDrag(false)
    const f = e.dataTransfer?.files?.[0]
    if (f) pick(f)
  }

  const dropBase = {
    marginTop: '22px',
    borderRadius: '18px',
    border: `2px dashed ${drag ? 'var(--primary)' : 'var(--border-2)'}`,
    background: drag ? 'var(--primary-tint)' : 'var(--surface)',
    padding: '46px 24px',
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'border-color .15s, background .15s',
    outline: 'none',
  }

  return (
    <div style={{ padding: '26px 28px 44px', maxWidth: '960px', margin: '0 auto' }}>
      <h2 style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-head)', color: 'var(--ink)' }}>
        Upload studies
      </h2>
      <p style={{ color: 'var(--muted)', fontSize: '14px', marginTop: '4px' }}>
        Drag in DICOM, PNG or JPG. Metadata is extracted, burned-in markers are masked, and files are
        validated before analysis.
      </p>

      {/* Dropzone -------------------------------------------------------------- */}
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload a study — drop a file or press Enter to browse"
        style={dropBase}
        onClick={openPicker}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openPicker() } }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onMouseEnter={(e) => { if (!drag) e.currentTarget.style.borderColor = 'var(--primary)' }}
        onMouseLeave={(e) => { if (!drag) e.currentTarget.style.borderColor = 'var(--border-2)' }}
      >
        <input ref={inputRef} type="file" accept={ACCEPT} hidden onChange={onInput} />
        <div style={{
          width: '60px', height: '60px', borderRadius: '16px', margin: '0 auto',
          display: 'grid', placeItems: 'center', background: 'var(--primary-tint)', color: 'var(--primary)',
        }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 15V3m0 0 4 4m-4-4L8 7" />
            <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
          </svg>
        </div>
        <div style={{ fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: '17px', marginTop: '16px', color: 'var(--ink)' }}>
          Drop a study here, or click to browse
        </div>
        <div style={{ fontSize: '13.5px', color: 'var(--muted)', marginTop: '6px' }}>
          DICOM (.dcm), PNG or JPG · chest X-ray
        </div>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: '7px', marginTop: '16px',
          fontSize: '12px', color: 'var(--teal-2)', background: 'var(--teal-tint)',
          padding: '6px 12px', borderRadius: '99px', fontWeight: 600,
        }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          Use only de-identified images — no PHI
        </div>
      </div>

      {/* What happens to your data ------------------------------------------- */}
      <div style={{
        marginTop: '18px', background: 'var(--surface-2)', border: '1px solid var(--border)',
        borderRadius: '14px', padding: '16px 18px',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: '9px',
          fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: '14px', color: 'var(--ink)',
        }}>
          <span style={{
            width: '28px', height: '28px', flex: 'none', borderRadius: '8px', display: 'grid',
            placeItems: 'center', background: 'var(--teal-tint)', color: 'var(--teal-2)',
          }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </span>
          What happens to this study
        </div>
        <ul style={{ margin: '10px 0 0', paddingLeft: '18px', color: 'var(--muted)', fontSize: '12.5px', lineHeight: 1.7 }}>
          <li>The image is processed <strong style={{ color: 'var(--ink-2)' }}>in memory</strong> for de-identification — DICOM metadata is stripped and burned-in corner markers are masked before analysis.</li>
          <li>Any patient identifiers you type below stay in <strong style={{ color: 'var(--ink-2)' }}>your browser only</strong> (session storage) and are never sent to the server.</li>
          <li>Analysis is decision-support only. The model reads chest X-rays and abstains on non-chest or out-of-distribution input.</li>
        </ul>
      </div>

      {/* Upload queue -------------------------------------------------------- */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '28px' }}>
        <div style={{ fontFamily: 'var(--font-head)', fontWeight: 600, fontSize: '16px', color: 'var(--ink)' }}>
          Upload queue
        </div>
        {picked && (
          <button
            type="button"
            onClick={() => { setPicked(null); setStatus(null); setErrMsg('') }}
            style={{ fontSize: '13px', fontWeight: 600, color: 'var(--muted)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
          >
            Clear
          </button>
        )}
      </div>

      <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {!picked && (
          <div style={{
            background: 'var(--surface)', border: '1px dashed var(--border-2)', borderRadius: '14px',
            padding: '22px 17px', textAlign: 'center', color: 'var(--faint)', fontSize: '13px',
          }}>
            No studies yet — drop or browse above to begin.
          </div>
        )}
        {picked && (
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '14px',
            padding: '15px 17px', boxShadow: 'var(--shadow-sm)', display: 'flex', alignItems: 'center', gap: '14px',
          }}>
            <span style={{
              width: '40px', height: '40px', flex: 'none', borderRadius: '10px', display: 'grid',
              placeItems: 'center', background: 'var(--primary-tint)', color: 'var(--primary)',
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <path d="M14 2v6h6" />
              </svg>
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--ink)', fontFamily: 'var(--font-mono)' }}>
                  {picked.name}
                </span>
                <span style={{
                  fontSize: '11px', fontWeight: 700, padding: '2px 8px', borderRadius: '99px',
                  background: status === 'error' ? 'var(--danger-tint)' : 'var(--primary-tint)',
                  color: status === 'error' ? 'var(--danger)' : 'var(--primary)',
                }}>
                  {status === 'error' ? 'Not analysed' : 'Analysing…'}
                </span>
              </div>
              <div style={{ fontSize: '12.5px', color: 'var(--muted)', marginTop: '3px' }}>
                {picked.modality} · {fmtSize(picked.size)} · de-identified in memory
              </div>
              {status === 'error' ? (
                <div role="alert" style={{ fontSize: '12.5px', color: 'var(--danger)', marginTop: '9px', lineHeight: 1.5 }}>
                  {errMsg} Pick another study to try again.
                </div>
              ) : (
                <div style={{ height: '5px', borderRadius: '99px', background: 'var(--surface-3)', marginTop: '9px', overflow: 'hidden' }}>
                  <div className="upload-indeterminate" />
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Optional client-only patient identifiers (reused component) ---------- */}
      <div style={{ marginTop: '28px' }}>
        <PatientIntake patient={patient} onChange={setPatient} />
      </div>

      {onNav && (
        <div style={{ marginTop: '18px' }}>
          <button
            type="button"
            onClick={() => onNav('app')}
            style={{
              fontSize: '13px', fontWeight: 600, color: 'var(--muted)', background: 'none',
              border: 'none', cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            ← Back to workspace
          </button>
        </div>
      )}
    </div>
  )
}
