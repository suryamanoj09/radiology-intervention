import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import auth, config
from .routers import (analyze, compare, ct_report, detect, feedback, report,
                      segment, study, viewer)
from .security import (AccessCodeMiddleware, RateLimitMiddleware,
                       SecurityHeadersMiddleware, SegmentLaunchLimitMiddleware)
from .services import self_audit, storage, vision_xray

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the model at startup so the first upload isn't a multi-second cold stall.
    try:
        vision_xray.warm_up()
        self_audit.warm_up()
        from .services import anatomy, localizer, seg_store
        anatomy.warm_up()
        localizer.warm_up()  # no-op unless LOCALIZER_WEIGHTS is set
        seg_store.warm_up()  # no-op unless segmentation is enabled
        logger.info("Vision + self-audit + anatomy models warmed up.")
    except Exception:
        logger.exception("Model warm-up failed; will load lazily on first request.")
    try:
        storage.start_sweeper()
    except Exception:
        logger.exception("Storage sweeper failed to start.")
    yield


app = FastAPI(
    title="RadAssist API",
    description="AI radiology decision-support backend. AI drafts; a licensed clinician reviews and approves.",
    version="0.2.0",
    lifespan=lifespan,
    # Public API docs enumerate every endpoint/schema — off unless explicitly enabled.
    docs_url="/docs" if config.ENABLE_DOCS else None,
    redoc_url="/redoc" if config.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if config.ENABLE_DOCS else None,
)

# Starlette wraps middleware in reverse registration order, so the middleware
# added LAST is outermost. Register the security middlewares first and CORS
# last, so CORS stays outermost and can attach its headers to every response —
# including a 429 emitted by the rate limiter — when the frontend is on a
# separate origin.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SegmentLaunchLimitMiddleware)  # stricter per-IP budget for seg launches
app.add_middleware(AccessCodeMiddleware)
app.add_middleware(auth.AuthMiddleware)  # gates PHI-adjacent paths when AUTH_ENABLED
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(analyze.router)
app.include_router(report.router)
app.include_router(compare.router)
app.include_router(study.router)
app.include_router(feedback.router)
app.include_router(viewer.router)  # CT/MRI model-free viewer (no AI)
app.include_router(segment.router)  # opt-in, non-diagnostic anatomy-overlay (default off)
app.include_router(detect.router)   # opt-in RESEARCH CADe: disease candidates (default off)
app.include_router(ct_report.router)  # CT/MRI research report (confirmed candidates + measurements)

# Only images/heatmaps/segment-masks are public. Analysis JSON lives in
# config.ANALYSIS_DIR, which is deliberately NOT mounted here.
app.mount("/static/uploads", StaticFiles(directory=config.UPLOADS_DIR), name="uploads")
app.mount("/static/heatmaps", StaticFiles(directory=config.HEATMAPS_DIR), name="heatmaps")
app.mount("/static/segments", StaticFiles(directory=config.SEGMENTS_DIR), name="segments")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "llm_provider": config.LLM_PROVIDER,
        "llm_key_present": bool(
            (config.LLM_PROVIDER == "gemini" and config.GEMINI_API_KEY)
            or (config.LLM_PROVIDER == "groq" and config.GROQ_API_KEY)
            or config.LLM_PROVIDER == "ollama"
        ),
        "report_default": "template" if config.LLM_PROVIDER == "none"
        or not (config.GEMINI_API_KEY or config.GROQ_API_KEY or config.LLM_PROVIDER == "ollama")
        else config.LLM_PROVIDER,
        "disclaimer": config.DISCLAIMER,
    }


# Serve the built React SPA from the SAME origin as the API. This mount MUST be
# registered LAST: FastAPI matches routes/mounts in registration order, so every
# /api router and the /static mounts above still win, and this only catches
# everything else. html=True serves index.html for unknown paths (client-side
# routing). Guarded so local dev (no build present) runs API-only without crashing.
_SPA_DIR = config.BASE_DIR / "frontend_dist"
if _SPA_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_SPA_DIR, html=True), name="spa")
    logger.info("Serving SPA from %s", _SPA_DIR)
else:
    logger.warning("SPA dir %s absent; API-only mode (local dev).", _SPA_DIR)
