# RadAssist — CT Experience UI Design Document

*High-level, buildable specification synthesized from the five CT research streams (Core-UX, Measurement, AI-Assist, Regional Workflows, Safety). Grounded in the current stack: `backend/app/services/dicom_utils.py` (`CT_PRESETS`, `render_view`, `_deidentify`, `_capture_view_meta`), `backend/app/routers/viewer.py` (`/api/dicom-view`, `VIEWER_DISCLAIMER`), `frontend/src/components/DicomViewer.jsx`, `backend/app/config.py`, `backend/app/auth.py`, `backend/app/security.py`.*

---

## 0. The organizing principle (read first — this governs every section)

**CT & MRI stay a viewer. AI, if ever added, describes anatomy — never disease.** Every layout decision, every disclaimer string, and every API schema below exists to make that boundary *structural* (enforced in code and schema), not cosmetic.

Two architectural facts drive the entire document:

1. **Today the pipeline server-bakes PNGs.** `render_view` decodes the series, computes true HU (`raw*slope + intercept`), windows to **8-bit**, downscales to `VIEW_MAX_EDGE` (1024), flattens to PNG, and **discards the HU volume**. The client only ever receives *slice image URLs* — never HU values, never a 3-D volume. Consequences: the current "WL drag" (`filter: brightness/contrast`) is a **display trick on an 8-bit raster, not real windowing**; changing a preset forces a **full re-upload + re-render round-trip**; and MPR/MIP/crosshair/HU-ROI are **all impossible from current server state**.

2. **The single highest-leverage change — the "[VOLUME PIVOT]" — is to deliver the volume, not baked PNGs.** Persist one **int16 HU volume per `view_id`** (ordered, in-plane downscaled, slice-count capped; ~256×256×200 int16 ≈ 26 MB) and ship it to the client once as a typed-array blob. Windowing then becomes a client-side **LUT over an `Int16Array`**; reslicing becomes an **array transpose**. Both are trivially CPU/free-tier friendly. This one move unlocks live WL drag, MPR, MIP/MinIP, crosshair localizer, HU probe, and HU-ROI — the entire "needs volume" tier.

**Buildability legend used throughout:**
- **NOW** — works on the current PNG-delivery pipeline, mostly client-side, no/tiny backend change.
- **VOLUME** — requires the [VOLUME PIVOT] (still CPU/free-tier friendly).
- **FUTURE** — heavier compute, per-weights license verification, or clinical validation burden.

**Three bugs to fix regardless of phase:**
- **B1 — Fake WL drag.** The current brightness/contrast filter is not windowing. Call it out; replace it via the pivot.
- **B2 — Series-grouping vs de-ID UID regeneration.** `_deidentify()` *regenerates* `SeriesInstanceUID`/`StudyInstanceUID`. Any series grouping must key off the **original** UID captured **before** the scrub (or a salted hash of it). This is a latent data-corruption bug for study navigation.
- **B3 — Downscale-spacing mismatch.** Slices are downscaled to 1024 px, but the API returns the *original* `PixelSpacing`. The client multiplies downscaled-pixel distances by original mm/px, **under-reporting every distance/area** on any raster wider than 1024 (large recons/scouts). 512×512 is unaffected. Fix: return `render_scale` (or effective spacing). Every mm/mm²/mm³ tool depends on this.

---

## 1. Overall layout & panels

A four-region clinical viewer. AI is a **separate, opt-in channel** — never merged into the primary viewport by default.

```
┌─ TOP BAR ────────────────────────────────────────────────────────────────────┐
│ RadAssist · CT/MRI VIEWER (no diagnosis)   [Modality: CT] [Suitability ✓/⚠]    │
│                                            [user ▾ · idle 12:41 · Logout] [Audit▸]│
├─ SAFETY STRIP (always visible) ───────────────────────────────────────────────┤
│ ⓘ Image viewer only — no AI diagnosis.   De-ID: 14 removed · UIDs regen        │
│ ⚠ Burned-in text: UNKNOWN — not removed          [Secondary-capture hidden]    │
├──────────────┬──────────────────────────────────────────────┬─────────────────┤
│ LEFT RAIL    │            CENTER VIEWPORT                     │  RIGHT RAIL      │
│ Series/study │   ┌────────────┬────────────┐                 │  (tabbed)        │
│ navigator    │   │  Axial     │  Coronal   │  layout:         │  • Display       │
│ • thumbnails │   ├────────────┼────────────┤  1×1 / 2×2 /     │  • Structures(AI)│
│ • modality   │   │  Sagittal  │  MIP / 3D  │  phase-linked    │  • Measure       │
│ • #slices    │   └────────────┴────────────┘                 │  • Annotate      │
│ • auto-label │   Overlays: masks · calipers · scout lines ·   │  • Info / Audit  │
│   chip       │             cursor HU readout                  │                  │
│ • QC flags   │   TOOL RAIL: Probe·Distance·Angle·ROI·Arrow·Text│                  │
├──────────────┴──────────────────────────────────────────────┴─────────────────┤
│ BOTTOM: cine ◀▮▶  slice 42/80  spacing 0.6×0.6mm  cursor HU: -12 (calibrated✓) │
│ WL40/WW80 (brain)  zoom/pan                                                     │
├────────────────────────────────────────────────────────────────────────────────┤
│ PERSISTENT DISCLAIMER: Not a medical device; not for diagnostic use…            │
└────────────────────────────────────────────────────────────────────────────────┘
```

**Panel responsibilities:**

- **Top bar** — de-identified study context; **Modality badge** (CT vs MR — gates whether HU presets apply); **Suitability chip** (green ✓ / amber ⚠ with reason) that *gates whether AI actions are enabled*; user/idle/logout; Audit drawer button.
- **Safety strip** — persistent, non-dismissible. De-ID identifier count + UID-regen note; burned-in-text state (`YES`/`NO`/`UNKNOWN`/`LIKELY`); secondary-capture-hidden note. (Extends the red burned-in warning already at `DicomViewer.jsx` ~lines 118–123.)
- **Left rail — series/study navigator** — thumbnails grouped by **SeriesInstanceUID** (see B2), each showing modality, slice count, an **auto-label chip** (heuristic: "Axial CT abdomen," "MR T2 FLAIR" — tagged "auto — verify"), and **QC flags** ("localizer — AI disabled," "gap in slices," "burned-in text," "dose/secondary-capture — hidden").
- **Center viewport** — single-pane now; **MPR grid (axial/coronal/sagittal)** + optional MIP/3D pane at the VOLUME tier. Layout selector (1×1 / 2×2 / 2×1 / phase-linked). Overlay layers, all toggleable and independent of the raster: segmentation masks, calipers/ROIs (SVG), scout/reference lines, cursor HU HUD. **Tool rail** (radio semantics, one active tool) replacing today's single "Caliper on/off" toggle.
- **Right rail — tabbed:** *Display* (WL/WW + presets + suggested-window chip), *Structures (AI)* (segmentation, default off), *Measure* (caliper/ROI list + HU-stats table + export), *Annotate* (key images, arrows, text), *Info/Audit* (de-ID tags, QC report, AI provenance trail).

**One required refactor to enable all of the above:** move rendering from `<img>` to a **`<canvas>`** with a stacked **SVG overlay** for annotations. This is the natural home for the client-side LUT (windowing), zoom/pan/rotate compositing, key-image capture, and crisp, hit-testable, draggable measurement handles. Store all measurement geometry in **original-raster px**, rendered through the existing `naturalWidth/naturalHeight ↔ display` transform.

---

## 2. Full feature list (grouped by buildability)

### 2A. BUILDABLE NOW (client-side / tiny backend change)

**Display & navigation**
- ★ Windowing presets (CT, HU) — the nine in `CT_PRESETS` already exist: brain 40/80, stroke 35/30, subdural 75/215, bone 600/2800, skeletal 400/1800, lung −600/1500, mediastinum 50/350, liver 30/150, angio 200/700. **Add two dict entries now:** `abdomen` soft-tissue (~40/400) so "soft tissue" isn't overloaded onto `mediastinum`, and a distinct PE/venous angio window. Plus a user-editable custom WL/WW field. (Note: preset switching is still a server round-trip until the pivot — acceptable for presets, not for drag.)
- ★ Slice navigation — scroll-wheel, arrow keys, scrub slider, prev/next (already in `DicomViewer.jsx`).
- ○ Cine play/pause + fps + loop/bounce (`requestAnimationFrame` over `slice_urls`); slice %/position indicator; neighbor-slice prefetch.
- ○ Zoom / pan / rotate90 / flip H-V / grayscale invert / fit / 1:1 / reset — all CSS `transform` + `filter: invert(1)` on the canvas. (MONOCHROME1 is already inverted server-side; expose a *user* toggle on top.)
- ○ Series & study navigator + manual layout presets (1×1 / 2×2 / 2×1). **Backend change:** group uploaded files by SeriesInstanceUID — **mind B2** (group before de-ID).
- ○ Region auto-chip from `BodyPartExamined` + suggested hanging-protocol/window (metadata already returned by `_capture_view_meta`).
- ○ Multi-window **server re-render** side-by-side (N calls to existing endpoint — chattier but works now; the pivot removes the round-trip).
- ○ Key-image capture — composited `canvas.toBlob()` with burned-in scale bar + orientation label. Carries the burned-in-PHI warning and the "not a medical device" provenance stamp. No AI, no diagnostic labeling on captures.
- ○ Secondary-capture / dose-report / scout **quarantine** (refuse to render — see §5).

**Measurement — geometry-only (no pixel values needed)**
- ○ Linear distance (electronic ruler) — anisotropic-correct `hypot(dx·col, dy·row)`; px fallback with "uncalibrated" badge. (Upgrade the existing 2-point caliper to persistent, multiple, draggable, per-slice.)
- ○ Angle / Cobb — 3-point and 4-point modes; convert endpoints to mm first when pixels are anisotropic.
- ○ Arrows / text annotations — pure vector overlay, session/export only, **never** burned into stored PNGs, **never** persisted server-side (PHI re-introduction risk).

### 2B. NEEDS VOLUME RECONSTRUCTION ([VOLUME PIVOT] — still CPU/free-tier)

- **True live WL drag** — int16 HU + canvas LUT `out = clamp((hu − (WL − WW/2)) / WW × 255)` on `pointermove`. Instant, correct, no round-trip. Fixes B1. *Recommended first VOLUME deliverable — cheapest, highest daily value.*
- **MPR (axial / coronal / sagittal)** — resample to an isotropic int16 volume once; cardinal planes are `vol[:,y,:]` / `vol[:,:,x]` transposes + 1-D anisotropy rescale, resliced client-side in single-digit ms. Label reformats "reconstructed, reduced resolution" (through-plane res = slice thickness).
- **MIP / MinIP / mean thick-slab** — `reduce(max|min|mean)` over a slab of the `Int16Array`, windowed with the same LUT; slab-thickness slider (3–50 mm). Combine with MPR so any plane supports slabbing.
- **Crosshair / reference-line localizer** — all panes index the same voxel `(x,y,z)`; pixel→voxel on click, shared state, every pane reslices + overlays its two reference lines. Pure client-side once the volume ships.
- **Cursor HU probe** — fetch current slice's int16 array once on slice-change; read under cursor on `pointermove`. CT → HU; MR → a.u. ("not quantitative, sequence/scanner-dependent").
- **HU ROI — circle / rect / freehand** (mean / SD / min / max / area) — boolean mask over `hu[mask]`; area = n_px · spacing_row · spacing_col. Cleanest as server endpoint `POST /api/dicom-measure` reusing the persisted int16 slice (small payloads, trivial CPU). Because it reads 16-bit data (not the 8-bit PNG), the precision-loss disclaimer does **not** apply — a genuine quality win over the current caliper.
- **Multiphase linked scroll + registration** (abdomen) — SimpleITK (Apache-2.0), position-synced non-contrast/arterial/portal-venous/delayed; shared ROI reads HU-per-phase.

### 2C. FUTURE (heavier compute / license verification / validation)

- Oblique / double-oblique / curved-planar (vessel straightening) — needs interpolation along arbitrary vectors + centerline tool.
- Full-volume rotating 3-D MIP / volume rendering — WebGL ray-casting.
- Cross-*series* / scout localization in true DICOM patient coordinates (`ImageOrientationPatient`/`ImagePositionPatient`) — needs full world-geometry retention.
- Auto hanging protocols by body part / window / plane — rule-based doable; robust version is where a heuristic/AI classifier assists.
- Volume estimation (planimetry Σ area·z-spacing, or thresholded voxel count) — HU plane + multi-slice orchestration + partial-volume/threshold UX; frame as "estimated volume of thresholded/outlined voxels," never "tumor volume."
- ROI-across-slices profile (HU vs slice sparkline) — HU plane + slice-range loop.
- GSPS / DICOM-SEG / DICOM-SR export of measurements (highdicom, MIT).
- Interactive click-to-segment (MedSAM/MobileSAM single-slice) — encoder caching + overlay UX.
- Anatomical organ/vessel/bone segmentation + volumetry (TotalSegmentator) — see §3.

---

## 3. The honest AI-assist layer (license-clean, non-diagnostic)

### 3.1 The regulatory bright line (why this is structural)

| Tier | Output | RadAssist stance |
|---|---|---|
| **Viewer / measurement** | Renders pixels, windowing, MPR, calipers, HU ROI. No disease claim. | **SHIP — this is the whole CT/MRI MVP.** |
| **CADe (detection)** | Marks candidate abnormality locations ("look here"). | **DO NOT SHIP as a claim.** Regulated device (21 CFR 892.2070). |
| **CADx (diagnosis)** | Characterizes disease / probability / malignancy. | **NEVER in MVP.** Highest regulatory bar. |

The FDA CDS final guidance (Sept 2022) + 21st Century Cures §3060: software that **acquires, processes, or analyzes a medical image** is a device and is **not** eligible for the non-device CDS carve-out. There is no decision-support escape hatch for image-analysis-for-pathology. Therefore: **any AI that reads CT/MR pixels to assert a finding is a device.** What stays defensible is **anatomy labeling, measurement assistance, and metadata classification** — framed as non-diagnostic research/education tooling, human-confirmed.

### 3.2 The models — what may ship, exactly

**Anchor: TotalSegmentator v2 — code Apache-2.0. Weight license is per-subtask (this is the critical nuance).**

- **SHIP (Apache-2.0, commercial-clean):** `total` (117 CT classes), `total_mr`, `body`/`body_mr`, `lung_vessels`, `liver_vessels`, `liver_segments`(`_mr`), `vertebrae_mr`, `cerebral_bleed`*, `hip_implant`, `pleural_pericard_effusion`, `lung_nodules`*, `kidney_cysts`, `liver_lesions`*, `breasts`, `head_glands_cavities`, `head_muscles`, `headneck_bones_vessels`, `trunk_cavities`, `ventricle_parts`, and the other head/craniofacial Apache tasks.
- **DO NOT SHIP (non-commercial / restricted weights):** `brain_aneurysm` (CC BY-NC 4.0, no commercial license offered at all), `tissue_types`/`tissue_types_mr`/`tissue_4_types` (rules out L3 body-composition via this route), `heartchambers_highres`, `coronary_arteries`, `aortic_sinuses`, `appendicular_bones`(`_mr`), `brain_structures`, `vertebrae_body`/`vertebrae_pp`, `face`(`_mr`), `thigh_shoulder_muscles`(`_mr`). **Enforce with a config whitelist constant** so restricted subtasks can never be invoked.
- **\* Trap tasks:** `lung_nodules`, `liver_lesions`, `cerebral_bleed` are Apache-clean *segmentation labels* — render **only** as "model-labeled candidate region, unvalidated, requires radiologist confirmation." Never as detection with implied sensitivity/specificity, never "bleed detected."
- **Dataset licenses** (CT CC BY 4.0; MR CC BY-NC-SA 2.0) matter only if you **retrain/redistribute training data** — not for using released weights.
- **CPU feasibility:** full-res `total` on chest-abdomen CT is slow on CPU (minutes, few GB RAM). Make it free-tier viable with `--fast` (3 mm), `--roi_subset <organs>`, `--ml` (single multilabel output). Run **async, concurrency 1, cache per series hash**. Built-in `--statistics` emits **volume (mL) + mean HU per ROI** for free — this is the measurement-automation engine.

**Supporting, license-clean:** nnU-Net v2 (Apache-2.0, only if you train your own), MONAI Core (Apache-2.0, use as preprocessing/inference utility layer; **Model-Zoo bundles are per-bundle license-vetted — never assume clean**), MedSAM/MobileSAM/SAM-Med2D (Apache-2.0, user-directed single-slice contouring only), highdicom (MIT, SEG/SR export), pydicom/SimpleITK/ITK/nibabel/scikit-image/numpy (permissive).

**No ML needed (buildable now):** suggested display window (honor DICOM VOI LUT → named presets → percentile fallback); input-suitability/QC gate (rules on `Modality`, `RescaleSlope/Intercept`, air≈−1000/water≈0 sanity, `ImageType` LOCALIZER/DOSE, slice-gap detection); series/sequence/body-part labeling (metadata heuristics on `BodyPartExamined`, `SeriesDescription`, `ScanningSequence`, `TE`/`TR`).

### 3.3 Exact framing & disclaimers

**Allowed claims:** "anatomical structure labeling," "organ segmentation (model-generated, radiologist-reviewable)," "automated measurement of a labeled region," "suggested display window," "series/body-part label," "input suitability check." Every output editable, overridable, human-confirmed.

**MUST NOT be claimed:** "tumor/nodule/mass/cancer detected," "malignant/benign," "suspicious for," "hemorrhage/stroke/infarct/bleed detected" (even though `cerebral_bleed` exists — it is a region label, not a validated detector), "fracture," "PE," "dissection/aneurysm present," "fatty liver/cirrhosis/splenomegaly," "normal study / no abnormality / nothing to report" (absence claims are diagnostic too), any accuracy/precision number without your own validation study, "FDA cleared / CE marked / medical device."

**Lexicon substitution table** (bake into copy, schema field names, and code review):

| Forbidden | Required |
|---|---|
| detected / found / positive for | *region computed by the model* / *candidate anatomy* |
| lesion / tumor / bleed / mass | *area of model attention* / *segmented region* |
| diagnosis / impression / finding | *anatomy label (auto — verify)* / *measurement* |
| 72% malignant | *approximate — reviewer must confirm* (no disease %) |
| normal / no abnormality | *no analysis performed* (viewer) |

**Schema taboo (enforced at the API):** `/api/segment` returns `regions[] = {label, volume_ml, color, method, model, license, timestamp}` — **no** field named or shaped like `finding`, `probability`, `impression`, `severity`, `malignancy`, `abnormal`, `diagnosis`. A code-review checklist item blocks any such field. `viewer.py` already enforces this for the viewer path.

**Disclaimer strings:**
- **Persistent viewer (keep verbatim, already deployed):** `VIEWER_DISCLAIMER` — "Image viewer only — NO AI analysis is performed on this modality… Not a medical device; not for diagnostic use. Windowing presets are starting points; 8-bit rendering loses precision; burned-in pixel text (if any) is not removed."
- **AI overlay (only when a Tier-1 overlay is toggled on):** "AI anatomy overlay — computed organ regions, **not a diagnosis**. These outlines label anatomy only; they do not detect, characterize, or exclude any disease, injury, or abnormality. Approximate and frequently wrong at boundaries — a qualified reader must verify every region before any use. Research/education prototype; not FDA-cleared, not CE-marked, not a medical device."
- **Microcopy:** overlay toggle `Anatomy overlay (AI) — approximate, verify`; caption `Computed region · not a finding`; volumetry `≈ 1,240 mL (auto — confirm)`; first-use hover `This does not look for disease.`

**Eight hard UI rules so AI can never read as diagnosis:** (1) separate opt-in rail, off by default; (2) schema taboo enforced at API; (3) anatomy words only (organ names, never pathology nouns); (4) no disease confidence — any confidence shown is *segmentation coverage*, never % disease, no red/green alarm semantics (colors encode organ identity); (5) provenance on every element (model + version + license + "computed region · not a finding"); (6) human-in-the-loop, non-authoritative — AI **cannot** auto-populate a report line or set a "finding," no "accept AI diagnosis" affordance exists; (7) persistent boundary banner while overlay is on; (8) distinct visual language — translucent organ fills / dashed contours in a labeled legend, deliberately unlike a CADe "hot spot" marker.

**MR:** treat AI as FUTURE (fewer license-clean CPU options). Keep MR to viewer + coded-tag `sequence_label` ("auto — verify"). **Never apply CT HU presets to MR** (the code already forbids this).

---

## 4. Measurement & reporting UX

### 4.1 The correctness guardrail that splits the toolset

**HU-quantitative tools must read the int16 HU array, never the 8-bit windowed PNG.** Windowing clips and quantizes — measuring the PNG would make "mean HU" depend on the chosen preset, silently wrong. This is the single most important measurement guardrail. Geometry tools (distance, angle, arrows, text) need only `PixelSpacing` + screen coordinates and ship now; every HU tool is gated on the [VOLUME PIVOT].

### 4.2 UI structure (four additions to the stage)

1. **Tool rail** — single-active-tool radio: Probe · Distance · Angle/Cobb · ROI (circle/rect/freehand submenu) · Arrow · Text · Volume.
2. **SVG overlay layer** stacked above the canvas — crisp, hit-testable, draggable handles, independent of pixels. Geometry stored in original-raster px; keyed to a **slice index** (drawn only when that slice is current; optional "pin to all slices").
3. **Readout HUD** (stage corner) — live cursor HU/a.u., WL/WW, slice i/N, effective spacing, zoom.
4. **Measurements panel** (right rail) — one row per item: type, value+unit, slice #, color swatch, visibility toggle, delete. Turns one-shot calipers into a persistent, reviewable set.

**Provenance chips on every result (the honesty surface):** unit (`HU` vs `a.u.`), calibration (`mm` vs `px — uncalibrated`), source (`measured from 16-bit data`). Measurement is explicitly **not AI** — an electronic ruler + region statistics, categorically different from the inference gate.

### 4.3 Per-tool buildability

| Tool | Data | Tier | Backend change |
|---|---|---|---|
| Calibrated spacing/thickness | PixelSpacing, SliceThickness, SpacingBetweenSlices | NOW (fix B3) | tiny (`render_scale`) |
| Linear distance | PixelSpacing (row+col) | NOW | none |
| Angle / Cobb | PixelSpacing (if anisotropic) | NOW | none |
| Arrows / text | none | NOW | none (client/export only) |
| Cursor HU/a.u. probe | Slope, Intercept | VOLUME (low) | persist + serve int16 HU |
| HU ROI circle/rect/freehand | Slope, Intercept, PixelSpacing | VOLUME (low) | HU plane + `/dicom-measure` |
| ROI across slices | Slope, Intercept, PixelSpacing | VOLUME/FUTURE | HU plane + slice loop |
| Volume estimation | spacing + z + (slope/intercept) | FUTURE | planimetry/threshold + partial-volume UX |
| SEG/SR export | — | FUTURE | serializer (highdicom) |
| AI auto-ROI/organ volumetry | — | FUTURE (license-clean only) | TotalSegmentator |

For z-metrics, prefer `SpacingBetweenSlices` (accounts for gap/overlap); fall back to `SliceThickness` **with a warning** when they differ or the former is absent. Surface anisotropy (row≠col) as a badge. Show an explicit "uncalibrated — px only" state when `PixelSpacing` is `None`.

### 4.4 Structured reporting UX (region-driven drawer, human authors the impression)

A report drawer (state S6) pre-fills **measurements only**; the reader authors every interpretation. **No AI output ever auto-populates a report line.** Region fields (from the workflow research):
- **Head/neuro:** adequacy/motion; hemorrhage present? (author) + location (intra-axial/SDH/EDH/SAH/IVH) + max thickness (mm, caliper); midline shift (mm); mass effect; hydrocephalus; grey-white differentiation; ASPECTS checklist (author); impression (free text).
- **Chest:** technique/phase; per-nodule table (lobe, long×short mm, solid/part-solid/GGO, Fleischner interval — author-selected, *assisted* by auto-measured size); PE present? central/lobar/segmental (author) + RV:LV (mm); nodes (station, short-axis mm); pleura; impression.
- **Abdomen/liver:** phases acquired; lesion table (Couinaud segment, size mm, HU per phase NC/A/PV/delayed from a **shared synced ROI**, enhancement pattern — author); organ volumes (from segmentation if run); impression. **No LI-RADS auto-category, no "HCC."**
- **Spine/bone:** Cobb angle (°, auto from tool); listhesis (mm); level-by-level vertebral height loss %; canal/foraminal dims (mm); level confirmed against optional auto vertebral labels; impression.

Export: CSV / DICOM SR (highdicom) — FUTURE. Key images (PNG) — NOW.

---

## 5. Safety / de-ID / audit UX

### 5.1 De-identification — what exists and the honest gaps

**Exists today** (`_deidentify`, `render_view`): scrubs direct identifiers + free-text descriptors; regenerates Study/Series/SOP UIDs; removes all private tags; runs per-file across the whole series; flags burned-in text passively via `BurnedInAnnotation` → `YES|NO|UNKNOWN` (red UI warning).

**CT/MRI-specific gaps — surface honestly, and they are the roadmap:**

1. **Burned-in pixel PHI is the #1 CT risk and is NOT removed.** Dose-report / "Patient Protocol" secondary-capture series are screenshots saturated with name/MRN/DOB/accession; scout/localizer images carry a burned-in banner; 3-D SC series overlay demographics. `BurnedInAnnotation` is often absent or lies — the `UNKNOWN` default is honest and correct.
   - **NOW (Phase-2):** **Quarantine rule** — detect `Modality == "SC"`, Secondary-Capture SOP class, `ImageType` containing `SECONDARY`/`DERIVED`/`DOSE`, or a pre-scrub `SeriesDescription` matching `dose|protocol|screen|report`, and **refuse to render** ("Dose/secondary-capture series hidden — high burned-in PHI risk"). **Active margin scan** — reuse the existing bright-glyph-in-margin heuristic (`MARKER_*` in `config.py`) on corner bands; upgrade `burned_in` `UNKNOWN → LIKELY` and optionally black-box the margin before serving. (Tesseract is Apache-2.0 but heavy; the glyph heuristic is the free-tier first pass.)
2. **Dates & ages** (`StudyDate`, `SeriesDate/AcquisitionDate/ContentDate`, `*Time`, `PatientAge`, `AcquisitionDateTime`) are HIPAA quasi-identifiers. **NOW:** add to `_IDENTIFIER_KEYWORDS`, or consistent date-shifting (per-study random offset preserving intervals). For MVP demo, deletion is simpler and safer.
3. **DICOM SR / encapsulated dose objects** carry text PHI outside the pixel path. **NOW:** refuse non-image SOP classes explicitly and log it.
4. **Overlay planes (60xx groups)** can hold burned-in annotation bitmaps. **NOW:** strip `0x60000000–0x60FFFFFF` alongside private tags.
5. **Provenance stamping (PS3.15).** After scrub set `PatientIdentityRemoved (0012,0062) = YES` and `DeidentificationMethod (0012,0063) = "RadAssist basic profile subset"`. **NOW, trivial.**
6. **Honesty statement:** "De-identification is a **subset** of the DICOM PS3.15 Basic Application Confidentiality Profile — direct identifiers, descriptors, private tags, and UIDs are removed in memory; burned-in pixel text and some quasi-identifiers may remain. Not a certified de-identification pipeline."

**De-ID status strip (top of viewer):** `De-ID: 14 identifiers removed · UIDs regenerated · private tags stripped` + when relevant the red `⚠ Burned-in text: LIKELY/UNKNOWN — not removed` bar + "secondary-capture series hidden" note.

### 5.2 Audit trail & auto-logoff (HIPAA §164.312)

| Requirement | Current | Gap → NOW |
|---|---|---|
| Unique user ID (a)(2)(i) | per-user login (`AUTH_USERS`) | OK (demo-grade) |
| Authentication (d) | HMAC-signed session cookie | OK; honest note "unsalted SHA-256, no IdP — demo auth" |
| **Auto logoff (a)(2)(iii)** | `SESSION_TTL_SECONDS` (12h absolute) | **Gap:** add idle timeout (10–15 min): client idle timer + "logging out in 60s" modal + sliding refresh; drop absolute TTL to a few hours |
| **Audit controls (b)** | none | **Gap:** append-only PHI-free JSONL `{ts, user, action, view_id, modality, n_slices, ip_hash}` for login/logout/view/segment/export |
| Integrity (c) | UID regen, only PNGs persisted, TTL-purged | State it |
| Transmission (e) | HTTPS/HSTS/secure cookie/CSP (`security.py`) | OK |

**NOW, dependency-free:** `services/audit.py` (thread-safe append-only JSONL, PHI-free by schema, private non-served dir mirroring `ANALYSIS_DIR`) wired into `dicom_view` + auth router; `useIdleLogout(minutes)` React hook + warn modal. Honesty caveat: "Single-container demo audit log; not tamper-evident or centrally retained."

### 5.3 8-bit rendering honesty (CT-specific)

State on the CT panel: "Rendered 8-bit for display; not full-fidelity diagnostic 12–16-bit data. Do not measure subtle HU differences off the displayed image." (ROI-HU computes on the stored HU array — §4.1.)

---

## 6. Phased build plan

### PHASE 1 — SHIP NOW on the current CPU stack (model-free, non-device viewer)

*Buildable immediately; a developer can start today. No volume, no models.*

**Frontend (`DicomViewer.jsx` → split into `ViewerStage`, `SeriesNavigator`, `WindowPresets`, `MeasurementTools`, `SafetyStrip`):**
1. **Canvas refactor** — move rendering `<img>` → `<canvas>` + stacked SVG overlay. Gate for everything else.
2. Zoom / pan / rotate90 / flip / invert / fit / reset (CSS transforms + `filter: invert`).
3. Cine play/pause + fps + loop/bounce + slice-% indicator + neighbor prefetch.
4. Tool rail (radio) + persistent measurements panel + provenance chips. Geometry tools now: **linear distance, angle/Cobb, arrows, text** (client/export only).
5. Key-image capture (`canvas.toBlob()` with scale bar + orientation + burned-in warning + provenance stamp).
6. `useIdleLogout(minutes)` hook + warn modal.
7. Safety strip: extend burned-in states; de-ID count badge; secondary-capture-hidden note.

**Backend (keep `viewer.py` model-free):**
1. **Fix B3** — return `render_scale` (or effective spacing) from `render_view`; client converts mm correctly.
2. **Add presets** — `abdomen` (~40/400) + distinct PE/venous angio to `CT_PRESETS`; custom WL/WW field.
3. **Series grouping** by SeriesInstanceUID — **fix B2** (capture original UID / salted hash **before** `_deidentify`). Enables the study navigator + manual layouts.
4. **De-ID hardening:** extend `_IDENTIFIER_KEYWORDS` with date/age tags; strip 60xx overlay groups; **quarantine SC/dose/scout series** (config `QUARANTINE_SECONDARY_CAPTURE=1`); active bright-glyph margin scan → richer `burned_in` state; stamp `(0012,0062)/(0012,0063)`; refuse non-image SOP classes explicitly.
5. **`services/audit.py`** — append-only PHI-free JSONL; wire into `dicom_view` + auth router.
6. **Config flags** (`config.py`): `IDLE_LOGOUT_MINUTES`, `AUDIT_ENABLED`, `QUARANTINE_SECONDARY_CAPTURE=1`, new de-ID tag list. Add new routes to `PROTECTED_PREFIXES` + `RATE_LIMITED_PATHS`.
7. Region auto-chip + suggested window/hanging-protocol from `BodyPartExamined` (metadata already captured).

**Explicitly call out B1** in the UI/code: the current WL "drag" is a display filter, not windowing — label it and schedule its replacement for Phase 2.

**Phase-1 regulatory posture:** non-device viewer, "not for diagnostic use." Zero disease claims. Full utility: windowing, navigation, geometry measurement, series nav, de-ID hardening, audit, idle logoff, key images.

### PHASE 2 — [VOLUME PIVOT] (non-diagnostic, still CPU/free-tier)

Persist one **int16 HU volume per `view_id`** (ordered via existing `_slice_position` sort, in-plane downscaled, slice-capped); add `has_hu` (True for CT; MR stores raw intensity tagged a.u.) and TTL cleanup for the arrays. New endpoints: `GET /api/dicom-hu-slice/{view_id}/{idx}` (int16 binary for the live probe), `POST /api/dicom-measure` (ROI/across-slice stats). This one move unlocks, in order of value: **live WL drag** (fixes B1) → **cursor HU probe** → **HU ROI (circle/rect/freehand)** → **MPR (axial/coronal/sagittal)** → **MIP/MinIP/thick-slab** → **crosshair localizer** → **multiphase linked scroll + registration** (SimpleITK). All CPU/free-tier, all schema-clean geometry — no models. Structured-report drawer with measurement pre-fill lands here.

### PHASE 3 — Opt-in, non-diagnostic AI (likely optional-GPU, feature-flagged)

Behind `SEGMENT_ENABLED=0` default, auth-gated, async queue (concurrency 1, cache per series hash), slice/series capped like `VIEW_MAX_*`. `routers/segment.py` → `/api/segment` returning the **taboo-free schema** (`regions[]{label, volume_ml, color, method, model, license, timestamp}`). **TotalSegmentator Apache-2.0 whitelist only** (`--fast`/`--roi_subset`/`--ml`/`--statistics`), rendered in the separate "Anatomy overlay (AI)" rail, default off, with the C2 disclaimer + provenance footer + eight hard UI rules from §3.3. Powers organ/vessel/vertebra labeling + volumetry, MPR auto-centering, organ-based hanging, slab targeting, measurement assist. Sequence/phase classifier upgrade. Interactive click-to-segment (MedSAM/MobileSAM single-slice) as user-directed contouring. Per-bundle-vetted MONAI models. Framing: "anatomy, not a finding," human-confirmed.

### LATER — the device line (do NOT ship without validation)

Any ICH/bleed/PE/nodule presentation as "present/absent" is **CADe/CADx = a regulated device**. Segmentation of a labeled structure is more defensible than "bleed detected," but requires clinical validation, a behavior card (reuse the CXR `validation/` harness pattern), and legal review. **Off in the MVP.** Body-composition/L3 needs a clean model (TotalSegmentator `tissue_types` is non-commercial). Oblique/curved MPR, 3-D VR, DICOM SEG/SR round-trip, MONAI Label editing, cross-series world-coordinate localization.

---

### Bottom line
Phase 1 ships now: a hardened, honest, model-free CT/MRI DICOM viewer with real clinical utility (windowing, cine, geometry measurement, series navigation, de-ID hardening, audit, idle logoff, key images) and zero disease claims — plus the three bug fixes (B1 fake-WL callout, B2 pre-de-ID series grouping, B3 downscale-spacing). Phase 2 is one architectural move (persist the int16 HU volume the pipeline already computes and discards) that unlocks live windowing, MPR, MIP, crosshair, and true HU measurement. AI enters only in Phase 3, through a separate opt-in "anatomy overlay" channel — license-clean (Apache/MIT), schema-constrained so no `finding`/`probability`/`diagnosis` field can exist, captioned "computed region · not a diagnosis," human-confirmed. The instant an output asserts a pathology it becomes a regulated device and leaves MVP scope.