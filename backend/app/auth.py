"""Dynamic login/logout for the public demo (dependency-light, stdlib-signed).

This is DEMO authentication, not a HIPAA identity system. It exists so the
PHI-adjacent surfaces (upload / analyze / report / compare / camera capture /
patient intake) can be gated behind a login on the single free CPU Space,
without an external IdP, extra services, or new Python dependencies.

How it works
------------
  * Credentials come from ENV only (never hardcoded). A user is a
    username + SHA-256 password hash. See _load_users().
  * On POST /api/login we verify the password and issue a compact session
    token: base64url(payload) + "." + base64url(HMAC-SHA256(secret, payload)).
    The payload is {"sub": user, "iat": ts, "exp": ts+ttl}. The server keeps
    NO session state — the signature is the trust anchor (stateless).
  * The token is delivered as an HttpOnly, SameSite, (optionally Secure) cookie
    so browser JS can never read it and it is sent automatically same-origin.
  * AuthMiddleware gates the configured protected path prefixes when auth is
    enabled; everything else (health, login, static SPA) stays open so the
    demo is still openable by default (AUTH_ENABLED=0).
  * get_current_user is an optional FastAPI dependency routers may use to read
    the signed identity for per-user features later — enforcement is the
    middleware's job, so no shared router files need editing.

Security notes / limits (documented honestly):
  * SHA-256 (unsalted) password hashing is weak vs. offline cracking but keeps
    zero new deps and no plaintext secret in code; acceptable for a demo login.
    Swap in bcrypt/argon2 for anything real.
  * Token state is in the signature only; there is no server-side revocation
    list. Logout clears the cookie; rotate SESSION_SECRET to invalidate all
    outstanding tokens at once.
  * Single-process, single-origin deploy: the login brute-force throttle is
    in-memory per-IP (same model as the rate limiter).
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Importing config runs load_dotenv(backend/.env) as a side effect. auth reads env
# at module load (below), and main.py imports `auth` before `config`, so without this
# a backend/.env (e.g. AUTH_DEMO_MODE=1) would not be applied to auth's config.
from . import config  # noqa: F401

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# --- Auth configuration (ENV only) -----------------------------------------
# Master switch. Default OFF so the core demo stays openable with no config.
AUTH_ENABLED = _env_bool("AUTH_ENABLED", "0")

# --- Demo login ------------------------------------------------------------
# AUTH_DEMO_MODE turns the auth GATE on with a seeded, DELIBERATELY-INSECURE demo
# credential that the login page then shows (+ a "fill" button), so anyone can
# experience the real login / 2FA flow without provisioning users. It intentionally
# does NOT trigger the production posture (see PROD_POSTURE below), so it keeps the
# open-demo convenience of an ephemeral signing key instead of fail-closing. The
# demo password is only ever revealed by /api/me when NO real users are configured.
# NEVER enable this in production.
AUTH_DEMO_MODE = _env_bool("AUTH_DEMO_MODE", "0")
DEMO_USERNAME = (os.getenv("AUTH_DEMO_USERNAME", "").strip() or "radiologist")
DEMO_PASSWORD = os.getenv("AUTH_DEMO_PASSWORD", "") or "RadAssist-Demo-2026"
# True when an operator configured real credentials (independent of the demo seed);
# gates whether /api/me may reveal the demo password.
_REAL_USERS_CONFIGURED = bool(
    os.getenv("AUTH_USERS", "").strip() or os.getenv("AUTH_USERNAME", "").strip())
# The real production switch, captured before demo mode folds into the gate.
_REAL_AUTH_ENABLED = AUTH_ENABLED
# Demo mode turns the gate on (login required) without a real production posture.
AUTH_ENABLED = AUTH_ENABLED or AUTH_DEMO_MODE

COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "radassist_session").strip()
# Secure cookie by default (HTTPS Space). Set SESSION_COOKIE_SECURE=0 for plain
# http local dev, otherwise the browser drops the cookie and login won't stick.
COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", "1")
# Lax is correct for the single-origin deploy (SPA + API same host). Use "none"
# only for a split-origin setup (also requires Secure + HTTPS on both ends).
COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "lax").strip().lower()
if COOKIE_SAMESITE not in ("lax", "strict", "none"):
    COOKIE_SAMESITE = "lax"

SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(12 * 3600)))
# Auto-logoff (HIPAA §164.312(a)(2)(iii)): sliding idle timeout. A session with no
# protected activity for this long is rejected even before the absolute TTL. The
# middleware refreshes the cookie on genuine activity, so active users stay in and
# idle ones are logged off. 0 disables the idle check.
SESSION_IDLE_TIMEOUT_SECONDS = int(os.getenv("SESSION_IDLE_TIMEOUT_SECONDS", str(15 * 60)))

# --- Secrets management: fail-closed on a weak SESSION_SECRET ---------------
# The HMAC signing key is the trust anchor for every session cookie. Shipping a
# default/blank/guessable key means an attacker can FORGE sessions, so in a
# production posture we FAIL CLOSED at startup rather than boot with a weak key.
#
#   * Production posture = AUTH_ENABLED=1 OR REQUIRE_STRONG_SECRETS=1 OR PROD=1.
#     If SESSION_SECRET is unset, a known dev-default, or too short, we RAISE with a
#     clear message so no deploy ever ships a default signing key.
#   * Open-demo posture (AUTH_ENABLED=0 and no prod flag) keeps the old convenience:
#     a per-process random EPHEMERAL key is minted with a one-time WARNING (sessions
#     don't survive a restart), so the zero-config demo still runs.
REQUIRE_STRONG_SECRETS = _env_bool("REQUIRE_STRONG_SECRETS", "0")
PROD = _env_bool("PROD", "0")
# Note: uses the REAL auth switch, not the demo-mode gate — AUTH_DEMO_MODE turns
# login on for a demo but must not force a fail-closed strong-secret requirement,
# so the zero-config demo login still boots with an ephemeral key.
PROD_POSTURE = _REAL_AUTH_ENABLED or REQUIRE_STRONG_SECRETS or PROD

# Minimum acceptable length for a configured secret in a production posture. 32 hex
# chars (128 bits) is the floor we generate; anything shorter is treated as weak.
SECRET_MIN_LENGTH = int(os.getenv("SESSION_SECRET_MIN_LENGTH", "32"))
# Known throwaway values that must never key a real deploy.
_WEAK_SECRETS = frozenset({
    "", "changeme", "change-me", "changethis", "change-this", "secret", "secretkey",
    "default", "dev", "devsecret", "development", "test", "testing", "password",
    "radassist", "radassist-dev", "please-change", "your-secret-here", "none",
})


def _is_weak_secret(secret: str) -> bool:
    """A secret is weak if it is blank, a known dev-default, or shorter than the floor."""
    s = (secret or "").strip()
    return (not s) or s.lower() in _WEAK_SECRETS or len(s) < SECRET_MIN_LENGTH


def _resolve_session_secret(raw: str, prod_posture: bool) -> tuple[str, bool]:
    """Resolve the effective signing secret. Returns (secret, is_ephemeral).

    Fail-closed: RAISES RuntimeError when the secret is weak AND we are in a production
    posture. In the open demo a weak/blank secret yields a per-process ephemeral one."""
    if _is_weak_secret(raw):
        if prod_posture:
            raise RuntimeError(
                "SESSION_SECRET is unset, a known dev-default, or shorter than "
                f"{SECRET_MIN_LENGTH} chars, but a production posture is active "
                "(AUTH_ENABLED/REQUIRE_STRONG_SECRETS/PROD). Refusing to start with a "
                "weak signing key. Set SESSION_SECRET to a strong random value, e.g. "
                "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"`.")
        return secrets.token_hex(32), True
    return raw.strip(), False


_SECRET, _SECRET_IS_EPHEMERAL = _resolve_session_secret(
    os.getenv("SESSION_SECRET", "").strip(), PROD_POSTURE)
if _SECRET_IS_EPHEMERAL:
    logger.warning(
        "SESSION_SECRET not set (or weak) — using an ephemeral signing key for the "
        "open demo. Logins will not survive a restart and differ per worker. Set a "
        "strong SESSION_SECRET for stable sessions; it is REQUIRED once AUTH_ENABLED=1.")
_SECRET_BYTES = _SECRET.encode("utf-8")

# Protected path prefixes (only enforced when AUTH_ENABLED). PHI-adjacent POSTs
# by default; login/logout/me + health + static SPA stay open.
_DEFAULT_PROTECTED = ("/api/analyze,/api/analyze-study,/api/generate-report,"
                      "/api/compare,/api/completeness-check,/api/dicom,"
                      "/api/localize-hires,/api/feedback,/api/analysis,"
                      "/api/segment,/api/mr-segment,/api/ct-detect,/api/mr-detect,"
                      # Admin session-management surface (list/revoke). Gated by the
                      # full session+CSRF middleware; the endpoints add a role==admin check.
                      "/api/admin,"
                      # Per-user account/session management (list own sessions, revoke,
                      # revoke-others) + 2FA disable. Gated by the full session+CSRF
                      # middleware exactly like /api/admin, so an unauthenticated (or
                      # half-authenticated / revoked) caller is rejected before the
                      # endpoint runs and every state-changing POST needs the CSRF token.
                      # NOTE: only /api/2fa/disable is protected here — /api/2fa/enroll and
                      # /api/2fa/verify must stay reachable by a half-authenticated (MFA-
                      # pending) session, so the broad /api/2fa prefix is deliberately NOT
                      # listed.
                      "/api/sessions,/api/2fa/disable,"
                      # Rendered PHI artifacts (patient slices / heatmaps / masks) — gate the
                      # payload too, not just the /api that creates it, so a leaked image URL
                      # is not an unauthenticated PHI fetch when AUTH_ENABLED.
                      "/static/uploads,/static/heatmaps,/static/segments")
PROTECTED_PREFIXES = tuple(
    p.strip() for p in os.getenv("AUTH_PROTECTED_PREFIXES", _DEFAULT_PROTECTED).split(",")
    if p.strip())

# Login brute-force throttle (per IP, in-memory).
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "10"))
LOGIN_WINDOW_SECONDS = float(os.getenv("LOGIN_WINDOW_SECONDS", "300"))

# Per-ACCOUNT lockout (in-memory): after this many CONSECUTIVE failed logins for a
# given username, that account is locked for LOGIN_LOCKOUT_SECONDS. A success resets
# the counter. Keyed on the submitted username string (existing OR not) so a locked
# 429 never reveals whether the account exists — it is orthogonal to enumeration,
# which is defended separately by the uniform message + always-run scrypt compare.
LOGIN_LOCKOUT_THRESHOLD = int(os.getenv("LOGIN_LOCKOUT_THRESHOLD", "5"))
LOGIN_LOCKOUT_SECONDS = float(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))

# --- CSRF (double-submit cookie) -------------------------------------------
# Cookie-authenticated state-changing requests must echo a CSRF token (readable
# cookie -> matching header). Only active when AUTH_ENABLED (it defends the cookie
# session); header/bearer/access-code auth is exempt (not a browser-cookie flow).
CSRF_ENABLED = _env_bool("CSRF_ENABLED", "1")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "radassist_csrf").strip()
CSRF_HEADER_NAME = os.getenv("CSRF_HEADER_NAME", "x-csrf-token").strip().lower()
# Methods that mutate state and therefore require a CSRF token under cookie auth.
_CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# --- Optional TOTP 2FA (RFC 6238, stdlib-only) ------------------------------
# Per-user, OPTIONAL. When a user has a CONFIRMED enrollment, a password-only login
# is incomplete until POST /api/2fa/verify succeeds (the session token carries an
# `mfa` claim only after that). Secrets are base32; a 30s step / 6 digits / SHA1 —
# the universal authenticator-app defaults so any TOTP app interoperates.
TOTP_ISSUER = os.getenv("TOTP_ISSUER", "RadAssist").strip() or "RadAssist"
TOTP_STEP_SECONDS = int(os.getenv("TOTP_STEP_SECONDS", "30"))
TOTP_DIGITS = int(os.getenv("TOTP_DIGITS", "6"))
# Accept the code for +/- this many steps to tolerate clock drift (1 => ~90s window).
TOTP_DRIFT_STEPS = int(os.getenv("TOTP_DRIFT_STEPS", "1"))


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Salted, memory-hard password hashing via stdlib scrypt (no new dependency —
# keeps this module dep-light while fixing the unsalted-SHA-256 weakness). Format:
# "scrypt$<salt_hex>$<dk_hex>". Legacy 64-char sha256 hashes are still accepted for
# backward compatibility (with a deprecation warning), so existing configs keep
# working while new credentials are salted+stretched.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt,
                          n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${_scrypt(password, salt).hex()}"


def _verify_password(password: str, stored: str) -> bool:
    stored = (stored or "").strip()
    if stored.startswith("scrypt$"):
        try:
            _, salt_hex, dk_hex = stored.split("$", 2)
            return hmac.compare_digest(_scrypt(password or "", bytes.fromhex(salt_hex)).hex(),
                                       dk_hex.lower())
        except Exception:
            return False
    if len(stored) == 64:  # legacy unsalted sha256 (deprecated)
        return hmac.compare_digest(_sha256_hex(password or ""), stored.lower())
    return False


def _load_users() -> dict[str, str]:
    """username -> sha256(password) hex, from ENV. No secrets in code.

    Two ways to configure, merged (AUTH_USERS wins on conflict):
      * AUTH_USERNAME + AUTH_PASSWORD_SHA256  (single-user convenience)
      * AUTH_USERS = "alice:<sha256hex>,bob:<sha256hex>"  (multi-user)
    As a LAST-RESORT dev convenience, AUTH_PASSWORD (plaintext env, never in
    code) is hashed at load with a warning. Prefer the *_SHA256 form.
    """
    users: dict[str, str] = {}

    single_user = os.getenv("AUTH_USERNAME", "").strip()
    single_hash = os.getenv("AUTH_PASSWORD_SHA256", "").strip().lower()
    single_plain = os.getenv("AUTH_PASSWORD", "")
    if single_user:
        if single_hash:
            users[single_user] = single_hash
        elif single_plain:
            logger.warning(
                "AUTH_PASSWORD is plaintext in the environment; prefer a pre-hashed "
                "credential. Hashing it at load with salted scrypt.")
            users[single_user] = hash_password(single_plain)

    for entry in os.getenv("AUTH_USERS", "").split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        name, _, h = entry.partition(":")
        name, h = name.strip(), h.strip().lower()
        if name and h:
            users[name] = h

    # Demo login: seed a clearly-insecure demo credential when AUTH_DEMO_MODE is on
    # (unless the operator already defined this username). Runs in the same in-memory
    # AND DB seeding path as real users, so the demo login works in both modes.
    if AUTH_DEMO_MODE and DEMO_USERNAME and DEMO_USERNAME not in users:
        users[DEMO_USERNAME] = _sha256_hex(DEMO_PASSWORD)

    return users


_USERS = _load_users()

if AUTH_DEMO_MODE and not _REAL_USERS_CONFIGURED:
    logger.warning(
        "AUTH_DEMO_MODE is ON — auth gate enabled with an INSECURE, published demo "
        "login (user %r). For demos only; NEVER production. Set real AUTH_USERS and "
        "AUTH_DEMO_MODE=0 for a real deployment.", DEMO_USERNAME)

# Usernames granted the `admin` role (session management). Comma-separated ENV, e.g.
# AUTH_ADMINS="alice,bob". In DB mode this seeds User.role='admin'; in the (DB-off)
# stateless demo it is consulted directly. Admin is the ONLY elevated role today.
AUTH_ADMINS = frozenset(
    n.strip() for n in os.getenv("AUTH_ADMINS", "").split(",") if n.strip())

if AUTH_ENABLED and not _USERS:
    logger.error(
        "AUTH_ENABLED=1 but no credentials configured (AUTH_USERNAME/"
        "AUTH_PASSWORD_SHA256 or AUTH_USERS). Every login will fail. "
        "Configure credentials or set AUTH_ENABLED=0 for the open demo.")


# --- TOTP enrollment store --------------------------------------------------
# username -> {"secret": <base32>, "confirmed": bool}. Seeded from ENV
# (AUTH_2FA_SECRETS="alice:BASE32,bob:BASE32" => already-confirmed) so enrollment
# survives a restart the same ENV-driven way the credentials do; runtime enrollments
# via /api/2fa/enroll live in-memory (a demo posture — mirror them into
# AUTH_2FA_SECRETS for durability, exactly like AUTH_USERS). Guarded by its own lock
# because /enroll and /verify mutate it concurrently with reads in verify paths.
_totp_lock = threading.Lock()


def _load_totp_secrets() -> dict[str, dict]:
    store: dict[str, dict] = {}
    for entry in os.getenv("AUTH_2FA_SECRETS", "").split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        name, _, secret = entry.partition(":")
        name, secret = name.strip(), secret.strip().upper().replace(" ", "")
        if name and secret:
            # ENV-provisioned secrets are treated as already CONFIRMED (an operator
            # opted the user in) so 2FA is enforced immediately on next login.
            store[name] = {"secret": secret, "confirmed": True}
    return store


_TOTP_SECRETS = _load_totp_secrets()


# --- DB-adapter seam (opt-in persistence) ----------------------------------
# When DATABASE_URL is set, users + 2FA enrollment live in the DB (via the storage
# adapter in services/store.py), SEEDED ONCE from the same ENV config the in-memory
# path reads — so an existing AUTH_USERS/AUTH_USERNAME + AUTH_2FA_SECRETS deployment
# keeps working AND runtime 2FA enrollments now survive a restart. When DATABASE_URL
# is UNSET every helper below takes its legacy `else` branch and behaviour is
# byte-for-byte the env/in-memory one: the DB layer stays fully dormant (no engine,
# no file, no query). Callers in this module route ALL user/2FA reads+writes through
# these helpers so neither branch's semantics leak to the login/2FA/session logic.
_seed_lock = threading.Lock()
_seeded_urls: set[str] = set()


def _ensure_db_ready() -> None:
    """Idempotently ensure the tables exist and the users table is seeded from ENV the
    first time a given DATABASE_URL is used. No-op when the DB is disabled. Seeding is
    emptiness-guarded, so it NEVER clobbers rows changed at runtime (it only fills a
    fresh, empty users table from the operator's ENV credentials)."""
    from . import db

    if not db.is_enabled():
        return
    url = db.database_url()
    if url in _seeded_urls:
        return
    with _seed_lock:
        if url in _seeded_urls:
            return
        from .services import store

        db.init_db()
        if not store.list_users():
            # Seed from the SAME env config the in-memory path uses, so a DB deploy
            # inherits AUTH_USERS/AUTH_USERNAME credentials and any ENV-provisioned
            # (already-confirmed) AUTH_2FA_SECRETS enrollments.
            env_totp = _load_totp_secrets()
            for name, h in _load_users().items():
                rec = env_totp.get(name)
                store.upsert_user(
                    name, h,
                    role=("admin" if name in AUTH_ADMINS else "user"),
                    twofa_secret=(rec or {}).get("secret"),
                    twofa_confirmed=bool(rec and rec.get("confirmed")))
        _seeded_urls.add(url)


def _user_password_hash(username: str) -> "str | None":
    """The stored password hash for a username, or None if unknown OR disabled. DB
    when enabled (seeded from ENV on first use); the ENV `_USERS` map otherwise. Both
    branches return None for a missing user so the enumeration-uniform dummy-hash burn
    in verify_credentials runs identically."""
    from . import db

    if db.is_enabled():
        _ensure_db_ready()
        from .services import store

        row = store.get_user(username or "")
        if not row or row.get("disabled"):
            return None
        return row.get("password_hash")
    return _USERS.get(username or "")


def _user_exists(username: str) -> bool:
    """Whether a username is a currently-valid (non-disabled) account. Used by
    verify_token to reject a token whose subject was removed/disabled since issue."""
    from . import db

    if db.is_enabled():
        _ensure_db_ready()
        from .services import store

        row = store.get_user(username or "")
        return bool(row) and not row.get("disabled")
    return (username or "") in _USERS


def _set_totp_enrollment(username: str, secret: "str | None", confirmed: bool) -> None:
    """Persist (or clear, when secret is None) a user's 2FA enrollment. DB when
    enabled (durable across restarts); the in-memory `_TOTP_SECRETS` dict otherwise."""
    from . import db

    if db.is_enabled():
        _ensure_db_ready()
        from .services import store

        store.set_twofa(username, secret, confirmed)
        return
    with _totp_lock:
        if secret is None:
            _TOTP_SECRETS.pop(username, None)
        else:
            _TOTP_SECRETS[username] = {"secret": secret, "confirmed": confirmed}


def _confirm_totp_enrollment(username: str) -> None:
    """Mark a user's EXISTING enrollment confirmed (first successful TOTP code). DB
    when enabled; the in-memory dict otherwise. No-op if there is no enrollment."""
    from . import db

    if db.is_enabled():
        _ensure_db_ready()
        from .services import store

        row = store.get_user(username or "")
        if row and row.get("twofa_secret"):
            store.set_twofa(username, row["twofa_secret"], True)
        return
    with _totp_lock:
        cur = _TOTP_SECRETS.get(username)
        if cur:
            cur["confirmed"] = True


def _new_totp_secret() -> str:
    # 20 random bytes -> 32 base32 chars, the RFC 4226/6238 recommended key length.
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_at(secret_b32: str, moment: float, step: int, digits: int) -> str:
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8), casefold=True)
    counter = int(moment // step)
    msg = counter.to_bytes(8, "big")
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return str(binary % (10 ** digits)).zfill(digits)


def verify_totp(secret_b32: str, code: str, at: float | None = None) -> bool:
    """Constant-time RFC 6238 check with +/- TOTP_DRIFT_STEPS tolerance. Never raises."""
    code = (code or "").strip().replace(" ", "")
    if not secret_b32 or not code or not code.isdigit():
        return False
    now = time.time() if at is None else at
    ok = False
    try:
        for drift in range(-TOTP_DRIFT_STEPS, TOTP_DRIFT_STEPS + 1):
            candidate = _totp_at(secret_b32, now + drift * TOTP_STEP_SECONDS,
                                 TOTP_STEP_SECONDS, TOTP_DIGITS)
            # Accumulate (no early break) so timing does not leak which step matched.
            if hmac.compare_digest(candidate, code):
                ok = True
    except Exception:
        return False
    return ok


def _otpauth_uri(username: str, secret_b32: str) -> str:
    from urllib.parse import quote
    issuer = quote(TOTP_ISSUER, safe="")
    label = quote(f"{TOTP_ISSUER}:{username}", safe="")
    return (f"otpauth://totp/{label}?secret={secret_b32}&issuer={issuer}"
            f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_STEP_SECONDS}")


def totp_enrollment(username: str) -> dict | None:
    from . import db

    if db.is_enabled():
        _ensure_db_ready()
        from .services import store

        row = store.get_user(username or "")
        if row and row.get("twofa_secret"):
            return {"secret": row["twofa_secret"],
                    "confirmed": bool(row.get("twofa_confirmed"))}
        return None
    with _totp_lock:
        rec = _TOTP_SECRETS.get(username or "")
        return dict(rec) if rec else None


def _totp_confirmed(username: str) -> bool:
    rec = totp_enrollment(username)
    return bool(rec and rec.get("confirmed"))


_DUMMY_HASH = hash_password("__radassist_dummy__")


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time credential check. Always runs a full hash (against a dummy for
    an unknown user) so timing doesn't leak whether the username exists."""
    expected = _user_password_hash(username)
    if expected is None:
        _verify_password(password or "", _DUMMY_HASH)  # burn equivalent time
        return False
    return _verify_password(password or "", expected)


# --- Stateless signed token -------------------------------------------------
def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def issue_token(username: str, abs_exp: int | None = None,
                mfa: bool = False, sid: str | None = None) -> str:
    # `iat` is LAST-ACTIVITY (refreshed each protected request for the sliding idle
    # window); `exp` is the ABSOLUTE cap, set once and preserved across refreshes.
    # `mfa` records that 2FA has been satisfied for this session; `sid` is a random
    # per-session id, REGENERATED on login and on 2FA completion (session-fixation
    # defence) and PRESERVED across idle refreshes.
    now = int(time.time())
    exp = int(abs_exp) if abs_exp else now + SESSION_TTL_SECONDS
    payload = {"sub": username, "iat": now, "exp": exp,
               "mfa": bool(mfa), "sid": sid or secrets.token_hex(8)}
    payload_b = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64u_encode(payload_b)
    sig = hmac.new(_SECRET_BYTES, body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64u_encode(sig)}"


def verify_token(token: str) -> dict | None:
    """Return the payload dict if the token is well-formed, unexpired, and the
    signature verifies; else None. Never raises."""
    if not token or "." not in token:
        return None
    try:
        body, _, sig_part = token.partition(".")
        expected_sig = hmac.new(_SECRET_BYTES, body.encode("ascii"), hashlib.sha256).digest()
        got_sig = _b64u_decode(sig_part)
        if not hmac.compare_digest(expected_sig, got_sig):
            return None
        payload = json.loads(_b64u_decode(body))
        now = int(time.time())
        if int(payload.get("exp", 0)) < now:  # absolute expiry
            return None
        if (SESSION_IDLE_TIMEOUT_SECONDS > 0
                and now - int(payload.get("iat", 0)) > SESSION_IDLE_TIMEOUT_SECONDS):
            return None  # idle timeout (auto-logoff)
        if not _user_exists(payload.get("sub") or ""):
            # User removed from config (or disabled) since issue -> reject.
            return None
        return payload
    except Exception:
        return None


def _mfa_satisfied(payload: dict) -> bool:
    """A session is 2FA-complete when the user has no CONFIRMED enrollment (2FA is
    optional) OR the token carries the `mfa` claim set at /2fa/verify time."""
    if not _totp_confirmed(payload.get("sub") or ""):
        return True
    return bool(payload.get("mfa"))


def _session_payload(request: Request) -> dict | None:
    """Full, fully-authenticated session payload (valid signature/expiry AND 2FA
    satisfied) — or None. This is the enforcement primitive the middleware uses."""
    payload = verify_token(request.cookies.get(COOKIE_NAME, ""))
    if payload is None or not _mfa_satisfied(payload):
        return None
    return payload


def current_user(request: Request) -> str | None:
    """The signed-in username from the session cookie, or None. Requires 2FA to be
    satisfied when the user has it enrolled, so a half-authenticated (password-only,
    2FA-pending) session does NOT read as signed in."""
    payload = _session_payload(request)
    return payload.get("sub") if payload else None


# Optional dependency routers MAY use to require/read the identity. Enforcement
# is otherwise handled by AuthMiddleware, so no router needs to import this.
def get_current_user(request: Request) -> str | None:
    return current_user(request)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/", samesite=COOKIE_SAMESITE)


# --- CSRF double-submit token ----------------------------------------------
def _issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _set_csrf_cookie(response: Response, token: str) -> None:
    # Deliberately NOT HttpOnly: the SPA must read it to echo it in the header
    # (double-submit). Same Secure/SameSite/path as the session cookie. The token
    # is not a secret on its own — security comes from same-origin-JS being the only
    # party that can both read this cookie AND set the matching request header.
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def _csrf_ok(request: Request) -> bool:
    cookie_tok = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_tok = request.headers.get(CSRF_HEADER_NAME, "")
    return bool(cookie_tok) and bool(header_tok) and secrets.compare_digest(cookie_tok, header_tok)


def _is_header_authed(request: Request) -> bool:
    """A request authenticated by a header (bearer token or shared access code) is
    NOT a browser cookie flow and cannot be CSRF-forged, so it is exempt from the
    double-submit requirement (keeps the access-code / future bearer paths working)."""
    return bool(request.headers.get("authorization") or request.headers.get("x-access-code"))


# --- Login brute-force throttle (per IP) -----------------------------------
_login_lock = threading.Lock()
_login_hits: dict[str, tuple[float, int]] = {}


def _login_throttled(ip: str) -> bool:
    now = time.time()
    with _login_lock:
        start, count = _login_hits.get(ip, (now, 0))
        if now - start >= LOGIN_WINDOW_SECONDS:
            start, count = now, 0
        count += 1
        _login_hits[ip] = (start, count)
        if len(_login_hits) > 4096:
            stale = [k for k, (s, _) in _login_hits.items()
                     if now - s >= LOGIN_WINDOW_SECONDS]
            for k in stale:
                _login_hits.pop(k, None)
        return count > LOGIN_MAX_ATTEMPTS


# --- Per-account lockout (consecutive failures) ----------------------------
# username -> (consecutive_failures, locked_until_ts). Keyed on the SUBMITTED name
# whether or not it exists, so the locked branch is existence-agnostic.
_account_lock = threading.Lock()
_account_fails: dict[str, tuple[int, float]] = {}


def _account_locked(username: str) -> bool:
    if LOGIN_LOCKOUT_THRESHOLD <= 0:
        return False
    now = time.time()
    with _account_lock:
        _fails, locked_until = _account_fails.get(username, (0, 0.0))
        return now < locked_until


def _record_login_failure(username: str) -> None:
    if LOGIN_LOCKOUT_THRESHOLD <= 0:
        return
    now = time.time()
    with _account_lock:
        fails, locked_until = _account_fails.get(username, (0, 0.0))
        if now >= locked_until:  # a previous lock has expired -> the counter is fresh
            if locked_until and fails >= LOGIN_LOCKOUT_THRESHOLD:
                fails = 0
        fails += 1
        locked_until = now + LOGIN_LOCKOUT_SECONDS if fails >= LOGIN_LOCKOUT_THRESHOLD else locked_until
        _account_fails[username] = (fails, locked_until)
        if len(_account_fails) > 4096:
            stale = [k for k, (_, lu) in _account_fails.items() if now - lu > LOGIN_LOCKOUT_SECONDS]
            for k in stale:
                _account_fails.pop(k, None)


def _reset_login_failures(username: str) -> None:
    with _account_lock:
        _account_fails.pop(username, None)


def _client_ip(request: Request) -> str:
    # Single shared derivation so the login throttle and the rate limiter key on
    # the SAME IP and both honor TRUSTED_PROXY_HOPS (reading the Nth-from-right XFF
    # entry), instead of this gate hardcoding parts[-1] and disagreeing at hop!=1.
    from .security import client_ip
    return client_ip(request)


# --- DB-backed session revocation helpers ----------------------------------
# Stateless signed cookies can't be force-revoked; when the DB is enabled we ALSO
# record each session's `sid` server-side so logout / an admin can kill a live one.
# All of this is a NO-OP when the DB is disabled (stateless as today).
def _ip_hash(ip: str) -> "str | None":
    """PHI-safe, non-reversible hash of the client IP, salted with the signing secret
    (never the raw address). Matches the audit trail's ip-hashing intent."""
    if not ip:
        return None
    return hashlib.sha256((_SECRET + "|" + ip).encode("utf-8")).hexdigest()[:32]


def _record_session(request: Request, sid: str, username: str) -> None:
    """Record + activate a server-side session (DB-backed revocation). No-op when the
    DB is disabled, so the demo stays purely stateless."""
    from . import db

    if not db.is_enabled():
        return
    try:
        _ensure_db_ready()
        from .services import store

        ua = (request.headers.get("user-agent") or "").strip()[:256] or None
        store.create_session(sid, username, user_agent=ua,
                             ip_hash=_ip_hash(_client_ip(request)))
    except Exception:
        logger.exception("session record failed")


def _revoke_current_session(request: Request) -> None:
    """Revoke the session named by the current cookie's `sid` (logout). No-op when the
    DB is disabled or the cookie is absent/invalid."""
    from . import db

    if not db.is_enabled():
        return
    payload = verify_token(request.cookies.get(COOKIE_NAME, ""))
    sid = payload.get("sid") if payload else None
    if not sid:
        return
    try:
        from .services import store

        store.revoke_session(sid)
    except Exception:
        logger.exception("session revoke failed")


def _session_revoked(sid: "str | None") -> bool:
    """True when the DB is enabled AND this sid is missing/revoked (=> reject). Always
    False when the DB is disabled (stateless: the cookie signature is the only anchor)."""
    from . import db

    if not db.is_enabled():
        return False
    try:
        _ensure_db_ready()
        from .services import store

        return not store.is_session_active(sid or "")
    except Exception:
        # Fail-OPEN on an infrastructure error here would defeat revocation, but
        # fail-CLOSED would take down the whole protected surface on a transient DB
        # blip. The signed cookie is still validated independently; log and allow.
        logger.exception("session active-check failed; allowing on signed cookie only")
        return False


# --- Middleware: gate protected prefixes when auth is enabled ---------------
class AuthMiddleware(BaseHTTPMiddleware):
    """401 on protected paths without a valid session, when AUTH_ENABLED.

    No-op when AUTH_ENABLED is false (open demo) or the path is not protected.
    Sits alongside AccessCodeMiddleware — they can be layered (a request must
    satisfy both). Returns JSON so the SPA can prompt a login; static assets and
    the SPA shell are never gated, so the login screen itself always loads.
    """

    async def dispatch(self, request: Request, call_next):
        if AUTH_ENABLED and request.url.path.startswith(PROTECTED_PREFIXES):
            payload = verify_token(request.cookies.get(COOKIE_NAME, ""))
            if payload is None:
                return JSONResponse(
                    {"detail": "Sign in to use this feature.", "code": "auth_required"},
                    status_code=401)
            # DB-backed revocation: when the DB is enabled, a signed cookie whose
            # server-side session was revoked (logout / admin kill) or never recorded
            # is rejected even though its signature/expiry still verify. No-op (skipped)
            # when the DB is disabled — sessions stay stateless exactly as today.
            if _session_revoked(payload.get("sid")):
                return JSONResponse(
                    {"detail": "This session has been signed out.", "code": "session_revoked"},
                    status_code=401)
            # 2FA gate: a user with a confirmed enrollment whose token is not yet
            # `mfa` is only half-authenticated — block protected access until verify.
            if not _mfa_satisfied(payload):
                return JSONResponse(
                    {"detail": "Two-factor verification required.", "code": "mfa_required"},
                    status_code=401)
            # CSRF (double-submit) on cookie-authenticated state-changing requests.
            # Header/bearer/access-code auth is exempt (not a browser-cookie flow).
            if (CSRF_ENABLED
                    and request.method.upper() not in _CSRF_SAFE_METHODS
                    and not _is_header_authed(request)
                    and not _csrf_ok(request)):
                return JSONResponse(
                    {"detail": "Missing or invalid CSRF token.", "code": "csrf_failed"},
                    status_code=403)
            response = await call_next(request)
            # Sliding idle window (auto-logoff): refresh the cookie on genuine
            # protected activity, preserving the ABSOLUTE exp cap AND the mfa/sid claims.
            if SESSION_IDLE_TIMEOUT_SECONDS > 0:
                try:
                    _set_session_cookie(response, issue_token(
                        payload["sub"], abs_exp=payload.get("exp"),
                        mfa=payload.get("mfa", False), sid=payload.get("sid")))
                    # Server-side sliding-window bookkeeping (DB-backed sessions only).
                    from . import db as _db
                    if _db.is_enabled():
                        from .services import store as _store
                        _store.touch_session(payload.get("sid") or "")
                except Exception:
                    logger.exception("session refresh failed")
            # Audit trail (§164.312(b)) — PHI-free: user + method + path + ip + status.
            try:
                from .services import audit
                audit.log_event(user=payload.get("sub"), action=request.method,
                                resource=request.url.path, ip=_client_ip(request),
                                status=getattr(response, "status_code", None))
            except Exception:
                logger.exception("audit log failed")
            return response
        return await call_next(request)


# --- Router -----------------------------------------------------------------
router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


# Uniform failure — same body + status for wrong-password AND unknown-user so the
# response never distinguishes the two (anti-enumeration). Timing is kept comparable
# by verify_credentials running a full scrypt compare even for an unknown user.
_INVALID_CREDS = {"detail": "Invalid username or password."}


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    if not AUTH_ENABLED:
        # Nothing to log into; report open state instead of minting a token.
        return {"authenticated": False, "auth_enabled": False,
                "detail": "Authentication is disabled; the demo is open."}

    username = body.username.strip()
    ip = _client_ip(request)
    if _login_throttled(ip):
        return JSONResponse(
            {"detail": "Too many login attempts. Try again in a few minutes."},
            status_code=429, headers={"Retry-After": str(int(LOGIN_WINDOW_SECONDS))})

    # Per-account lockout. Keyed on the submitted name (existing or not) so the 429
    # is existence-agnostic and cannot be used to enumerate accounts.
    if _account_locked(username):
        return JSONResponse(
            {"detail": "This account is temporarily locked after too many failed "
                       "attempts. Try again later."},
            status_code=429, headers={"Retry-After": str(int(LOGIN_LOCKOUT_SECONDS))})

    if not verify_credentials(username, body.password):
        _record_login_failure(username)
        return JSONResponse(_INVALID_CREDS, status_code=401)

    _reset_login_failures(username)

    # Session-fixation defence: a brand-new random sid is minted here (and recorded
    # server-side for DB-backed revocation), so any pre-login cookie value is discarded.
    if _totp_confirmed(username):
        # Password OK but 2FA still owed — issue a HALF session (mfa=False). Protected
        # paths stay 401 (mfa_required) until POST /api/2fa/verify upgrades it.
        sid = secrets.token_hex(8)
        _record_session(request, sid, username)
        _set_session_cookie(response, issue_token(username, mfa=False, sid=sid))
        _set_csrf_cookie(response, _issue_csrf_token())
        return {"authenticated": False, "auth_enabled": True, "user": username,
                "mfa_required": True}

    sid = secrets.token_hex(8)
    _record_session(request, sid, username)
    _set_session_cookie(response, issue_token(username, mfa=True, sid=sid))
    _set_csrf_cookie(response, _issue_csrf_token())
    return {"authenticated": True, "auth_enabled": True, "user": username,
            "mfa_required": False}


@router.post("/logout")
def logout(request: Request, response: Response):
    # DB-backed revocation: mark this session's sid revoked so its still-valid signed
    # cookie can no longer be replayed (a stolen cookie is now dead server-side). No-op
    # when the DB is disabled — logout then only clears the cookie, as today.
    _revoke_current_session(request)
    _clear_session_cookie(response)
    # Invalidate the paired CSRF cookie too, so no stale double-submit token lingers.
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/", samesite=COOKIE_SAMESITE)
    return {"authenticated": False, "auth_enabled": AUTH_ENABLED}


@router.get("/me")
def me(request: Request):
    """Session probe the SPA calls on load: is auth on, am I signed in, and is 2FA
    owed (password accepted, verification pending) or enrolled?"""
    raw = verify_token(request.cookies.get(COOKIE_NAME, ""))
    user = raw.get("sub") if raw else None
    mfa_pending = bool(raw and _totp_confirmed(user) and not raw.get("mfa"))
    authed = bool(raw and _mfa_satisfied(raw))
    resp = {
        "auth_enabled": AUTH_ENABLED,
        "authenticated": authed,
        "user": user if authed else None,
        "mfa_enrolled": bool(user and _totp_confirmed(user)),
        "mfa_pending": mfa_pending,
        "demo_mode": AUTH_DEMO_MODE,
    }
    # Reveal the demo credentials ONLY in demo mode, when no real users are
    # configured, and to an as-yet-unauthenticated caller — so a real deployment can
    # never leak a password through this probe.
    if AUTH_DEMO_MODE and not _REAL_USERS_CONFIGURED and not authed:
        resp["demo_credentials"] = {"username": DEMO_USERNAME, "password": DEMO_PASSWORD}
    return resp


# --- CSRF token ------------------------------------------------------------
@router.get("/csrf")
def csrf(request: Request, response: Response):
    """Issue a CSRF token: sets the readable double-submit cookie AND returns the
    token in the body. The SPA echoes it in the `X-CSRF-Token` header on every
    state-changing (POST/PUT/PATCH/DELETE) request under cookie auth."""
    token = _issue_csrf_token()
    _set_csrf_cookie(response, token)
    return {"csrf_token": token, "header": CSRF_HEADER_NAME, "enabled": CSRF_ENABLED}


# --- Optional TOTP 2FA -----------------------------------------------------
class TotpVerifyRequest(BaseModel):
    code: str


@router.post("/2fa/enroll")
def totp_enroll(request: Request, response: Response):
    """Begin (or restart) TOTP enrollment for the CURRENT session's user. Returns a
    fresh base32 secret + otpauth:// URI to load into an authenticator app. The
    enrollment is PENDING until /api/2fa/verify confirms a code; a pending enrollment
    does NOT yet force 2FA at login (so a bad enroll can't lock the user out)."""
    if not AUTH_ENABLED:
        return JSONResponse({"detail": "Authentication is disabled.", "code": "auth_disabled"},
                            status_code=400)
    # Identify the user from the (possibly half-authenticated) session cookie.
    raw = verify_token(request.cookies.get(COOKIE_NAME, ""))
    user = raw.get("sub") if raw else None
    if not user:
        return JSONResponse({"detail": "Sign in first.", "code": "auth_required"}, status_code=401)

    # SECURITY (2FA-bypass defence): re-enrolling OVERWRITES the stored secret with a
    # fresh confirmed=False record. If a password-only (MFA-pending) session were
    # allowed to do that on an account that ALREADY has confirmed 2FA, it would clear
    # the confirmed flag -> _mfa_satisfied() would then return True -> the half session
    # would become fully authenticated WITHOUT ever proving the second factor. So a
    # user who already has CONFIRMED 2FA may only (re-)enroll from a session that has
    # itself satisfied 2FA. INITIAL enrollment (no confirmed record yet) is unaffected:
    # such a session is already fully authenticated because the user has no 2FA to owe.
    if _totp_confirmed(user) and not _mfa_satisfied(raw):
        return JSONResponse(
            {"detail": "Two-factor verification required.", "code": "mfa_required"},
            status_code=401)

    secret = _new_totp_secret()
    _set_totp_enrollment(user, secret, confirmed=False)
    return {
        "secret": secret,
        "otpauth_uri": _otpauth_uri(user, secret),
        "issuer": TOTP_ISSUER,
        "digits": TOTP_DIGITS,
        "period": TOTP_STEP_SECONDS,
        "algorithm": "SHA1",
        "confirmed": False,
    }


@router.post("/2fa/verify")
def totp_verify(body: TotpVerifyRequest, request: Request, response: Response):
    """Verify a TOTP code for the current session's user. Two roles:
      * CONFIRM a pending enrollment (first successful code marks 2FA active); and
      * COMPLETE login for an already-enrolled user (upgrades the half session).
    On success the session token is ROTATED with mfa=True (fixation defence) and a
    fresh CSRF token is issued."""
    if not AUTH_ENABLED:
        return JSONResponse({"detail": "Authentication is disabled.", "code": "auth_disabled"},
                            status_code=400)
    raw = verify_token(request.cookies.get(COOKIE_NAME, ""))
    user = raw.get("sub") if raw else None
    if not user:
        return JSONResponse({"detail": "Sign in first.", "code": "auth_required"}, status_code=401)

    rec = totp_enrollment(user)
    if not rec:
        return JSONResponse({"detail": "No 2FA enrollment in progress.", "code": "no_enrollment"},
                            status_code=400)
    if not verify_totp(rec["secret"], body.code):
        return JSONResponse({"detail": "Invalid or expired code.", "code": "totp_invalid"},
                            status_code=401)

    _confirm_totp_enrollment(user)

    # Rotate the session (NEW sid, recorded server-side) and mark it 2FA-satisfied.
    # Preserve the absolute exp cap from the current token so verify doesn't extend the
    # session lifetime. Revoke the pre-rotation (half) sid so it can't be replayed.
    _revoke_current_session(request)
    sid = secrets.token_hex(8)
    _record_session(request, sid, user)
    _set_session_cookie(response, issue_token(user, abs_exp=raw.get("exp"), mfa=True, sid=sid))
    _set_csrf_cookie(response, _issue_csrf_token())
    return {"authenticated": True, "auth_enabled": True, "user": user, "mfa": True}


# --- Admin: session management (list + revoke) -----------------------------
# Guarded by AUTH_ENABLED + a fully-authenticated session with role=='admin'. The
# /api/admin prefix is in PROTECTED_PREFIXES, so AuthMiddleware already enforces a
# valid (non-revoked, 2FA-satisfied) session + CSRF before these run; the role check
# below is the authorization layer on top. Server-side sessions require the DB, so
# these return a clear 400 when DATABASE_URL is unset.
class AdminRevokeRequest(BaseModel):
    sid: str | None = None
    username: str | None = None


def _current_user_role(request: Request) -> "tuple[str | None, str | None]":
    """(username, role) for the fully-authenticated caller, else (None, None). Role is
    read from the DB user row when enabled, else derived from AUTH_ADMINS."""
    user = current_user(request)
    if not user:
        return None, None
    from . import db

    if db.is_enabled():
        _ensure_db_ready()
        from .services import store

        row = store.get_user(user)
        return user, (row.get("role") if row else "user")
    return user, ("admin" if user in AUTH_ADMINS else "user")


def _require_admin(request: Request):
    """None when the caller is an authenticated admin; otherwise a JSONResponse to
    return immediately (auth disabled / not signed in / not an admin)."""
    if not AUTH_ENABLED:
        return JSONResponse({"detail": "Authentication is disabled.", "code": "auth_disabled"},
                            status_code=400)
    user, role = _current_user_role(request)
    if not user:
        return JSONResponse({"detail": "Sign in first.", "code": "auth_required"}, status_code=401)
    if role != "admin":
        return JSONResponse({"detail": "Administrator privilege required.", "code": "forbidden"},
                            status_code=403)
    return None


def _db_required_response():
    return JSONResponse(
        {"detail": "Session management requires DATABASE_URL; server-side sessions are "
                   "disabled in the stateless demo.", "code": "db_disabled"},
        status_code=400)


@router.get("/admin/sessions")
def admin_list_sessions(request: Request, username: str | None = None):
    """List server-side sessions (optionally for one user), newest first. Admin only."""
    err = _require_admin(request)
    if err is not None:
        return err
    from . import db

    if not db.is_enabled():
        return _db_required_response()
    from .services import store

    return {"sessions": store.list_sessions(username=username)}


@router.post("/admin/sessions/revoke")
def admin_revoke_sessions(body: AdminRevokeRequest, request: Request):
    """Kill a live session by `sid`, or every live session for a `username`. Admin only.
    The revoked session's next protected request is rejected (session_revoked)."""
    err = _require_admin(request)
    if err is not None:
        return err
    from . import db

    if not db.is_enabled():
        return _db_required_response()
    from .services import store

    if body.sid:
        revoked = store.revoke_session(body.sid.strip())
        return {"revoked": 1 if revoked else 0, "sid": body.sid.strip()}
    if body.username:
        n = store.revoke_all_for_user(body.username.strip())
        return {"revoked": n, "username": body.username.strip()}
    return JSONResponse({"detail": "Provide a sid or username to revoke.", "code": "bad_request"},
                        status_code=400)


# --- Per-user: account/session self-management -----------------------------
# These let an ordinary signed-in user manage THEIR OWN sessions + 2FA (no admin
# role required). /api/sessions and /api/2fa/disable are in PROTECTED_PREFIXES, so
# AuthMiddleware already enforces a valid, non-revoked, 2FA-satisfied session (+ CSRF
# on the POSTs) before any of these run — an unauthenticated caller is rejected with
# 401 auth_required upstream. The endpoints re-identify the caller (and their current
# sid) from the signed cookie and scope EVERY read/write to that caller's own rows, so
# one user can never see or revoke another user's session. Server-side sessions require
# the DB; when DATABASE_URL is unset the app is stateless (no session history to show
# or revoke), which is reported honestly rather than faked.
class SessionRevokeRequest(BaseModel):
    sid: str


class TotpDisableRequest(BaseModel):
    # Optional: a code is only required when the caller currently has CONFIRMED 2FA
    # (proving possession of the second factor before turning it off). A caller with no
    # confirmed enrollment has nothing to prove, so the field may be omitted/empty.
    code: str | None = None


def _caller_and_sid(request: Request) -> "tuple[str | None, str | None]":
    """(username, sid) for the FULLY-authenticated caller (valid signature/expiry AND
    2FA satisfied), else (None, None). The sid is the caller's own current session id,
    used to mark is_current and to exempt the current session from revoke-others."""
    payload = _session_payload(request)
    if not payload:
        return None, None
    return payload.get("sub"), payload.get("sid")


@router.get("/sessions")
def list_my_sessions(request: Request):
    """List the CURRENT user's own LIVE sessions (never another user's), newest first.

    Each item: {id, sid, created_at, last_seen, user_agent, ip_hash, is_current}. `id`
    == `sid` is the handle the client passes to /api/sessions/revoke. No raw IP is ever
    returned (ip_hash only). When the DB is disabled the app is stateless (no session
    history exists), so this returns {"supported": false, "sessions": []} and the UI can
    show an honest 'session history needs the database' note."""
    user, current_sid = _caller_and_sid(request)
    if not user:
        # Defence in depth — the middleware already 401s an unauthenticated caller on
        # this protected prefix, but never trust that alone for a per-user data read.
        return JSONResponse({"detail": "Sign in first.", "code": "auth_required"}, status_code=401)
    from . import db

    if not db.is_enabled():
        return {"supported": False, "sessions": []}
    from .services import store

    rows = store.list_sessions(username=user, include_revoked=False)
    sessions = [
        {
            "id": r["sid"],
            "sid": r["sid"],
            "created_at": r.get("created_at"),
            "last_seen": r.get("last_seen"),
            "user_agent": r.get("user_agent"),
            "ip_hash": r.get("ip_hash"),
            "is_current": r["sid"] == current_sid,
        }
        for r in rows
    ]
    return {"supported": True, "sessions": sessions}


@router.post("/sessions/revoke")
def revoke_my_session(body: SessionRevokeRequest, request: Request):
    """Revoke ONE of the current user's own sessions by `sid`. Ownership is verified
    against the stored session record (username == caller) before revoking: a sid that
    belongs to another user is refused with 403, an unknown sid with 404. Revoking the
    caller's CURRENT sid effectively logs them out (its next protected request is
    rejected server-side as session_revoked)."""
    user, _ = _caller_and_sid(request)
    if not user:
        return JSONResponse({"detail": "Sign in first.", "code": "auth_required"}, status_code=401)
    from . import db

    if not db.is_enabled():
        return _db_required_response()
    from .services import store

    sid = (body.sid or "").strip()
    if not sid:
        return JSONResponse({"detail": "Provide a sid to revoke.", "code": "bad_request"},
                            status_code=400)
    # Locate the record to enforce ownership. list_sessions() is scanned server-side
    # only (the row is never returned to the client), so no cross-user data leaks: an
    # unknown sid -> 404, another user's sid -> 403, so neither existence nor ownership
    # of another user's session is confirmable through the response.
    record = next((s for s in store.list_sessions() if s["sid"] == sid), None)
    if record is None:
        return JSONResponse({"detail": "Session not found.", "code": "not_found"}, status_code=404)
    if record.get("username") != user:
        return JSONResponse({"detail": "That session is not yours.", "code": "forbidden"},
                            status_code=403)
    revoked = store.revoke_session(sid)
    return {"revoked": 1 if revoked else 0, "sid": sid}


@router.post("/sessions/revoke-others")
def revoke_my_other_sessions(request: Request):
    """Sign out of all OTHER devices: revoke every live session for the current user
    EXCEPT the caller's own current sid. Returns the number revoked. The current
    session is preserved so the caller stays signed in on this device."""
    user, current_sid = _caller_and_sid(request)
    if not user:
        return JSONResponse({"detail": "Sign in first.", "code": "auth_required"}, status_code=401)
    from . import db

    if not db.is_enabled():
        return _db_required_response()
    from .services import store

    revoked = 0
    for s in store.list_sessions(username=user, include_revoked=False):
        if s["sid"] != current_sid:
            if store.revoke_session(s["sid"]):
                revoked += 1
    return {"revoked": revoked, "kept": current_sid}


@router.post("/2fa/disable")
def totp_disable(body: TotpDisableRequest, request: Request):
    """Turn OFF TOTP 2FA for the current user. Safety: the caller must be FULLY
    authenticated (2FA already satisfied for this session — enforced by _session_payload
    here and by the middleware upstream) and, if they currently have a CONFIRMED
    enrollment, must pass a valid current TOTP `code` (same check as /api/2fa/verify) to
    prove possession of the second factor before it is removed. On success the
    enrollment is cleared (DB or in-memory), so /api/me then reports
    mfa_enrolled=false."""
    if not AUTH_ENABLED:
        return JSONResponse({"detail": "Authentication is disabled.", "code": "auth_disabled"},
                            status_code=400)
    # Fully-authenticated caller only: a half (MFA-pending) session reads as not
    # signed in here, so it cannot strip 2FA to slip past the second factor.
    user = current_user(request)
    if not user:
        return JSONResponse({"detail": "Sign in first.", "code": "auth_required"}, status_code=401)

    rec = totp_enrollment(user)
    if rec and rec.get("confirmed"):
        # Enrolled: require a valid current code before disabling (possession proof).
        if not verify_totp(rec.get("secret") or "", body.code or ""):
            return JSONResponse({"detail": "Invalid or expired code.", "code": "totp_invalid"},
                                status_code=401)

    _set_totp_enrollment(user, None, False)
    return {"disabled": True, "mfa_enrolled": False, "user": user}
