"""Lightweight security middleware for the public deployment.

Dependency-light (Starlette only, already a FastAPI transitive dep):
  * RateLimitMiddleware — thread-safe in-memory per-IP fixed-window limiter on
    the expensive POST endpoints and the id-enumeration GETs, returning 429.
  * SecurityHeadersMiddleware — conservative response headers (CSP, HSTS, ...).
  * AccessCodeMiddleware — optional shared access code gating PHI-adjacent paths.

Rate-limit state is per-process/in-memory, correct for the single free Space
container. Behind multiple workers/replicas each keeps its own counter (limit
multiplies) — swap in a shared store at that point.
"""

import secrets
import threading
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from . import config


def client_ip(request) -> str:
    """Real client IP, robust against a spoofed leftmost X-Forwarded-For.

    A trusted reverse proxy appends the true peer to the RIGHT of any client-
    supplied XFF, so we read the Nth-from-right entry (N = trusted hops). This
    stops an attacker rotating fake leftmost IPs to slip past the rate limiter.
    """
    peer = request.client.host if request.client else "unknown"
    hops = config.TRUSTED_PROXY_HOPS
    # Only honor XFF when we actually sit behind >=1 trusted proxy. With hops<=0 the
    # whole header is attacker-supplied, so ignore it and use the direct peer — else an
    # attacker could rotate XFF per request to defeat every per-IP throttle.
    if hops > 0:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                return parts[-min(hops, len(parts))]
    return peer


def _is_rate_limited(method: str, path: str) -> bool:
    if method == "POST" and path in config.RATE_LIMITED_PATHS:
        return True
    return path.startswith(config.RATE_LIMITED_PREFIXES)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._lock = threading.Lock()
        self._hits: dict[str, tuple[float, int]] = {}  # ip -> (window_start, count)

    async def dispatch(self, request, call_next):
        if _is_rate_limited(request.method, request.url.path):
            ip = client_ip(request)
            now = time.time()
            window = config.RATE_LIMIT_WINDOW_SECONDS
            limit = config.RATE_LIMIT_MAX
            retry_after = 0
            with self._lock:
                start, count = self._hits.get(ip, (now, 0))
                if now - start >= window:
                    start, count = now, 0
                count += 1
                self._hits[ip] = (start, count)
                over_limit = count > limit
                if over_limit:
                    retry_after = int(window - (now - start)) + 1
                if len(self._hits) > 4096:
                    stale = [k for k, (s, _) in self._hits.items() if now - s >= window]
                    for k in stale:
                        self._hits.pop(k, None)
            if over_limit:
                return JSONResponse(
                    {"detail": "Rate limit exceeded. Please slow down and retry shortly."},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)


class SegmentLaunchLimitMiddleware(BaseHTTPMiddleware):
    """Dedicated, STRICTER per-IP fixed-window limiter for the two segmentation POST
    launches (/api/segment, /api/mr-segment). A segmentation run is minutes-long and
    multi-GB, so launches get their own small budget separate from the generic
    RATE_LIMITED_PATHS bucket; the ~seconds poll GETs stay on the generic prefix
    limiter. Same in-memory posture as RateLimitMiddleware."""

    _LAUNCH_PATHS = ("/api/segment", "/api/mr-segment", "/api/ct-detect", "/api/mr-detect")

    def __init__(self, app):
        super().__init__(app)
        self._lock = threading.Lock()
        self._hits: dict[str, tuple[float, int]] = {}

    async def dispatch(self, request, call_next):
        if request.method == "POST" and request.url.path in self._LAUNCH_PATHS:
            ip = client_ip(request)
            now = time.time()
            window = config.SEGMENT_RATE_LIMIT_WINDOW_SECONDS
            limit = config.SEGMENT_RATE_LIMIT_MAX
            over_limit = False
            retry_after = 0
            with self._lock:
                start, count = self._hits.get(ip, (now, 0))
                if now - start >= window:
                    start, count = now, 0
                count += 1
                self._hits[ip] = (start, count)
                over_limit = count > limit
                if over_limit:
                    retry_after = int(window - (now - start)) + 1
                if len(self._hits) > 4096:
                    stale = [k for k, (s, _) in self._hits.items() if now - s >= window]
                    for k in stale:
                        self._hits.pop(k, None)
            if over_limit:
                return JSONResponse(
                    {"detail": "Too many segmentation runs. Please wait before retrying."},
                    status_code=429, headers={"Retry-After": str(retry_after)})
        return await call_next(request)


class AccessCodeMiddleware(BaseHTTPMiddleware):
    """Gate PHI-adjacent paths behind a shared access code (when configured).

    No-op unless config.ACCESS_CODE is set AND the request path starts with a
    configured protected prefix. The core CXR demo stays open; demographics /
    camera / ingestion register their prefixes so those surfaces require the code.
    """

    async def dispatch(self, request, call_next):
        code = config.ACCESS_CODE
        prefixes = config.ACCESS_CODE_PROTECTED_PREFIXES
        if code and prefixes and request.url.path.startswith(prefixes):
            # Header ONLY — a ?access_code= query param would write the shared
            # secret into proxy/access logs and browser history.
            supplied = request.headers.get("x-access-code") or ""
            if not secrets.compare_digest(supplied, code):  # constant-time
                return JSONResponse(
                    {"detail": "This feature requires a valid access code."},
                    status_code=401)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Strict-Transport-Security",
                                "max-age=31536000; includeSubDomains")
        # Self-hosted SPA: allow same-origin assets + inline styles (Vite); images
        # incl. data: URIs (heatmaps/PDF); connect same-origin. No third-party.
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'self'; form-action 'self'; frame-src 'none'")
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        # microphone (dictation) + camera (capture) stay enabled same-origin.
        resp.headers.setdefault(
            "Permissions-Policy", "microphone=(self), camera=(self), geolocation=()")
        return resp
