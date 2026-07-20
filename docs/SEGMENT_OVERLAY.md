# Anatomy Segmentation Overlay — Design / README

*Opt-in, non-diagnostic AI overlay for the CT & MR viewers. Grounds the seam in
`backend/app/config.py` (flags, `MODEL_REGISTRY`, `assert_task_allowed`,
`CLEAN_LICENSES`, overlay copy), `backend/app/models/segment.py` (taboo-free
schema), the segmentation router/service, and `frontend/src/api.js`.*

---

## 0. THE HARD RULE (read first — this governs everything below)

**This is an anatomy-labeling overlay, NEVER disease detection.** It labels /
segments anatomy and measures regions ONLY. It never detects, characterizes, or
excludes any disease, injury, or abnormality. The boundary is made *structural*
in code and schema, not left to copy discipline:

- **Schema half** — every segment model subclasses `_TabooFree` in
  `models/segment.py`; a diagnosis-shaped field name/alias (probability, finding,
  severity, lesion, …) aborts module import. No score-shaped field can exist.
- **License + behaviour half** — a weight/task runs only if it is `commercial_ok`
  AND `anatomy_only` (below).

UI rules that follow from the hard rule:
- **Opt-in, default OFF.** `SEGMENT_ENABLED=0` / `MR_SEGMENT_ENABLED=0`.
- **Categorical, translucent colors only** — colors encode tissue/organ *identity*.
  NEVER a red/green alarm palette, NEVER a hot/heatmap colormap.
- **No "accept / adopt-to-report" affordance.** A region is never promotable into a
  finding or report.
- Canonical caption on every region readout: **`Computed region · not a finding`**
  (`config.OVERLAY_CAPTION`). Toggle label, volume format, and the CT/MR overlay
  disclaimers are the verbatim strings in `config.py` and travel with the response.

---

## 1. Taboo-free schema (region shape)

Each region is a plain dict / `Region` model with EXACTLY these keys and **no
diagnosis-shaped key ever**. `label` is an anatomy/tissue noun from a closed
vocabulary — never a pathology word.

| field | type | notes |
|---|---|---|
| `structure_id` | int | 1..N; **0 is reserved** for unlabeled/background — never a region |
| `label` | str (≤64) | anatomy/tissue noun ONLY (never a pathology word) |
| `color` | str | `#rrggbb` lowercase hex; categorical identity, never alarm |
| `volume_ml` | float \| None | `voxel_count * row_mm*col_mm*z_mm / 1000`; None if any spacing None |
| `voxel_count` | int | labeled voxels in the region |
| `area_mm2` | float \| None | per-slice sum when in-plane spacing known, else None |
| `mean_intensity` | float | a measurement, NOT a score |
| `intensity_unit` | `'HU'` \| `'a.u.'` | MR intensity is arbitrary / non-quantitative |
| `hu_range` | `[lo,hi]` \| None | CT band bounds; None for MR |
| `n_components` | int | connected components in the region |
| `method` | str | e.g. `hu-threshold-v1` |
| `model` | str | provenance model name |
| `license` | str | must be in `config.CLEAN_LICENSES` |

**FORBIDDEN** in any key or `label` value: finding / probability / score /
impression / severity / malignancy / abnormal / diagnosis / positive / negative /
suspicious / detected / lesion / tumor / cancer / mass / nodule / bleed /
hemorrhage / infarct / stroke / aneurysm / effusion / edema / fracture / stenosis /
pathology / disease / normal / confidence / likelihood / risk / grade / birads /
lirads / pirads / flag / triage / urgent / coverage / heatmap.

`SegmentResponse` (see `models/segment.py`) wraps `regions` with job metadata and a
**required `disclaimer`** so the CT/MR boundary is never dropped from a response.

---

## 2. License + anatomy whitelist (fail-closed on BOTH axes)

A task is invokable ONLY if `commercial_ok` AND `anatomy_only`
(`config.MODEL_REGISTRY` + `assert_task_allowed`, which fail closed on unknown
task names). This blocks two distinct classes:

- **Non-commercial weights** (e.g. `brain_aneurysm` CC-BY-NC, the `tissue_types`
  family) — `commercial_ok=False` ⇒ blocked regardless of anatomy.
- **Apache-clean but disease-shaped "trap" tasks** (`lung_nodules`,
  `liver_lesions`, `cerebral_bleed`, `pleural_pericard_effusion`) — they segment a
  *candidate lesion*, which reads as detection ⇒ `anatomy_only=False` ⇒ blocked.

`TOTALSEG_TASK_WHITELIST` (env) may only **INTERSECT** the code-derived allow-set —
it can narrow, never widen. `classical` needs no weights and is always allowed.
`CLEAN_LICENSES` gates the `Region.license` value at the schema layer. **Snapshot
2026-07: re-audit every per-subtask weight LICENSE on any version bump** (see the
header note in `requirements-segment.txt`).

---

## 3. Classical baseline (ship now) vs pluggable heavy seam

- **Ship-now baseline — REAL, CPU-instant, ZERO heavy deps.** Deterministic
  classical labeling: HU-threshold tissue bands for CT
  (`classical-hu-threshold`), intensity-cluster / skull-strip for MR
  (`classical-mr-intensity`). Runs on numpy/scipy/scikit-image — already installed.
- **Pluggable seam — designed + wired, NOT installed.** TotalSegmentator (CT & MR
  tasks) and SynthSeg (MR brain) live behind the same provider contract. The heavy
  deps are the OPTIONAL `requirements-segment.txt` (`totalsegmentator`, `nnunetv2`,
  `nibabel`, `SimpleITK`), installed only on a `SEGMENT_MODEL=totalseg` deploy. The
  provider self-gates to classical-only when those imports are missing, so the app
  boots and serves without them.

**Provider contract** the module exposes (called by the lead's `segmentation.py`):

```
CT: label_tissue(hu, spacing_mm, *, is_ct=True) -> (regions, label_vol)
MR: label_mr(vol, spacing_mm)                    -> (regions, label_vol)
```

`hu`/`vol` is `np.ndarray (Z,H,W) int16` (HU for CT, arbitrary a.u. for MR);
`spacing_mm` is `(row_mm, col_mm, z_mm)` and ANY element may be `None`. `regions`
is `list[dict]` (Region shape); `label_vol` is `np.ndarray (Z,H,W) uint8` where each
voxel = its region's `structure_id` (0 = unlabeled). **Deterministic** — fixed
thresholds/params, no RNG, byte-identical across runs — and it enforces the
`SEGMENT_MAX_STRUCTURES` cap.

---

## 4. Modality guard & endpoints

Two **separate** endpoints, each hard-guarded on the DICOM Modality header so a
head CT can never be silently MR-segmented and vice versa:

- **`/api/segment` — CT only** (`SEGMENT_MODALITIES = {"CT"}`).
- **`/api/mr-segment` — MR only** (`MR_SEGMENT_MODALITIES = {"MR"}`).

Frontend calls (in `frontend/src/api.js`):
- `startAnatomySegment(files, modality, opts={})` → POST the correct endpoint.
- `pollAnatomySegment(jobId)` → GET `/api/segment/{jobId}` → `SegmentResponse`.
- `assertNoDiagnosisFields(obj)` → throws if a diagnosis-shaped key is present
  (belt-and-suspenders over the taboo-free schema).

Keeping segmentation in its own router leaves the viewer model-free by construction.

---

## 5. Job store limitation

The job store is **in-memory and single-container**: `SEGMENT_MAX_CONCURRENT_JOBS=1`
(a minutes-long, multi-GB run never fans out), bounded by `SEGMENT_QUEUE_MAX`, with
per-IP launch limiting (`SEGMENT_RATE_LIMIT_MAX`) and a TTL sweep. Jobs do **not**
survive a restart and are **not** shared across replicas — this path is single-node
by design and is not horizontally scalable without an external queue/store.
