import { useRef, useState } from 'react'

function DropZone({ label, sub, onFile, busy, done, disabled }) {
  const inputRef = useRef(null)
  const [drag, setDrag] = useState(false)

  function handleFiles(files) {
    if (disabled) return
    if (files && files[0]) onFile(files[0])
  }

  function open() {
    if (!disabled) inputRef.current?.click()
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={label}
      aria-disabled={disabled}
      className={`dropzone ${drag ? 'drag' : ''} ${done ? 'done' : ''} ${disabled ? 'disabled' : ''}`}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDrag(true) }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); handleFiles(e.dataTransfer.files) }}
      onClick={open}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() } }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".png,.jpg,.jpeg,.dcm,.dicom,image/png,image/jpeg"
        hidden
        onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }}
      />
      <div className="dz-label">{busy ? 'Analyzing…' : label}</div>
      <div className="dz-sub">{done ? 'Uploaded ✓ — drop another to replace' : sub}</div>
    </div>
  )
}

export default function UploadPanel({ onUpload, onPriorUpload, onClear, onClearPrior, busySlot, hasPrior, hasCurrent }) {
  const anyBusy = busySlot !== null
  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <h3>Upload study</h3>
        {hasCurrent && onClear && (
          <button type="button" className="btn btn-small" onClick={onClear} disabled={anyBusy}
            title="Clear the current study and its report, then upload a fresh image">
            ✕ Clear &amp; upload fresh
          </button>
        )}
      </div>
      <div className="dz-row">
        <DropZone
          label="Current chest X-ray"
          sub="PNG, JPG, or DICOM (.dcm) — drop or click"
          onFile={onUpload}
          busy={busySlot === 'current'}
          done={hasCurrent}
          disabled={anyBusy}
        />
        <DropZone
          label="Prior study (optional)"
          sub="For interval comparison"
          onFile={onPriorUpload}
          busy={busySlot === 'prior'}
          done={hasPrior}
          disabled={anyBusy}
        />
      </div>
      {hasPrior && onClearPrior && (
        <button type="button" className="btn btn-small" onClick={onClearPrior} disabled={anyBusy}
          style={{ marginTop: 8 }} title="Remove the prior study from the comparison">
          ✕ Clear prior study
        </button>
      )}
      <p className="muted small" style={{ marginTop: 10 }}>
        Use only public or de-identified images. Do not upload identifiable patient data.
      </p>
    </div>
  )
}
