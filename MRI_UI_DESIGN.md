# RadAssist — MRI Viewer: High-Level UI Design Document

Synthesized from five MRI research streams (Core-UX, Measurement, AI-Assist, Clinical Workflows, Safety/Regulatory). Grounded in the existing model-free pipeline: `render_view` in `backend/app/services/dicom_utils.py`, `/api/dicom-view` in `backend/app/routers/viewer.py`, and `frontend/src/components/DicomViewer.jsx`. Same structure as the CT design; every MRI-specific divergence from CT is called out.

---

## 0. Framing invariants — the honesty contract every UI element must obey

MRI diverges from CT on two axes that shape the entire design: **intensity has no absolute scale**, and **the clinically useful unit of work is the multi-*series* study, not one flat stack.**

1. **No HU, no calibrated intensity — ever.** MR signal is scanner/coil/sequence/gain-dependent and arbitrary. The backend already gives MR a percentile window with `"unit": "a.u."` and refuses `CT_PRESETS` (`dicom_utils.py` L390–398); the frontend already shows "auto window (percentile, arbitrary units)" (`DicomViewer.jsx` L92). UI rule: no HU string, no CT preset buttons on MR (`presets: []`), no tissue-named presets ("fat"/"fluid") that imply calibration.
2. **Geometry is trustworthy; intensity is not.** The one honest quantitative readout MR can give is **distance/area in mm** when `PixelSpacing` is present. Keep the caliper; never extend that trust to a bare signal readout.
3. **The defensible MR measurement is a *ratio*.** Because the arbitrary scale cancels, signal-intensity ratio (SIR) or % change between two ROIs *in the same image* is the headline measurement — lead the UI toward ratios, not bare means.
4. **Sequence label is advisory and coded-only.** `_seq_label` reads only coded enums (`ScanningSequence`/`SequenceVariant` SE/GR/IR/EP…), never scrubbed free text. Always render as **"auto — verify."** No downstream logic (windowing, AI, tissue claims) may branch on the label with confidence.
5. **Free-text descriptors are scrubbed, not shown.** `_deidentify` deletes `SeriesDescription`/`ProtocolName`/`SequenceName`/`ImageComments` (techs type PHI there) — which is *why* the sequence hint is coded-only. Surface this in a tooltip so the terse "SE IR" label isn't read as a bug.
6. **Burned-in text is disclosed, never claimed clean.** `burned_in` stays YES/NO/UNKNOWN — especially relevant for MR secondary captures and derived maps (ADC/MIP) that burn in scale bars.
7. **The response carries nothing diagnosis-shaped.** `/api/dicom-view` deliberately omits any `finding`/`probability`/`impression` field. Any future MR AI preserves this: labeled overlay, never a scored finding.
8. **MR physical safety is explicitly out of scope.** This is a viewer of acquired DICOMs, not a scanner console. Show **no** MR-safe/conditional/unsafe, implant, SAR, or contrast-advisory indication — a one-line scope statement in the MR banner prevents that scope creep.

---

## 1. The architectural decisions that unlock most features

Two pure-engineering changes (no license or honesty risk) gate everything below.

**(A) Series grouping — the Phase 1 prerequisite.** Today `render_view` collapses *all* uploaded files into one `_slice_position`-sorted stack; `SeriesInstanceUID` is read only to regenerate it during de-ID. MR studies are inherently multi-series (T1/T2/FLAIR/DWI/ADC/T1C). **Bucket incoming files by `SeriesInstanceUID` (captured before de-ID regenerates it), classify each series, and return a `series[]` array** instead of a flat `slice_urls`. Every hanging protocol below is a layout over that array. This is the single highest-leverage task — without it, no multi-sequence workflow can render.

**(B) Raw-intensity transport — the Tier-2/Phase-2 pivot.** Today the server bakes an 8-bit windowed PNG per slice and the client approximates windowing with CSS brightness/contrast. That path *cannot* honestly support signal readout (a windowed PNG carries only 0–255 display values, clipped and window-dependent) or true WL/WW/invert. Pivot: **server decodes once, ships compact raw per-slice intensity; the browser does windowing/invert/zoom/pan/cursor-readout on a `<canvas>` LUT.** Ideal for the free tier — the client's machine does interactive work, so the CPU-only server goes idle after decode with no per-window round-trips (unlike CT's re-POST preset path).
- Transport: gzip'd `Uint16`/`Float32` blob per series + JSON manifest (geometry, TE, b-value, position). A 16-bit PNG will **not** survive `canvas.getImageData` (clamps to 8-bit) — use a raw typed-array blob or a hi/lo two-channel 8-bit pack unpacked in JS.
- Memory: reuse `VIEW_MAX_EDGE` downscale + slice cap. Worst case ~6 seq × 30 slices × 512² × 2 B ≈ 90 MB → lazy-load the active series (+ its DWI/ADC partner), evict the rest.
- Honesty preserved: raw values are acquired MR intensity → cursor readout labeled **a.u.**; the viewer response still contains no finding field; AI overlays arrive only via a separate, explicitly-labeled endpoint.

**Correctness fix that gates all measurement:** `render_view` downscales any slice with long edge > `VIEW_MAX_EDGE` (1024) but returns the *original* `PixelSpacing`. The frontend maps clicks to `naturalWidth` (downscaled) × original spacing → **mm is wrong by the downscale factor whenever downscaling fired.** Return `spacing_eff = spacing_orig × (orig_dim / rendered_dim)` (or a `render_scale`) and multiply pixel deltas by it. Fix before advertising any measurement as trustworthy. (Rare for 256/512 MR; real for high-res.)

---

## 2. Layout (hanging-protocol shell)

```
┌──────────────────────────────────────────────────────────────┐
│  Header: [CT | MRI]  "Image viewer — AI opt-in & labeling only"│
│  Persistent: not a medical device · human-in-the-loop          │
│  Toolbar: viewports[1×1|1×2|2×2] Window[auto|full|reset]       │
│  Zoom Pan Invert Caliper ROI Angle Ratio Link◉ Cursor-readout  │
├───────────┬──────────────────────────────────────┬───────────┤
│ SERIES    │   ┌───────────────┐  ┌──────────────┐ │ RIGHT RAIL│
│ RAIL      │   │  Viewport A   │  │  Viewport B  │ │ [Info]    │
│ (thumbs   │   │ (active seq)  │  │ (linked seq) │ │ [Measure] │
│  grouped  │   │  overlays:    │  │              │ │ [Assist ▸ │
│  by       │   │  calipers/ROI │  │  slice slider│ │  opt-in]  │
│  inferred │   │  slice slider │  └──────────────┘ │           │
│  T1/T2/…  │   └───────────────┘                   │ metadata/ │
│  +plane   │   cursor: (x,y) SI=812 a.u. b=1000 TE90│ QC tables│
│  +verify) │                                        │           │
├───────────┴──────────────────────────────────────┴───────────┤
│ Metadata strip: modality · plane · spacing · TR/TE · de-ID badge│
│ ⚠ Burned-in warning (if any) · Persistent NOT-A-DEVICE line    │
└──────────────────────────────────────────────────────────────┘
```

Left **series rail** (thumbnails grouped by series, each with inferred-sequence + plane + "auto — verify" chip), center **viewport grid** (1×1 / 1×2 / 2×2 hanging), right **rail** with Info / Measure / opt-in Assist tabs, persistent bottom metadata + disclaimer. Reuse the existing banner, burned-in warning, and de-ID badge verbatim. CT and MRI share this shell; the only deltas are units (HU vs a.u.) and the sequence/label trust story.

---

## 3. Feature inventory by buildability

Tiers: **Tier 0** = already shipped (reuse). **Tier 1 / Phase 1** = buildable now on the current CPU-only, model-free stack (series grouping + client-side viewer upgrades, no new heavy deps). **Tier 2 / Phase 2** = bounded backend refactor (raw-intensity transport). **Tier 3 / Phase 3** = future (MPR volume infra, registration, or license-gated models, async).

### Tier 0 — already shipped (reuse verbatim)
Slice nav (wheel/key/slider, `_slice_position` ordering, "slice X/Y (capped)" at `VIEW_MAX_SLICES=80`); stack-wide percentile a.u. window; CSS brightness/contrast aid; mm caliper with px fallback; burned-in warning; de-ID badge; coded sequence hint ("auto — verify"); persistent disclaimer; memory-safe decode (downscale-before-retain, slice cap, `n_slices_total`/`truncated`).

### Tier 1 / Phase 1 — buildable now (developer-ready)

**1. Series / sequence navigation.** Split by `SeriesInstanceUID` → series rail, one thumbnail group per series with an inferred-sequence label + "auto — verify" badge (overrideable dropdown). Classification is **deterministic heuristic, not AI**, and PHI-safe by using coded/numeric tags only — never the scrubbed free-text descriptors:
- **T1** — short `RepetitionTime` (<~800 ms) + short `EchoTime` (<~30 ms), SE/GR
- **T2** — long TR (>~2000 ms) + long TE (>~80 ms), SE
- **FLAIR** — `ScanningSequence` contains `IR` + long `InversionTime` (~2000–2500 ms) + long TE
- **STIR** — `IR` + short `InversionTime`
- **DWI** — `EP` + `DiffusionBValue (0018,9087)` present, b>0
- **ADC** — `ImageType (0008,0008)` contains `ADC`/`DERIVED` (computed map), or derived partner of a DWI
- **T1C** — T1 pattern **and** `ContrastBolusAgent (0018,0010)` *has a value* (presence flag only — never render the string; it can be free text)

Honest caveat surfaced in-tooltip: coded params only *weakly* imply the clinical name (`IR` could be FLAIR or STIR). Confidence < threshold → amber chip. User can reassign a series' label, which re-lays-out the protocol.

**2. Plane / orientation badge.** Derive axial / coronal / sagittal / oblique deterministically from `ImageOrientationPatient` dominant normal axis (the normal is already computed in `_slice_position`). Zero compute, no confidence needed (pure geometry), corner label + rail icon.

**3. Viewport grid + hanging protocols.** 1×1 / 1×2 / 2×2, auto-arranged by sequence into region templates (2×2 stroke, 3-pane spine, multiphase liver — see §5).

**4. Linked scroll (index / proportional).** Show 2+ series; scrolling one moves the others. **Index-link** for same-acquisition families (DWI↔ADC, dynamic phases). `Link` toggle + link-mode badge. Pure client-side math, zero server cost.

**5. DWI + ADC auto-pairing.** Detect the pair by shared frame-of-reference + matching geometry (DWI = EP/b>0; ADC = DERIVED/ImageType ADC), drop into a linked 1×2 with **exact synchronized scroll**. Show **b-value** (coded/numeric) + dual cursor readout. Honesty line: the MVP **co-displays and pairs** so the human reads bright-DWI/dark-ADC mismatch — it does **not** auto-flag "restricted diffusion" (a diagnostic call).

**6. Multi-echo grouping.** Group frames by `EchoNumbers (0018,0086)` / `EchoTime` into a slice × echo grid: scroll slices at fixed echo, or step echoes (chip showing `TE = X ms`) at fixed slice.

**7. Side-by-side sequence compare.** 2-up of any two series — just two synced viewers, no AI "these correlate" claim.

**8. Client-side zoom / pan / invert / rotate-flip + magnifier loupe.** CPU-trivial canvas transforms on the user's machine. Standard radiology mouse map (on-screen hint + docs):

| Input | Action |
|---|---|
| Left-drag | Window (WL/WW) — Tier 2; CSS B/C stopgap now |
| Middle-drag / Space+drag | Pan |
| Right-drag | Zoom (cursor-anchored) |
| Wheel | Scroll slices |
| `I` | Invert grayscale (MONOCHROME1 already inverted server-side — this toggles on top) |
| `+ / −`, `R` | Zoom in/out, reset |
| Arrows / slider | Slice nav (shipped) |

Touch: pinch-zoom, two-finger pan, vertical drag to scroll.

**9. Measurement — distance & angle (see §4).** Polyline caliper and angle tools are Tier 1 (need only the effective-spacing fix).

**10. Structured report templates + deterministic rule engines (see §5).** Region-templated reader-entry forms with ASPECTS/LI-RADS/PI-RADS/McDonald *arithmetic over reader inputs* — transparent lookup, not a model.

### Tier 2 / Phase 2 — raw-intensity transport (bounded refactor)
True client-side WL/WW windowing in a.u. (left-drag); **live signal-intensity cursor readout** `(x,y) SI = N a.u.`; **ROI mean±SD + area (mm²)**; **SIR / %Δ / CNR**; **geometric position-based linked scroll** (via per-slice `ImagePositionPatient`, correct across differing slice counts/spacing); per-sequence remembered windows; **cross-reference / localizer lines** (project active slice plane onto other planes via the two IOP frames; click-to-jump). Persist annotations.

### Tier 3 / Phase 3 — future
Server-side orthogonal **MPR reformats** (+ thin-slab MIP; anisotropic spacing yields blocky reformats that **must be disclosed**); oblique/curved MPR; **SimpleITK/elastix registration** (longitudinal current↔prior, multiphase alignment, difference maps); multi-echo parameter maps (T2*/R2*); calibrated ADC readout (verify-calibration flag); **AI anatomical-labeling overlays** (§6).

---

## 4. Measurement & annotation UX

**Constraint that shapes everything:** MR ROI values are never "HU" and never shown against CT thresholds. Report only as **relative signal intensity (a.u.)** with the caption *"Relative signal (arbitrary units) — not HU, not tissue-specific. Compare within this image only."* Parametric maps (ADC/T1/T2) carry real units via RescaleSlope/Intercept, but since the identifying free-text is scrubbed the viewer can't auto-detect "this is ADC" — honest resolution: **apply RescaleSlope/Intercept if present, label "stored/rescaled units — relative," let the human interpret.** Ratios stay valid either way. This is *measurement* (arithmetic on pixels), not diagnosis — no feature asserts what a region *is*.

- **Distance — polyline caliper (NOW).** Click vertices; 2 pts = straight, ≥3 = polyline with per-segment + cumulative length; draggable endpoints; anisotropy-safe `hypot(dx·spacing_col, dy·spacing_row)`. Gated on the effective-spacing fix.
- **Angle (NOW).** 3-point vertex and 4-point/2-line (Cobb-style). Convert vertices to mm space first when `spacing_row ≠ spacing_col` so anisotropy doesn't skew degrees. No server round-trip.
- **ROI stats (NEXT).** mean/SD/min/max/area/n. **Do not compute on the windowed 8-bit PNG** (display-domain, window-dependent, clipped) — if shown at all as an instant preview, hard-label "display-domain, window-dependent." Recommended: persist the **downscaled float slice** alongside each PNG (same geometry, ROI coords map 1:1; ~42 MB/view, TTL cleanup) and add `POST /api/dicom-roi` → `{view_id, slice_idx, rois:[polygon|ellipse|rect]}` → `{mean, sd, min, max, area_mm2, n_px, units:"a.u."|"rescaled"}` via numpy mask. Shapes: ellipse/rectangle/freehand, draggable, per-ROI color + auto label. `area_mm2 = n_px × spacing_row × spacing_col`, valid only for in-plane ROIs on native slices; grey out when spacing absent.
- **Signal-intensity ratio — the headline MR measurement (NEXT).** Designate a reference ROI → `SIR = mean_A/mean_B`, `%Δ = 100·(A−B)/B`, optional CNR `|A−B|/SD_bg`. Hard-gate: both ROIs on the **same slice / same acquisition / same window**; block/warn on cross-sequence or cross-study ratios; warn on saturated or near-zero denominator. Framing: "Signal ratio (relative) — decision support, not a diagnosis."
- **Region annotations (NOW client / NEXT persist).** Arrow, text, freehand ink, bounding box, per-object note. Annotation list panel (show/hide, rename, recolor, delete, jump-to-slice), stored per slice index as **vector overlays (JSON), never burned into pixels** (preserves de-ID). Inline warning on the note field: "Do not type patient identifiers." Export into the existing report path (`routers/report.py` / `ReportPanel.jsx`) as a structured human-authored table carrying the disclaimer.
- **Validity badge on every measurement** (green = mm valid / amber = approx MR distortion / grey = px-only): **valid** = in-plane on native slice with `PixelSpacing`; **approximate** = MR gradient-nonlinearity/B0 distortion worst at FOV edges ("measurements approximate — MR distortion"); **invalid/disabled** = no spacing, uncorrected downscale, through-plane 3D without `SliceThickness`+`SpacingBetweenSlices`+consistent geometry, or reformatted/MPR/oblique planes.
- **Two must-fix items before calling measurement trustworthy:** (1) effective pixel spacing after downscale (§1); (2) raw-pixel path for ROI stats.

New schemas in `backend/app/models/schemas.py` (ROI-stats + annotation; note existing `pixel_spacing_col` anisotropy comment at L70–71).

---

## 5. Clinical workflows → reporting UX

Each region is a hanging protocol over `series[]` plus a right-panel structured template. Reader enters features; the app does only **transparent published-rulebook arithmetic** and shows which inputs produced the category — never an auto-assigned score. All reuse the `FindingsForm` attest pattern (unchecked-by-default, "I have reviewed and adopt…" acknowledgement).

- **Brain — Stroke.** 2×2: DWI (b≈1000) | ADC | FLAIR | SWI/GRE. DWI↔ADC index-linked (highest-value linked-scroll case); FLAIR/SWI position-linked. Template: restricted-diffusion y/n, vascular territory pick-list, **ASPECTS** clickable 10-region checklist → auto-sum 10−n (reader clicks; number is arithmetic), DWI–FLAIR mismatch, hemorrhage on SWI, old infarcts.
- **Brain — Tumor.** T1post primary ‖ FLAIR; optional **subtraction pane** (T1post − T1pre) only if co-registered same-geometry, else flag "not registered." Template: location, 3D size, enhancement pattern, edema, midline shift (mm, caliper), lesion count, follow-up (new/stable/larger/smaller), reader-assigned BT-RADS/RANO.
- **Brain — MS / demyelination.** 3D FLAIR tri-planar; signature layout = **current ‖ prior FLAIR** (longitudinal is the killer feature). Template built on McDonald DIS/DIT: lesion count, DIS location checklist (periventricular/juxtacortical/infratentorial/spinal), DIT (enhancing+non-enhancing, new/enlarged vs prior), burden trend.
- **Spine.** Sagittal T1|T2|STIR index-linked + axial pane; **click a disc level on sagittal → jump axial** (defining interaction); auto-label vertebral levels. Per-level table (disc / canal stenosis / foraminal L-R / cord signal / listhesis), rows auto-seeded from labeled levels.
- **MSK.** PD-FS primary + multi-plane cross-referenced; template routed by `BodyPartExamined`. Knee (menisci/cruciates/collaterals/cartilage-by-compartment/effusion), shoulder (rotator cuff per-tendon/labrum/AC/biceps). Reader selects Outerbridge/ICRS grades and tear types.
- **Body (abdomen/pelvis).** Multiphase hanging protocol, all dynamic phases index-linked + subtraction pane; in/out-phase paired. **LI-RADS** and **PI-RADS** worksheets: reader enters features (arterial hyperenhancement, washout, capsule, size, growth / T2, DWI-ADC, DCE, zone), app computes the LR/PI-RADS category from the deterministic rulebook.

**Hard "never" line across all templates:** no MRI feature ever auto-asserts a diagnosis, disease category, count-as-diagnosis, or severity/malignancy score ("acute stroke detected," auto-ASPECTS, LR-5, PI-RADS 5, "HCC," "consistent with MS"). The reader assigns every clinical decision; the app labels anatomy, registers images, and measures.

---

## 6. AI-assist layer — license-clean, honest, opt-in by construction

Keep the viewer **model-free by construction.** AI arrives only as a **separate, opt-in, default-OFF overlay** with its own endpoint (`/api/mr-segment`, modality-guarded to MR-only, mirroring how the CXR path refuses non-CXR), reusing the chest pipeline's guardrails. Ground rule inherited from chest: **segmentation / anatomical labeling / volumetry / QC = defensible decision support; diagnostic classification = NOT claimable without validation + regulatory clearance.**

### License landscape (verify each weight file against the project OSS ship-list before adoption — framework Apache license ≠ weight license)

**Defensible (anatomical labeling / QC):**
- **SynthSeg** (BBillot) — **Apache-2.0 code + weights** in the *standalone repo* (⚠ the FreeSurfer-bundled `mri_synthseg` inherits FreeSurfer's non-clean license — pull standalone). Contrast/resolution-agnostic single 3D U-Net; **~minutes/volume on CPU, borderline — async background job, not interactive.** Whole-brain seg + parcellation + per-structure volumes + built-in QC score.
- **FastSurfer** (Deep-MI) — **Apache-2.0 code + weights**; seg-only module (VINN/asegdkt) is the feasible piece; **full surface pipeline is hours on CPU — defer.**
- **HD-BET** (MIC-DKFZ) — **Apache-2.0**; brain extraction, robust to pathology, async on CPU.
- **SynthStrip** (FreeSurfer/Hoopes) — **weights MIT / CC-BY-4.0** (clean), lighter than HD-BET.
- **TotalSegmentator (MR tasks)** — code Apache-2.0, **most weights Apache-2.0**; ⚠ `appendicular_bones(_mr)`, `tissue_types`, `heartchambers_highres`, `face` are **NON-COMMERCIAL** → hard-exclude in code; use only `total_mr`/`vertebrae_mr` tier. `--fast` ~couple minutes CPU, async.
- **MRIQC** (NiPreps) — **Apache-2.0** (≤0.16 was BSD-3, also clean); heavy, wraps ANTs/AFNI, async-only. No-reference technical QC (SNR/CNR/motion/ghosting) — never clinical.
- **Lightweight numpy QC heuristic (build yourself)** — clean license, **instant on free CPU** (background-noise SNR, edge sharpness, slice-to-slice intensity jumps). Advisory technical flag, buildable now.
- **MONAI (Apache-2.0)** + selected Model-Zoo bundles — each bundle's *weight* license must be verified individually.

**Off the ship-list (blocked):**
- **BraTS-derived tumor/lesion weights** (any nnU-Net glioma model) — nnU-Net *framework* is Apache-2.0, but BraTS weights carry a **Synapse non-commercial data-use provenance** → not license-clean for a public app; and tumor detection is a diagnostic claim → **double-blocked.** Framework fine, weights excluded. Research-only/private-offline future item.
- **FreeSurfer/SynthSeg-*bundled* weights** for commercial-clean shipping — FreeSurfer license is not Apache/MIT-style; use the standalone SynthSeg repo instead.

**Sequence auto-labeling** stays the deterministic coded-tag heuristic (§3) — no model, no license risk; an optional future tiny 2D CNN would be trained on our own license-clean data.

### Overlay UX contract (how AI never reads as diagnosis)
1. **Separate visual channel** — toggleable overlay / right-rail Assist tab, default OFF, launched by an explicit "Run anatomical analysis (opt-in)" button that starts an **async job** (never blocks the viewer). Clean image always one click away.
2. **Language contract** — "anatomical structure label (auto)," "candidate organ boundary — verify," "region of model attention." Never "lesion / tumor / edema / infarct / normal / abnormal / finding / impression."
3. **Categorical, legended color — not heat.** Segmentation uses categorical colors with a visible structure-name legend. **Do not** use a red/hot pathology-implying heatmap (that's the CXR Grad-CAM idiom, implies "danger here").
4. **Human-in-the-loop, editable** — accept/edit/reject per label; no silent auto-persistence of an AI verdict; export only with the disclaimer baked in.
5. **Schema discipline** — response carries label geometry + structure name only; **no probability/finding/impression field.** Any confidence shown is "model confidence in the label," not likelihood of disease.
6. **Persistent disclaimer** when AI is on: *"Computer-generated anatomical segmentation — for labeling and measurement support only. Verify against source images. Not a diagnosis; not a medical device."*

### AI hooks by workflow (all Phase 3, all reader-editable, all "labeling/measurement")
Brain structure map + volumetry (SynthSeg/FastSurfer-seg); skull-strip toggle (HD-BET/SynthStrip); QC badge (MRIQC/SynthSeg-QC/numpy proxy); vascular-territory *labeling* of a user ROI via a registered MNI atlas ("ROI in left MCA territory"); vertebra/level labeling (TotalSegmentator) to pre-fill spine table; registration-based longitudinal difference maps for MS/tumor follow-up; WM-lesion candidate masks feeding only a *count* field. **Not allowed anywhere:** tumor/MS/stroke/hemorrhage detection, "normal/no abnormality," atrophy/"abnormal for age" verdicts, any finding-shaped score.

### Classical (no-ML) assist buildable now
**ROI propagation across slices** via intensity-band region-growing / simple 2D registration (numpy/scipy) — zero license risk, framed "assisted ROI copy — verify."

---

## 7. Safety, de-ID & regulatory UX

- **De-ID badge** ("N identifiers removed") + **burned-in warning** (YES/NO/UNKNOWN — never assert clean pixels) persist on every panel, verbatim from current code. Extra vigilance for MR secondary captures / derived maps.
- **Sequence-source tooltip** — a small `sequence_source: "coded-tags"` flag lets the UI explain why the label is terse ("SE IR"): free-text descriptors were scrubbed for PHI, so labels are coded-only and advisory.
- **MR-safety out-of-scope one-liner** in the MR banner — no implant/SAR/MR-conditional indication; this is an image viewer, not a scanner console.
- **Contrast** — a T1+C series is still just the coded "auto — verify" label; the app never infers or advises on gadolinium administration.
- **Regulatory framing** — even "just segmentation" MR volumetry has 510(k) precedent; RadAssist stays in the non-clinical safe harbor (demonstration / de-identified / no-real-patient per INTENDED-USE.md) *only* while intended use is unchanged. A diagnostic MR claim crosses to FDA Class II+ CADe/CADx / EU MDR Rule 11 Class IIa+ — future, gated, not in the demo. **Lock intended-use + "anatomical labeling, not detection" before any MR AI build.**

---

## 8. API shape

`/api/dicom-view` evolves from one flat stack to a **series list**:
```
{ view_id, modality,
  series: [ {
     series_id, inferred_label, label_basis, label_confidence, sequence_source:"coded-tags",  // "auto — verify"
     plane,                                     // axial|sagittal|coronal|oblique (from IOP)
     frame_of_reference_uid,                    // pairing + geometric linking
     n_slices, n_slices_total, truncated, is_derived,
     slice_urls[]              (Tier 1: baked PNG)  |  raw_url + intensity_scale (Tier 2),
     slice_positions[],        // ImagePositionPatient·normal — enables position-link w/o registration
     echo_times[], b_values[],
     window:{ center, width, unit:"a.u." },
     spacing_mm, spacing_col_mm, slice_thickness_mm, render_scale
  } ... ],
  pairs: [ { dwi_series_id, adc_series_id } ],
  identifiers_removed, burned_in, disclaimer }
```
New: `POST /api/dicom-roi` (ROI stats on persisted raw floats); `POST /api/mr-segment` (future, MR-guarded, `structures:[{name, polygon}]`, no scores). **No** `finding`/`probability`/`impression` field anywhere.

---

## 9. Phased build plan

**Phase 1 — NOW, current CPU stack, no ML, no new licenses (developer-ready):**
- **Backend:** group `render_view` files by `SeriesInstanceUID` (capture UID before de-ID regenerates it); classify sequence per-series via coded/numeric tags (extend `_seq_label`); derive plane from `ImageOrientationPatient` in `_capture_view_meta`; return `series[]` with `slice_positions[]`, `echo_times[]`, `b_values[]`, per-series percentile window, `frame_of_reference_uid`, `render_scale`; surface `sequence_source`; **fix effective spacing after downscale.**
- **Frontend (`DicomViewer.jsx`):** series rail with "auto — verify" chips (overrideable) + plane badge; viewport grid 1×1/1×2/2×2 + region hanging protocols; index/proportional linked scroll; DWI+ADC auto-pairing (linked 1×2, b-value + dual readout); multi-echo grouping; zoom/pan/invert/rotate + loupe; polyline caliper + angle; documented mouse/keyboard scheme + on-screen hints; structured report templates + deterministic ASPECTS/LI-RADS/PI-RADS/McDonald rule engines (reuse `FindingsForm`); numpy QC heuristic + async-job scaffold wired with cheap producers first.
- **Invariants held:** MR stays out of `CXR_MODALITIES`; render path model-free; a.u. window + coded-only label unchanged; all guardrails/disclaimers verbatim.

**Phase 2 — bounded backend refactor (raw-intensity transport):** true client-side WL/WW in a.u. (left-drag); live SI cursor readout; ROI mean±SD + area (`/api/dicom-roi` on persisted floats); SIR/%Δ/CNR; geometric position-linked scroll + cross-reference/localizer lines; per-sequence remembered windows; persist annotations. Runs on free CPU (client does the interactive work).

**Phase 3 — worker/GPU or async, license-gated, all labeling/measurement:** SimpleITK/elastix registration (longitudinal + multiphase difference maps); SynthSeg brain seg + volumetry; SynthStrip/HD-BET skull-strip; TotalSegmentator Apache-tier organ/vertebra labeling; MRIQC full QC; orthogonal MPR (+ MIP, disclose anisotropy); multi-echo parameter maps; calibrated ADC. FastSurfer full-surface and any BraTS-derived tumor weights deferred/excluded.

---

### Key file anchors
- `E:\Radiology intervention\backend\app\services\dicom_utils.py` — `render_view`, `_downscale`, `_capture_view_meta`, `_seq_label`, `_slice_position`, `_deidentify`, `CT_PRESETS`
- `E:\Radiology intervention\backend\app\routers\viewer.py` — `/api/dicom-view`; add `/api/dicom-roi` and (future) `/api/mr-segment`
- `E:\Radiology intervention\backend\app\models\schemas.py` — series-list + ROI-stats + annotation schemas (note anisotropy comment L70–71)
- `E:\Radiology intervention\frontend\src\components\DicomViewer.jsx` — series rail, viewport grid, linked scroll, caliper→polyline/angle/ROI/annotation, opt-in Assist tab
- `E:\Radiology intervention\frontend\src\components\FindingsForm.jsx` — reuse for structured report templates and attest pattern

**Net:** the MRI MVP is a multi-*series*, model-free honest viewer (series rail + plane badge + a.u. percentile windowing + DWI/ADC pairing + linked scroll + caliper) — all Phase-1-buildable on the current CPU stack. Measurement gains truth in Phase 2 via the raw-intensity path (ratios, not bare means). AI enters only in Phase 3 as a separate, opt-in, license-gated **anatomical-labeling overlay** with categorical legended colors, editable and human-confirmed, carrying no diagnosis-shaped output — behind a locked non-clinical intended use.