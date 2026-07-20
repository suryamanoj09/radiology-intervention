import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Storage. Images/heatmaps are served publicly; analysis JSON is kept in a
# NON-served directory so a study's full results are not world-readable by id.
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage")))
UPLOADS_DIR = STORAGE_DIR / "uploads"
HEATMAPS_DIR = STORAGE_DIR / "heatmaps"
ANALYSIS_DIR = STORAGE_DIR / "analysis"  # private; not mounted as StaticFiles
# Reviewer thumbs-up/down feedback, appended as JSONL. Private (NOT mounted) and
# PHI-free by construction (schema-validated, no free-text identifier fields).
FEEDBACK_DIR = STORAGE_DIR / "feedback"
# Audit trail (HIPAA §164.312(b)): PHI-free access log, private (NOT mounted).
AUDIT_DIR = STORAGE_DIR / "audit"
# Anatomy-overlay segmentation masks (opt-in AI). Served publicly like uploads/
# heatmaps (opaque filenames only), TTL-swept with the other derived artefacts.
SEGMENTS_DIR = STORAGE_DIR / "segments"
for _d in (UPLOADS_DIR, HEATMAPS_DIR, ANALYSIS_DIR, FEEDBACK_DIR, AUDIT_DIR, SEGMENTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
# On by default only when auth is on (an access log needs an identity to be useful).
AUDIT_ENABLED = os.getenv("AUDIT_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
# Hard ceiling on the (TTL-exempt, append-only) feedback log so it cannot grow the
# disk without bound; writes past this are dropped (a warning is logged).
FEEDBACK_MAX_BYTES = int(os.getenv("FEEDBACK_MAX_MB", "50")) * 1024 * 1024

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").strip().lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b").strip()
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

# Flagging uses the model's per-class operating points; this is a floor fallback
# for classes whose calibrated threshold is unavailable.
FINDING_THRESHOLD = float(os.getenv("FINDING_THRESHOLD", "0.5"))
# Priority/urgent review flag for critical labels (on raw sigmoid confidence).
URGENT_THRESHOLD = float(os.getenv("URGENT_THRESHOLD", "0.6"))
# Pneumothorax is the one true emergency in the label set and CXR models are
# insensitive to small/apical/supine cases, so it gets a low, sensitivity-
# favoring "cannot exclude" threshold. But a RED "review promptly" banner on a
# score whose calibrated probability is ~8% (the 0.50-0.60 band) is alert fatigue,
# so the ALERT band (0.35..URGENT) is an AMBER advisory "cannot exclude"; only a
# genuinely high score (>= URGENT) escalates to a RED urgent banner.
PNEUMOTHORAX_ALERT_THRESHOLD = float(os.getenv("PNEUMOTHORAX_ALERT_THRESHOLD", "0.35"))
PNEUMOTHORAX_URGENT_THRESHOLD = float(os.getenv("PNEUMOTHORAX_URGENT_THRESHOLD", "0.6"))
# The top-of-page priority BANNER fires only when a finding's CALIBRATED probability
# clears this floor — never off a raw/uncalibrated score. A pneumothorax at raw 54%
# whose calibrated P is ~5% must not raise an emergency banner (alert fatigue). The
# per-finding "cannot exclude" disposition chip still carries the sensitivity caveat.
PRIORITY_MIN_CALIBRATED_P = float(os.getenv("PRIORITY_MIN_CALIBRATED_P", "0.30"))
# FIX #4 — triage/calibration TAIL SAFETY. A sparse-label isotonic map can snap its
# tail to 1.0 (fit on a handful of positives), which would clear the triage floor and
# manufacture a false "urgent" banner. Two hardenings, both ONLY on the calibrated-P
# path that feeds triage (flags stay on the raw score, unchanged):
#   * clamp the calibrated P used for triage to this maximum, so a snapped 1.0 tail
#     cannot present as certainty; and
#   * require the label's isotonic map to carry at least CALIBRATION_MIN_KNOTS distinct
#     knot values (support) before its calibrated P may escalate the banner.
TRIAGE_MAX_CALIBRATED_P = float(os.getenv("TRIAGE_MAX_CALIBRATED_P", "0.90"))
CALIBRATION_MIN_KNOTS = int(os.getenv("CALIBRATION_MIN_KNOTS", "4"))

# FIX #3 — per-label RELIABILITY gating, driven by the MEASURED behaviour card (not a
# hardcoded list). A label is "reliably measured" only when the validation set had
# enough positive support AND the measured AUROC is above chance. A label failing
# either bar (e.g. Pneumonia 0.458 AUROC / sens 0.0, or Pneumothorax 0.828 on only 9
# positives) is framed as ADVISORY "cannot exclude", NOT a confident finding, and must
# NOT drive an urgent triage escalation.
RELIABILITY_MIN_POSITIVES = int(os.getenv("RELIABILITY_MIN_POSITIVES", "20"))
RELIABILITY_MIN_AUROC = float(os.getenv("RELIABILITY_MIN_AUROC", "0.6"))  # <= this == at/below chance

# FIX #1 — "no flag" is NOT a normal read. The CXR path never makes an explicit
# "normal" call; the absence of a flag must be surfaced as an explicit non-claim, in
# the API contract (not just a frontend string), because the model can (and measurably
# does) miss disease. See behaviour_card.json -> no_flag_npv for the measured NPV.
READ_DISPOSITION_NOT_NORMAL = "not_a_normal_read"
NORMAL_READ_MESSAGE = (
    "The absence of a flagged finding is NOT a normal read. This tool screens for a "
    "limited set of findings and can miss disease — including labels it is not reliably "
    "measured on. Do not infer a normal study from the lack of a flag; a qualified "
    "clinician must interpret the image independently."
)
ABSTAIN_READ_MESSAGE = (
    "This image was withheld from scoring (it does not look like a readable frontal "
    "chest radiograph). This is NOT a normal read and NOT a negative result."
)

# --- Pretrained ensemble (no training) -------------------------------------
# Comma-separated TorchXRayVision (Apache-2.0) weight names whose BANDED outputs
# are averaged per label to improve robustness/calibration. Defaults to a SINGLE
# model for CPU speed on the free 2-vCPU Space; add e.g.
#   ENSEMBLE_WEIGHTS=densenet121-res224-all,densenet121-res224-rsna
# to bring in a model stronger on pneumonia/lung-opacity. Each model keeps its own
# op_threshs so its output is banded (0.5 == that model's operating point) before
# averaging; labels a model lacks (or with a NaN op_thresh) simply don't vote.
# License-clean options: densenet121-res224-all, -rsna, -chex, -mimic_ch, -mimic_nb,
# -nih, -pc (all Apache-2.0). Do NOT reintroduce Open-i weights.
ENSEMBLE_WEIGHTS = [
    w.strip() for w in os.getenv("ENSEMBLE_WEIGHTS", "densenet121-res224-all").split(",")
    if w.strip()
]

# Test-time augmentation: average each model's output over the image and its
# horizontal flip. Pathology labels here are side-agnostic, so this is a valid
# robustness boost. Roughly DOUBLES inference time; off by default on CPU.
TTA_HFLIP = os.getenv("TTA_HFLIP", "0").strip().lower() in ("1", "true", "yes", "on")

# Per-finding Grad-CAM localization: how many flagged findings get an attention
# region/overlay (capped for latency). Emergency/priority labels are localized
# first so a flagged pneumothorax always gets a region.
LOCALIZE_MAX = int(os.getenv("LOCALIZE_MAX", "6"))
LOCALIZE_PRIORITY_LABELS = {
    "Pneumothorax", "Pneumonia", "Consolidation", "Effusion", "Edema", "Mass", "Lung Lesion",
}

# --- Attention-region size estimate (from the Grad-CAM CAM, not a lesion) ----
# High-attention mask = CAM >= this fraction of its own max. This is the SAME
# mask the attention bbox uses, so the reported bbox and the size estimate always
# describe the same region.
ATTENTION_MASK_FRAC = float(os.getenv("ATTENTION_MASK_FRAC", "0.6"))
# Cap the simplified attention polygon so payload + overlay cost stays bounded
# regardless of blob shape.
ATTENTION_POLY_MAX_POINTS = int(os.getenv("ATTENTION_POLY_MAX_POINTS", "40"))

# Attention-on-background reliability check. A flag whose Grad-CAM attention sits
# on near-black, non-anatomical pixels (image border / blank area) is likely a
# shortcut artifact, not a real finding (e.g. "Emphysema" over a black margin).
# Pixels <= BACKGROUND_LEVEL count as background; if the high-attention region is
# mostly background we SUPPRESS the flag; a smaller fraction adds a caution note.
BACKGROUND_LEVEL = int(os.getenv("BACKGROUND_LEVEL", "15"))
ATTENTION_BG_SUPPRESS = float(os.getenv("ATTENTION_BG_SUPPRESS", "0.55"))
ATTENTION_BG_CAUTION = float(os.getenv("ATTENTION_BG_CAUTION", "0.30"))

# Anatomy-awareness gate: segment chest anatomy (lungs/heart/mediastinum/bones)
# and suppress a finding whose attention region does NOT overlap the anatomy that
# finding could plausibly arise from (e.g. "Cardiomegaly" attention on the arm).
ANATOMY_GATE_ENABLED = os.getenv("ANATOMY_GATE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
ANATOMY_MIN_OVERLAP = float(os.getenv("ANATOMY_MIN_OVERLAP", "0.20"))   # below => suppress
ANATOMY_CAUTION_OVERLAP = float(os.getenv("ANATOMY_CAUTION_OVERLAP", "0.50"))  # below => caution

# --- Burned-in marker masking (shortcut-learning defence) -------------------
# THE root-cause fix for shortcut learning. Portable/supine films carry burned-in
# corner text ("L", "PORTABLE", "AP", timestamps). Those tokens are near-perfect
# statistical predictors of the pathologies sick bed-bound patients have (edema,
# effusion), so a CXR model learns the TEXT instead of the anatomy (Zech 2018;
# DeGrave 2021, "shortcuts over signal"). We inpaint the markers BEFORE the model
# (and Grad-CAM) ever see them, so it cannot cheat on text it can't see. The
# ORIGINAL image is still what the clinician views; only the model's input is
# cleaned. Markers are detected as near-saturated, compact glyphs in the margin
# bands only — the central chest is never touched, so a real bright finding in the
# lungs is safe.
MASK_MARKERS_ENABLED = os.getenv("MASK_MARKERS", "1").strip().lower() in ("1", "true", "yes", "on")
# A pixel must be at least this bright (0-255) to be marker candidate. Burned-in
# text is drawn at/near pure white; real anatomy rarely holds a flat 235+ plateau
# over a compact blob, so this strongly discriminates text from tissue.
MARKER_BRIGHT_MIN = int(os.getenv("MARKER_BRIGHT_MIN", "235"))
# Only the outer this-fraction band on each edge is searched (corners/margins).
MARKER_MARGIN_FRAC = float(os.getenv("MARKER_MARGIN_FRAC", "0.22"))
# A candidate blob larger than this fraction of the frame is a bright FIELD
# (shoulder, collimation), not a marker — skip it.
MARKER_MAX_AREA_FRAC = float(os.getenv("MARKER_MAX_AREA_FRAC", "0.03"))
MARKER_MIN_AREA = int(os.getenv("MARKER_MIN_AREA", "10"))  # ignore single-pixel specks
MARKER_INPAINT_RADIUS = int(os.getenv("MARKER_INPAINT_RADIUS", "5"))

# --- Heatmap localization honesty -------------------------------------------
# A Grad-CAM map's NATIVE grid (densenet121-res224 = 7x7) is what actually carries
# spatial information; upsampling it to 1000px does NOT add resolution. A crisp
# CONTOUR implies a boundary the model cannot support, so we only draw one when
# the native grid is at least CONTOUR_MIN_GRID cells (e.g. the optional res512
# ResNet = 16x16). Below that we render a SOFT gradient edge, never a crisp line.
CONTOUR_MIN_GRID = int(os.getenv("CONTOUR_MIN_GRID", "16"))
# A high-attention region spanning fewer than this many NATIVE grid cells is the
# upsampler talking, not real structure -> not outline-worthy.
CAM_MIN_CELLS = float(os.getenv("CAM_MIN_CELLS", "3"))
# If the high-attention mask covers more than this fraction of the whole image the
# map is non-specific -> state 'diffuse' (soft heat, no outline, labelled).
CAM_DIFFUSE_MAX_FRAC = float(os.getenv("CAM_DIFFUSE_MAX_FRAC", "0.40"))
# Native grid of the ACTIVE localization CAM. The default densenet121-res224 CAM
# is 7x7. This must reflect the model that ACTUALLY produces the CAM — setting it
# to 16 while the CAM is still 7x7 would draw false crisp contours on a coarse map.
CAM_NATIVE_GRID = int(os.getenv("CAM_NATIVE_GRID", "7"))
# Optional res512 ResNet localizer (16x16 grid) for FLAGGED findings only — the
# 224 ensemble still produces the displayed confidence; this model produces only a
# higher-resolution ATTENTION MAP (captioned as such). It makes a crisp contour
# defensible and can beat the 7x7 pointing ceiling. It is ~10s/CAM on CPU, so it is
# OFF by default and CAPPED (below); enable on a GPU deploy or when latency is not
# critical. Implemented in services/localizer.py.
LOCALIZER_WEIGHTS = os.getenv("LOCALIZER_WEIGHTS", "").strip()
# When the localizer is enabled, cap how many (priority-first) findings get the
# expensive 16x16 CAM; the rest fall back to the fast 7x7 densenet map.
LOCALIZER_MAX_FINDINGS = int(os.getenv("LOCALIZER_MAX_FINDINGS", "2"))
# Overlay colormap: encodes INTENSITY ONLY, never pathology identity. 'inferno'
# (default; monotonic luminance, safe on a grey base) or 'cividis' (designed for
# colour-vision deficiency). Jet/rainbow is never offered (measured higher error).
HEATMAP_COLORMAP = os.getenv("HEATMAP_COLORMAP", "inferno").strip().lower()


def native_cam_grid() -> int:
    """Native Grad-CAM grid of the ACTIVE localizer (densenet121-res224 => 7).
    Never inferred from LOCALIZER_WEIGHTS, because the localizer is not swapped yet
    and a mismatched grid would fake crisp contours on a coarse map."""
    return CAM_NATIVE_GRID if CAM_NATIVE_GRID > 0 else 7


# --- Overlay rendering ------------------------------------------------------
# The CAM is normalized between a LOW-percentile floor and a HIGH-percentile
# ceiling. Min-max normalization manufactures a hot focal spot on EVERY image
# (the single brightest pixel becomes 1.0 even on a flat, uncertain map). We
# instead subtract the floor (typical background attention) and divide by the
# ceiling: cold regions go transparent, and a genuinely diffuse map — where floor
# and ceiling nearly coincide — is treated as "no localization" and stays dim
# rather than being stretched into a false hotspot.
OVERLAY_LO_PCT = float(os.getenv("OVERLAY_LO_PCT", "60"))
OVERLAY_HI_PCT = float(os.getenv("OVERLAY_HI_PCT", "99"))
# If (ceiling - floor) is below this fraction of the CAM's max, the map has no
# real contrast (diffuse/uncertain) -> render nothing, don't fake a hotspot.
OVERLAY_MIN_CONTRAST_FRAC = float(os.getenv("OVERLAY_MIN_CONTRAST_FRAC", "0.06"))
# Heat alpha = norm**gamma * alpha_max, so COLD regions are fully transparent (no
# whole-frame purple haze burying the anatomy). gamma>1 sharpens the falloff.
OVERLAY_ALPHA_GAMMA = float(os.getenv("OVERLAY_ALPHA_GAMMA", "1.7"))
OVERLAY_ALPHA_MAX = float(os.getenv("OVERLAY_ALPHA_MAX", "0.72"))

# --- Calibration hook (no training) ----------------------------------------
# Optional per-label flag thresholds in BANDED (op_norm) space, emitted by the
# validation harness (validation/run_validation.py --emit-calibration) from NIH
# operating-point tuning. This does NOT retrain the model — it only moves each
# label's decision threshold. Ensembling/TTA shift a label off the single-model
# 0.5 operating point, so re-deriving thresholds here restores calibration.
# JSON shape: {"thresholds": {"Pneumonia": 0.42, ...}, "meta": {...}}
CALIBRATION_PATH = Path(os.getenv("CALIBRATION_PATH", str(BASE_DIR / "calibration.json")))

# Model behaviour card (measured per-label AUROC/sens/spec + localization from the
# validation harness) served to the UI so accuracy is shown honestly, not claimed.
BEHAVIOR_CARD_PATH = Path(os.getenv("BEHAVIOR_CARD_PATH", str(BASE_DIR / "behavior_card.json")))


def _load_calibration() -> dict[str, float]:
    try:
        if CALIBRATION_PATH.exists():
            data = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
            return {str(k): float(v) for k, v in data.get("thresholds", {}).items()}
    except Exception:
        pass
    return {}


# Loaded once at import; empty dict => every label uses FINDING_THRESHOLD.
LABEL_THRESHOLDS = _load_calibration()

# --- Probability calibration (the displayed number is a SCORE, not a probability) -
# Measured ECE ~= 0.24: the banded confidence is overconfident. This maps the raw
# score -> a calibrated P(disease) PER LABEL, fitted on held-out NIH data by the
# validation harness (run_validation.py --emit-calibration-map). We SHIP BOTH:
# `probability` (the raw score, still what flag thresholds use, so calibration never
# silently moves a flag) and `calibrated_probability` (honest P for display).
# isotonic (default) | platt | none.
CALIBRATION_MODE = os.getenv("CALIBRATION_MODE", "isotonic").strip().lower()
CALIBRATION_MAP_PATH = Path(os.getenv("CALIBRATION_MAP_PATH", str(BASE_DIR / "calibration_map.json")))
# A label with no calibration map falls back to a bare score, and a bare "51%"
# reads to a human as "coin flip — might be real" when the calibrated truth may be
# ~2-5%. So an uncalibrated label's score is NOT shown as a probability; the UI
# renders a "not calibrated — read independently" state. On by default.
SUPPRESS_UNCALIBRATED_SCORES = os.getenv("SUPPRESS_UNCALIBRATED_SCORES", "1").strip().lower() in ("1", "true", "yes", "on")

# Labels too weak to surface as findings. `Fracture` is XRV's weakest label
# (report-mention supervision, no site, low prevalence, uncalibrated) — in practice
# a fabricated body part on an uninterpretable score with no map. Denied labels are
# NOT shown as findings; they appear only in the "what we didn't check" panel as an
# honest SCOPE statement (never "no fracture"). Auto-deny also any label whose
# measured AUROC < LABEL_MIN_AUROC.
LABEL_DENYLIST = {
    s.strip() for s in os.getenv("LABEL_DENYLIST", "Fracture").split(",") if s.strip()
}
LABEL_MIN_AUROC = float(os.getenv("LABEL_MIN_AUROC", "0.70"))
# Only HARD-DENY a label on its measured AUROC when that measurement is RELIABLE
# (enough positives in the validation set). A sub-floor AUROC from a tiny sample
# (e.g. Pneumonia scored 0.46 on 2 positives, Nodule 0.63 on 7) is statistical noise,
# NOT evidence the label is weak — hiding it on that basis is dishonest (it asserts a
# measurement we don't have). Such labels instead SURFACE with the AUROC-weak + not-
# calibrated cautions the UI already shows. The explicit LABEL_DENYLIST is independent
# and always denies. Set to 0 to restore the old behaviour (deny on any sub-floor AUROC,
# reliable or not) once the validation set is large enough that estimates are trustworthy.
LABEL_MIN_AUROC_REQUIRE_RELIABLE = os.getenv(
    "LABEL_MIN_AUROC_REQUIRE_RELIABLE", "1").strip().lower() in ("1", "true", "yes", "on")

# --- Multi-view fusion operator ---------------------------------------------
# max = safety-favouring per-label max of the raw score (default; a one-view finding
#       is never diluted). noisy_or / calibrated_mean combine CALIBRATED probabilities
#       and are only defensible once a calibration map exists (else they fall back to
#       max). See services/fusion.py.
FUSION_MODE = os.getenv("FUSION_MODE", "max").strip().lower()
# A DOWN-WEIGHTED view (self-audit said "less reliable", e.g. a lateral) previously
# fed fusion at full strength — it could drive the study MAX by accident. Its score
# is now scaled by this factor for aggregation (still shown at full value per-view).
DOWNWEIGHT_FUSION_FACTOR = float(os.getenv("DOWNWEIGHT_FUSION_FACTOR", "0.6"))

# --- Prior-study comparison noise floor -------------------------------------
# A delta smaller than the model's own measured instability is not real change.
# perturbation_std => suppress any interval delta below k * the label's measured
# perturbation std (hflip/rotate/crop), labelling it "within measurement noise".
# fixed => legacy fixed DELTA only. Stats written by perturbation_stability.py --emit-stats.
COMPARE_MIN_DELTA_MODE = os.getenv("COMPARE_MIN_DELTA_MODE", "perturbation_std").strip().lower()
COMPARE_NOISE_K = float(os.getenv("COMPARE_NOISE_K", "2.0"))
PERTURBATION_STATS_PATH = Path(os.getenv("PERTURBATION_STATS_PATH", str(BASE_DIR / "perturbation_stats.json")))

# --- Anatomy-gate safety audit ----------------------------------------------
# The anatomy gate can DELETE a correct finding (PSPNet mis-segments). warn_only
# keeps the caution note but never suppresses; suppress (default) is the safety
# gate. Its false-negative rate is measured into the behaviour card.
ANATOMY_GATE_MODE = os.getenv("ANATOMY_GATE_MODE", "suppress").strip().lower()  # suppress | warn_only

# CT/MRI viewer (NO AI): bounds for the model-free multi-slice render path.
# A series is many files, so a larger file count + aggregate size than the single
# analyze path, but the rendered slice count served is capped for the free Space.
VIEW_MAX_FILES = int(os.getenv("VIEW_MAX_FILES", "150"))
VIEW_MAX_SLICES = int(os.getenv("VIEW_MAX_SLICES", "80"))
VIEW_MAX_TOTAL_BYTES = int(os.getenv("VIEW_MAX_TOTAL_MB", "150")) * 1024 * 1024
# Each decoded slice is downscaled to <= this longest edge BEFORE it is retained,
# so peak memory is bounded (~VIEW_MAX_SLICES * edge^2 * 4B) no matter how large
# the source rasters claim to be — a decode-time DoS guard, not just a display cap.
VIEW_MAX_EDGE = int(os.getenv("VIEW_MAX_EDGE", "1024"))

# Multi-image study: max current images accepted in one /api/analyze-study call.
# Each image runs the full ensemble + per-finding Grad-CAM, so this caps CPU/latency
# on the free Space. Kept small deliberately (PA + lateral + a couple extra).
STUDY_MAX_IMAGES = int(os.getenv("STUDY_MAX_IMAGES", "4"))

# Upload / rendering bounds.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_OVERLAY_EDGE = int(os.getenv("MAX_OVERLAY_EDGE", "1024"))

# Decompression-bomb guard: reject an image/slice whose decoded pixel count exceeds
# this. 25 MP covers real chest radiographs (up to ~5000x5000) and CT/MR slices while
# bounding the transient decode (25 MP float32 ≈ 100 MB/file) — a crafted RLE/JPEG
# DICOM can otherwise amplify a tiny upload into a huge array.
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", str(25_000_000)))
# Absurd multi-frame counts are refused BEFORE decode (a 1x1x64M-frame file passes a
# pixel-count check but explodes a per-frame Python loop). Frames beyond N*this bound
# are rejected. Also the hard ceiling for how many frames one file may contribute.
MAX_FRAMES_PER_FILE = int(os.getenv("MAX_FRAMES_PER_FILE", str(4 * 200)))
# Process-wide cap on concurrent heavy DICOM decodes, so many small requests cannot
# each spawn a big transient array and collectively OOM the box (the per-IP rate limit
# does not bound in-flight concurrency). Independent of the anyio threadpool size.
MAX_CONCURRENT_DECODES = int(os.getenv("MAX_CONCURRENT_DECODES", "3"))

# Per-IP fixed-window rate limit on the expensive POST endpoints. Coarse
# abuse/DoS brake for the single public container; env-tunable.
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "30"))
RATE_LIMIT_WINDOW_SECONDS = float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMITED_PATHS = {"/api/analyze", "/api/analyze-study", "/api/generate-report",
                      "/api/compare", "/api/completeness-check", "/api/feedback",
                      "/api/dicom-view", "/api/dicom-view-series", "/api/dicom-raw",
                      "/api/dicom-roi", "/api/segment", "/api/mr-segment",
                      "/api/ct-detect", "/api/mr-detect"}
# GET endpoints that expose stored results by id — throttle to blunt enumeration.
# The segment/detect job poll GETs + the hires-localizer GET live under these prefixes.
RATE_LIMITED_PREFIXES = ("/api/analysis/", "/api/segment/", "/api/mr-segment/",
                         "/api/ct-detect/", "/api/mr-detect/", "/api/localize-hires/")

# Number of trusted reverse-proxy hops in front of the app (HF Spaces = 1). The
# client IP is read as the Nth-from-right X-Forwarded-For entry, so a client-
# supplied leftmost XFF can't spoof past the rate limiter.
TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "1"))

# DICOM de-identification: scrub direct identifiers + regenerate UIDs at ingest.
DEIDENTIFY_DICOM = os.getenv("DEIDENTIFY_DICOM", "1").strip().lower() in ("1", "true", "yes", "on")

# Data minimization: purge stored uploads/heatmaps/analysis older than this many
# seconds (ephemeral demo; disk is not a durability or security control).
STORAGE_TTL_SECONDS = int(os.getenv("STORAGE_TTL_SECONDS", str(6 * 3600)))

# Shared access-code gate. When ACCESS_CODE is set, any request whose path starts
# with one of ACCESS_CODE_PROTECTED_PREFIXES must send it (header X-Access-Code or
# ?access_code=). Empty ACCESS_CODE => gate disabled (open demo). PHI-adjacent
# features (camera/demographics/ingestion) register their prefixes here.
ACCESS_CODE = os.getenv("ACCESS_CODE", "").strip()
ACCESS_CODE_PROTECTED_PREFIXES = tuple(
    p.strip() for p in os.getenv("ACCESS_CODE_PROTECTED_PREFIXES", "").split(",") if p.strip()
)

# Interactive API docs (/docs, /redoc, /openapi.json) enumerate every endpoint +
# schema. Off by default on the public deploy; enable for local dev.
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "0").strip().lower() in ("1", "true", "yes", "on")

# CORS. Comma-separated env override; defaults to local dev. On the single-origin
# deploy this is moot (same host); set it if the frontend is split to another host.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if o.strip()
]

# Chest X-ray is the only analyzed modality; these DICOM Modality codes are the
# radiograph types the chest model may score. Anything else is refused, not
# silently run through the wrong model. "OT" (Other/Secondary-Capture) is
# deliberately EXCLUDED: an "OT" DICOM is an unknown/derived object (screenshots,
# scanned documents, secondary captures) and must NOT be scored as a chest film —
# it routes to the viewer instead (FIX #5, routing/OOD hole).
CXR_MODALITIES = {"CR", "DX", "RG"}

# --- Self-audit / abstention gate ("knows when to shut up") -----------------
# A composite out-of-distribution / quality score decides READ / DOWN-WEIGHT /
# ABSTAIN so the model refuses non-chest-radiograph input (a knee film, a CT
# slice, a photo of a dog) BEFORE scoring, rather than emitting confident
# nonsense. Fails safe and is cheaper on refusal.
SELF_AUDIT_ENABLED = os.getenv("SELF_AUDIT_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
# Use the TorchXRayVision autoencoder reconstruction error as the strong OOD
# signal (downloads a small extra model once). If it fails to load, the gate
# degrades to heuristics only and never hard-ABSTAINs on the AE signal alone.
SELF_AUDIT_AE = os.getenv("SELF_AUDIT_AE", "1").strip().lower() in ("1", "true", "yes", "on")
# ood_score in [0,1]; higher = less like a frontal CXR. Tuned empirically below.
OOD_CAUTION_THRESHOLD = float(os.getenv("OOD_CAUTION_THRESHOLD", "0.5"))
OOD_ABSTAIN_THRESHOLD = float(os.getenv("OOD_ABSTAIN_THRESHOLD", "0.75"))
# Autoencoder reconstruction-MSE mapped through these bounds to [0,1]. Calibrated
# empirically: real CXRs measured ~0.001-0.012; only high-frequency non-CXR
# garbage (noise/checkerboard) exceeds ~0.02, so the AE is a WEAK secondary
# signal (it can't catch smooth non-CXR images) and never hard-ABSTAINs alone.
AE_ERR_LOW = float(os.getenv("AE_ERR_LOW", "0.015"))
AE_ERR_HIGH = float(os.getenv("AE_ERR_HIGH", "0.15"))
# Color saturation is the STRONG, cheap OOD signal: X-rays are grayscale, so a
# color photo/screenshot/selfie is almost certainly not a radiograph. Mean
# per-pixel saturation above this => treat as color (non-CXR).
COLOR_SAT_OOD = float(os.getenv("COLOR_SAT_OOD", "0.12"))

DISCLAIMER = (
    "For decision support only — not a diagnosis. This tool assists a qualified "
    "clinician by drafting reports and highlighting regions for review. All outputs, "
    "including highlighted regions and suggested differentials, are AI-generated and "
    "may be incorrect. They must be reviewed, corrected, and approved by a licensed "
    "radiologist before any use. This software is a non-clinical demonstration "
    "prototype; it is not FDA-cleared and is not a medical device."
)

# ============================================================================
# Anatomy segmentation overlay (opt-in, NON-DIAGNOSTIC AI) — CT & MRI
# ============================================================================
# HARD RULE (from CT_UI_DESIGN.md / MRI_UI_DESIGN.md): this overlay LABELS/SEGMENTS
# anatomy and MEASURES regions ONLY. It never detects, characterizes, or excludes
# disease. The response schema is taboo-free by construction (models/segment.py),
# the endpoints live in a SEPARATE router (routers/segment.py) so the viewer stays
# model-free-by-construction, and both are OFF by default.
#
# Ship-now baseline is REAL, CPU-instant, and adds ZERO heavy deps: deterministic
# classical HU-threshold tissue labeling (CT) and intensity-cluster/skull-strip
# labeling (MR). Heavy models (TotalSegmentator/SynthSeg) are a PLUGGABLE seam that
# is designed + wired but NOT installed; the provider self-gates to classical-only
# when the optional import is missing (like localizer.available()).
SEGMENT_ENABLED = os.getenv("SEGMENT_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
MR_SEGMENT_ENABLED = os.getenv("MR_SEGMENT_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
# classical (default, always available) | totalseg (heavy, requirements-segment.txt only)
SEGMENT_MODEL = os.getenv("SEGMENT_MODEL", "classical").strip().lower()

# Which DICOM Modality codes each endpoint accepts (hard header-only guard so a
# head CT can never be silently MR-segmented and vice versa).
SEGMENT_MODALITIES = {"CT"}
MR_SEGMENT_MODALITIES = {"MR"}

# Ingest/compute bounds (mirror the viewer's VIEW_MAX_* DoS guards).
SEGMENT_MAX_FILES = int(os.getenv("SEGMENT_MAX_FILES", "300"))
SEGMENT_MAX_SLICES = int(os.getenv("SEGMENT_MAX_SLICES", "200"))
SEGMENT_MAX_TOTAL_BYTES = int(os.getenv("SEGMENT_MAX_TOTAL_MB", "300")) * 1024 * 1024
SEGMENT_MAX_EDGE = int(os.getenv("SEGMENT_MAX_EDGE", "256"))  # in-plane downscale before retain
SEGMENT_MAX_VOXELS = int(os.getenv("SEGMENT_MAX_VOXELS", str(64_000_000)))
SEGMENT_MAX_STRUCTURES = int(os.getenv("SEGMENT_MAX_STRUCTURES", "64"))
SEGMENT_TIMEOUT_SECONDS = float(os.getenv("SEGMENT_TIMEOUT_SECONDS", "600"))
SEGMENT_MAX_CONCURRENT_JOBS = 1  # a minutes-long, multi-GB job never fans out
# Bounded queue. Each queued job's closure holds its raw upload bytes in memory until
# it runs, so keep this small (queue_max * SEGMENT_MAX_TOTAL_BYTES is the worst-case
# resident raw-upload memory) to avoid an OOM DoS on a small Space.
SEGMENT_QUEUE_MAX = int(os.getenv("SEGMENT_QUEUE_MAX", "3"))
SEGMENT_JOB_TTL_SECONDS = int(os.getenv("SEGMENT_JOB_TTL_SECONDS", str(STORAGE_TTL_SECONDS)))
# Heavy-provider run flags (only used when SEGMENT_MODEL=totalseg + installed).
SEGMENT_FAST = os.getenv("SEGMENT_FAST", "1").strip().lower() in ("1", "true", "yes", "on")
SEGMENT_ML = os.getenv("SEGMENT_ML", "1").strip().lower() in ("1", "true", "yes", "on")
SEGMENT_STATISTICS = os.getenv("SEGMENT_STATISTICS", "1").strip().lower() in ("1", "true", "yes", "on")
# Dedicated (stricter) per-IP launch limiter for the two segment POSTs — a run is
# minutes long and multi-GB, so launches get their own budget (poll GETs stay on
# the generic prefix limiter).
SEGMENT_RATE_LIMIT_MAX = int(os.getenv("SEGMENT_RATE_LIMIT_MAX", "6"))
SEGMENT_RATE_LIMIT_WINDOW_SECONDS = float(os.getenv("SEGMENT_RATE_LIMIT_WINDOW_SECONDS", "60"))

# --- License + anatomy whitelist (fail-closed on BOTH axes) -----------------
# A model/task may be invoked ONLY if it is commercial_ok AND anatomy_only. This
# blocks BOTH non-commercial weights (e.g. brain_aneurysm CC-BY-NC) AND Apache-clean
# but DISEASE-SHAPED "trap" tasks (lung_nodules/liver_lesions/cerebral_bleed — they
# segment a *candidate lesion*, which reads as detection). Snapshot 2026-07; re-audit
# each weight's LICENSE on any version bump. `classical` needs no weights and is
# always allowed. Env TOTALSEG_TASK_WHITELIST may only INTERSECT (never widen) this.
MODEL_REGISTRY: dict[str, dict] = {
    # Always-available, weight-free classical baselines.
    "classical-hu-threshold": {"license": "no-model (scipy/numpy BSD-3-Clause)", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "classical-mr-intensity": {"license": "no-model (scipy/numpy/scikit-image BSD-3-Clause)", "commercial_ok": True, "anatomy_only": True, "modality": "MR"},
    # TotalSegmentator v2 CT tasks — Apache-2.0 weights, anatomy-only (SHIP).
    "total": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "body": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "lung_vessels": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "liver_vessels": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "liver_segments": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "hip_implant": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "kidney_cysts": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "breasts": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "head_glands_cavities": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "headneck_bones_vessels": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "trunk_cavities": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    "ventricle_parts": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "CT"},
    # TotalSegmentator MR tasks — Apache-2.0, anatomy-only (SHIP, MR).
    "total_mr": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "MR"},
    "body_mr": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "MR"},
    "vertebrae_mr": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "MR"},
    # SynthSeg standalone — Apache-2.0 weights, brain anatomy labeling (SHIP, MR).
    "synthseg": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": True, "modality": "MR"},
    # --- Apache-clean but DISEASE-SHAPED "trap" tasks: commercial_ok, NOT anatomy_only => BLOCKED.
    "cerebral_bleed": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": False, "modality": "CT"},
    "lung_nodules": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": False, "modality": "CT"},
    "liver_lesions": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": False, "modality": "CT"},
    "pleural_pericard_effusion": {"license": "Apache-2.0", "commercial_ok": True, "anatomy_only": False, "modality": "CT"},
    # --- NON-COMMERCIAL weights: commercial_ok False => BLOCKED regardless of anatomy.
    "brain_aneurysm": {"license": "CC-BY-NC-4.0", "commercial_ok": False, "anatomy_only": False, "modality": "CT"},
    "tissue_types": {"license": "non-commercial", "commercial_ok": False, "anatomy_only": True, "modality": "CT"},
    "tissue_types_mr": {"license": "non-commercial", "commercial_ok": False, "anatomy_only": True, "modality": "MR"},
    "tissue_4_types": {"license": "non-commercial", "commercial_ok": False, "anatomy_only": True, "modality": "CT"},
    "heartchambers_highres": {"license": "non-commercial", "commercial_ok": False, "anatomy_only": True, "modality": "CT"},
    "coronary_arteries": {"license": "non-commercial", "commercial_ok": False, "anatomy_only": True, "modality": "CT"},
    "appendicular_bones": {"license": "non-commercial", "commercial_ok": False, "anatomy_only": True, "modality": "CT"},
    "vertebrae_body": {"license": "non-commercial", "commercial_ok": False, "anatomy_only": True, "modality": "CT"},
    "face": {"license": "non-commercial", "commercial_ok": False, "anatomy_only": True, "modality": "CT"},
}

# Derived: the tasks actually invokable — commercial AND anatomy-only. Env may only
# narrow (intersect) this set, never widen it.
_ALLOWED = frozenset(
    name for name, m in MODEL_REGISTRY.items() if m["commercial_ok"] and m["anatomy_only"]
)
# The weight-free classical baselines are ALWAYS available and must never be removed
# by an env whitelist meant to narrow the HEAVY task set — otherwise narrowing the
# whitelist would 503/403 the shipped default overlay. They are exempt from narrowing.
_CLASSICAL_MODELS = frozenset({"classical-hu-threshold", "classical-mr-intensity"})
_env_wl = {s.strip() for s in os.getenv("TOTALSEG_TASK_WHITELIST", "").split(",") if s.strip()}
TOTALSEG_TASK_WHITELIST = (
    frozenset((_env_wl & _ALLOWED) | _CLASSICAL_MODELS) if _env_wl else _ALLOWED
)
# CLEAN SPDX-ish license ids the schema will accept on a Region.license field.
CLEAN_LICENSES = frozenset({
    "Apache-2.0", "MIT", "BSD-3-Clause", "CC-BY-4.0",
    "no-model (scipy/numpy BSD-3-Clause)", "no-model (scipy/numpy/scikit-image BSD-3-Clause)",
})


class ModelNotAllowed(Exception):
    """A model/task is not commercial-clean and anatomy-only — fail closed."""


def assert_task_allowed(task: str) -> None:
    """Raise ModelNotAllowed unless `task` is registered, commercial_ok, anatomy_only,
    AND in the (possibly env-narrowed) whitelist. Fail-closed on unknown names — a
    task not in the registry can never run. Call this FIRST, before any weight loads."""
    m = MODEL_REGISTRY.get(task)
    if m is None:
        raise ModelNotAllowed(f"segmentation task '{task}' is not in the model registry (fail-closed)")
    if not m["commercial_ok"]:
        raise ModelNotAllowed(f"segmentation task '{task}' has a non-commercial weight license ({m['license']})")
    if not m["anatomy_only"]:
        raise ModelNotAllowed(f"segmentation task '{task}' is disease-shaped, not anatomy-only (blocked)")
    # The weight-free classical baselines are always available (they are the shipped
    # default and load no weights), so the HEAVY-task whitelist can never disable them.
    if task in _CLASSICAL_MODELS:
        return
    if task not in TOTALSEG_TASK_WHITELIST:
        raise ModelNotAllowed(f"segmentation task '{task}' is not in the active whitelist")


def assert_model_allowed(name: str) -> None:
    """Same fail-closed gate keyed on a model name (alias of assert_task_allowed for
    the classical + heavy providers that self-identify by model name)."""
    assert_task_allowed(name)


# --- Overlay disclaimer + microcopy (verbatim; rendered ONLY while overlay is ON) ---
CT_OVERLAY_DISCLAIMER = (
    "AI anatomy overlay — computed organ regions, not a diagnosis. These outlines "
    "label anatomy only; they do not detect, characterize, or exclude any disease, "
    "injury, or abnormality. Approximate and frequently wrong at boundaries — a "
    "qualified reader must verify every region before any use. Research/education "
    "prototype; not FDA-cleared, not CE-marked, not a medical device."
)
MR_OVERLAY_DISCLAIMER = (
    "AI anatomy overlay (MR) — computed anatomical regions, not a diagnosis. These "
    "outlines label anatomy only; they do not detect, characterize, or exclude any "
    "disease, injury, or abnormality. MR signal is arbitrary (a.u.) and not "
    "quantitative — no intensity shown is tissue-specific, and any region volume is "
    "a geometric estimate from voxel spacing, not a measure of disease. Approximate "
    "and frequently wrong at boundaries — a qualified reader must verify every region "
    "before any use. Research/education prototype; not FDA-cleared, not CE-marked, "
    "not a medical device."
)
OVERLAY_TOGGLE_LABEL = "Anatomy overlay (AI) — approximate, verify"
OVERLAY_CAPTION = "Computed region · not a finding"
OVERLAY_VOLUME_FMT = "≈ {n} mL (auto — confirm)"
OVERLAY_HOVER_FIRSTUSE = "This does not look for disease."
OVERLAY_BANNER_ON = (
    "Anatomy overlay ON — labels anatomy only; it does not look for disease. Every "
    "region is model-generated and must be verified."
)

# ============================================================================
# Research CADe — disease-CANDIDATE detection on CT/MRI (UNVALIDATED, opt-in)
# ============================================================================
# This is the OPPOSITE of the anatomy overlay: it intentionally surfaces disease-
# shaped CANDIDATE regions (e.g. "candidate pulmonary nodule"). It is therefore
# gated far more strictly and framed as RESEARCH ONLY:
#   * opt-in, default OFF (CT_DETECT_ENABLED);
#   * an abstain gate refuses inappropriate input BEFORE detecting;
#   * every candidate is labelled UNVALIDATED, "not a diagnosis", "confirm with a
#     licensed radiologist", carried on a mandatory research disclaimer;
#   * the score is a detector score, NEVER a validated probability of disease;
#   * human confirm/dismiss feedback is recorded (the training signal).
# Ship-now detectors are CLASSICAL, deterministic, CPU-instant (numpy/scipy). Heavy
# pretrained models (TotalSegmentator lung_nodules/liver_lesions/cerebral_bleed —
# Apache-2.0 weights) are the same pluggable seam, installed only on GPU deploys.
CT_DETECT_ENABLED = os.getenv("CT_DETECT_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
MR_DETECT_ENABLED = os.getenv("MR_DETECT_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
# Research framing is ALWAYS on for this path — it cannot be turned into a device claim.
DETECT_RESEARCH_ONLY = True
DETECT_MAX_CANDIDATES = int(os.getenv("DETECT_MAX_CANDIDATES", "40"))
# Detector score below which a candidate is dropped (keeps the list reviewable).
DETECT_MIN_SCORE = float(os.getenv("DETECT_MIN_SCORE", "0.35"))

# Machine-readable "absence is not normality" guarantee. This travels ON the API
# response (detect + report), so a second UI or any consumer that reads
# candidate_count==0 cannot programmatically treat it as a negative/normal read.
# The non-claim must live in the contract, not only in a frontend string.
DETECT_NOT_NORMAL_MESSAGE = (
    "Absence of candidates is NOT a normal or negative result. This research detector "
    "is unvalidated, has no measured accuracy, and may miss real disease. Only a "
    "licensed radiologist reading the full study can determine normality."
)

# Registry of research candidate DETECTORS (disease-shaped by design — separate from
# the anatomy MODEL_REGISTRY). Each is commercial-license-clean; `validated` is False
# for all of them (no clinical validation has been performed) so the UI can never
# imply otherwise.
DETECTOR_REGISTRY: dict[str, dict] = {
    "classical-lung-nodule-cade": {
        "license": "no-model (scipy/numpy BSD-3-Clause)", "commercial_ok": True,
        "kind": "pulmonary nodule", "modality": "CT", "validated": False,
        "available": True},
    "classical-hyperdensity-cade": {
        "license": "no-model (scipy/numpy BSD-3-Clause)", "commercial_ok": True,
        "kind": "hyperdensity (e.g. haemorrhage/calcification)", "modality": "CT",
        "validated": False, "available": True},
    "classical-calcification-cade": {
        "license": "no-model (scipy/numpy BSD-3-Clause)", "commercial_ok": True,
        "kind": "calcification", "modality": "CT", "validated": False, "available": True},
    "classical-effusion-cade": {
        "license": "no-model (scipy/numpy BSD-3-Clause)", "commercial_ok": True,
        "kind": "pleural fluid collection", "modality": "CT", "validated": False,
        "available": True},
    "classical-pneumothorax-cade": {
        "license": "no-model (scipy/numpy BSD-3-Clause)", "commercial_ok": True,
        "kind": "intrathoracic air (possible pneumothorax)", "modality": "CT",
        "validated": False, "available": True},
    "classical-mr-hyperintensity-cade": {
        "license": "no-model (scipy/numpy/scikit-image BSD-3-Clause)", "commercial_ok": True,
        "kind": "relative hyperintensity", "modality": "MR", "validated": False,
        "available": True},
    # Heavy pluggable seam (Apache-2.0 weights; NOT installed on the CPU box).
    "lung_nodules": {"license": "Apache-2.0", "commercial_ok": True,
                     "kind": "pulmonary nodule", "modality": "CT", "validated": False,
                     "available": False},
    "cerebral_bleed": {"license": "Apache-2.0", "commercial_ok": True,
                       "kind": "intracranial haemorrhage", "modality": "CT",
                       "validated": False, "available": False},
    "liver_lesions": {"license": "Apache-2.0", "commercial_ok": True,
                      "kind": "liver lesion", "modality": "CT", "validated": False,
                      "available": False},
}


class DetectorNotAllowed(Exception):
    """A research detector is not registered / not commercial-clean — fail closed."""


def assert_detector_allowed(name: str) -> None:
    """Fail closed unless `name` is a registered, commercial-license-clean research
    detector. (Kept separate from assert_task_allowed: research detectors are
    intentionally disease-shaped, so the anatomy `anatomy_only` gate does not apply —
    the RESEARCH framing + disclaimers are what keep them defensible.)"""
    d = DETECTOR_REGISTRY.get(name)
    if d is None:
        raise DetectorNotAllowed(f"detector '{name}' is not registered (fail-closed)")
    if not d["commercial_ok"]:
        raise DetectorNotAllowed(f"detector '{name}' is not commercial-license-clean")


# Mandatory research disclaimer carried on EVERY candidate response.
CT_DETECT_DISCLAIMER = (
    "RESEARCH USE ONLY — UNVALIDATED. These are AI-generated CANDIDATE regions, NOT a "
    "diagnosis. This detector has NOT been clinically validated, is NOT FDA-cleared or "
    "CE-marked, and is NOT a medical device. It may miss real disease and flag normal "
    "anatomy. Every candidate must be reviewed and confirmed by a licensed radiologist "
    "before any use. Scores are detector confidence, NOT a probability of disease."
)
CT_DETECT_TOGGLE_LABEL = "Candidate findings (AI) — RESEARCH, unvalidated"
CT_DETECT_CANDIDATE_CAPTION = "Unvalidated candidate — radiologist must confirm"
MR_DETECT_DISCLAIMER = (
    "RESEARCH USE ONLY — UNVALIDATED. AI-generated CANDIDATE regions on MR, NOT a "
    "diagnosis. MR signal is arbitrary (a.u.), so candidates are RELATIVE outliers vs "
    "the image's own tissue signal — never an absolute or tissue-specific claim. This "
    "detector has NOT been clinically validated, is NOT a medical device, may miss real "
    "disease and flag normal anatomy, and every candidate must be confirmed by a "
    "licensed radiologist. Scores are detector confidence, NOT a probability of disease."
)
