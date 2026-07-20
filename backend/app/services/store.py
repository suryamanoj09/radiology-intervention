"""Storage-adapter seam — the ONE place callers go for durable user/feedback/audit
state, so no caller cares whether the backend is Postgres/SQLite (DB enabled) or the
legacy env/file/in-memory mechanisms (DB disabled).

DISPATCH RULE
-------------
Every public function is::

    def op(...):
        if db.is_enabled():
            <DB branch — implemented in THIS phase>
        return <fallback — the existing env/file/in-memory behaviour>

This phase implements the DB branch for all functions and PROVES it (see the smoke
test). The fallback branch is intentionally a documented delegation point: nothing
routes through this module yet, so the fallbacks raise NotImplementedError naming the
exact existing function the migration agents must call. Wiring the fallbacks + moving
callers onto these functions is the NEXT phase — doing it now would risk regressing the
244 green tests, which this phase must not touch.

RETURN CONTRACT (backend-agnostic)
----------------------------------
The DB branch returns PLAIN dicts / lists of dicts (never SQLModel objects) and ISO-8601
strings for timestamps, so the DB and fallback branches are drop-in interchangeable and
no caller ever imports a DB type. `created_at` is an ISO-8601 UTC string.

    User dict:     {id, username, password_hash, role, twofa_secret,
                    twofa_confirmed, disabled, created_at}
    Feedback dict: {id, image_hash, label, action, reviewer, raw_score,
                    image_source, created_at}
    Audit dict:    {id, actor, action, path, method, ip_hash, created_at}

PHI SAFETY: only usernames, scrypt password hashes, a de-identified image hash, and a
hashed IP + de-identified path ever reach here. No pixels, no patient identifiers.

--------------------------------------------------------------------------------------
PUBLIC API (exact signatures the migration agents MUST route through)
--------------------------------------------------------------------------------------
  Users
    get_user(username: str) -> dict | None
    list_users() -> list[dict]
    create_user(username: str, password_hash: str, role: str = "user",
                twofa_secret: str | None = None, twofa_confirmed: bool = False,
                disabled: bool = False) -> dict
    upsert_user(username: str, password_hash: str, role: str = "user",
                twofa_secret: str | None = None, twofa_confirmed: bool = False,
                disabled: bool = False) -> dict
    set_password(username: str, password_hash: str) -> dict | None
    set_twofa(username: str, secret: str | None, confirmed: bool) -> dict | None
    set_disabled(username: str, disabled: bool) -> dict | None

  Feedback
    add_feedback(image_hash: str, label: str, action: str,
                 reviewer: str | None = None, raw_score: float | None = None,
                 image_source: str | None = None) -> dict
    list_feedback(limit: int | None = None) -> list[dict]

  Audit
    add_audit(actor: str | None, action: str, path: str | None = None,
              method: str | None = None, ip_hash: str | None = None) -> dict
    list_audit(limit: int | None = None) -> list[dict]

  Sessions (DB-backed revocation; DB-only, benign stateless fallback)
    create_session(sid, username, user_agent=None, ip_hash=None) -> dict | None
    touch_session(sid) -> dict | None
    revoke_session(sid) -> bool
    is_session_active(sid) -> bool
    list_sessions(username=None, include_revoked=True) -> list[dict]
    revoke_all_for_user(username) -> int

NOTE on twofa_secret: it is encrypted at rest at this boundary (Fernet; see
_encrypt_secret/_decrypt_secret). Writers pass plaintext base32; the stored column is
ciphertext ("enc:"-marked); readers get plaintext back — so auth.py is unchanged.
--------------------------------------------------------------------------------------
"""

from __future__ import annotations

import base64
import logging
import os
import threading
from typing import Optional

from .. import db

logger = logging.getLogger(__name__)


# ============================================================================
# Encryption at rest for the 2FA secret (Fernet, encrypt-on-write/decrypt-on-read)
# ============================================================================
# users.twofa_secret is a TOTP shared secret (base32) — a bearer credential that,
# if the DB is exfiltrated, lets an attacker mint valid codes and defeat 2FA. So it
# is NEVER stored in the clear: create_user / upsert_user / set_twofa encrypt it at
# THIS boundary and get_user / list_users decrypt it, so the rest of auth.py keeps
# handling a plain base32 string and is unchanged.
#
# Key: Fernet key derived (HKDF-SHA256) from a dedicated ENCRYPTION_KEY env var, or
# from SESSION_SECRET when ENCRYPTION_KEY is unset (so a single strong secret can key
# both signing and encryption). Stored values carry an "enc:" marker so a legacy /
# ENV-seeded plaintext secret is still read back verbatim (graceful, no data loss).
#
# If the `cryptography` library is unavailable, we DO NOT silently pretend to encrypt:
# storage falls back to plaintext with a one-time WARNING and the marker is absent, so
# the honesty posture holds (no fabricated encryption claim). It is a hard dependency
# in requirements.txt, so this fallback only fires on a broken/partial install.
_ENC_PREFIX = "enc:"
_ENC_SALT = b"radassist-twofa-enc-v1"
_ENC_INFO = b"users.twofa_secret"

try:
    from cryptography.fernet import Fernet, InvalidToken  # noqa: F401
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    _CRYPTO_AVAILABLE = True
except Exception:  # pragma: no cover - only on a broken install
    _CRYPTO_AVAILABLE = False

_fernet_lock = threading.Lock()
_fernet_cache: dict[str, "Fernet"] = {}
_warned_no_crypto = False


def _encryption_source() -> str:
    """The secret the Fernet key is derived from: ENCRYPTION_KEY if set, else the
    resolved SESSION_SECRET (imported lazily from auth so there is no import cycle and
    the demo's per-process ephemeral secret is reused when nothing is configured)."""
    key = os.getenv("ENCRYPTION_KEY", "").strip()
    if key:
        return key
    try:
        from .. import auth

        return auth._SECRET
    except Exception:
        return os.getenv("SESSION_SECRET", "").strip()


def _fernet() -> "Optional[Fernet]":
    if not _CRYPTO_AVAILABLE:
        return None
    src = _encryption_source()
    with _fernet_lock:
        f = _fernet_cache.get(src)
        if f is None:
            hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=_ENC_SALT, info=_ENC_INFO)
            key = base64.urlsafe_b64encode(hkdf.derive(src.encode("utf-8")))
            f = Fernet(key)
            _fernet_cache[src] = f
        return f


def _encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a 2FA secret for storage. None -> None (no enrollment). On a broken
    crypto install, store plaintext with a one-time warning (documented gap, no
    fabricated claim)."""
    global _warned_no_crypto
    if plaintext is None:
        return None
    f = _fernet()
    if f is None:
        if not _warned_no_crypto:
            logger.warning("cryptography unavailable — storing twofa_secret WITHOUT "
                           "encryption at rest (install `cryptography` to enable).")
            _warned_no_crypto = True
        return plaintext
    token = f.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return _ENC_PREFIX + token


def _decrypt_secret(stored: Optional[str]) -> Optional[str]:
    """Decrypt a stored 2FA secret back to plaintext base32. A value without the
    `enc:` marker is legacy/ENV-seeded plaintext and returned verbatim. A marked value
    that fails to decrypt (wrong key / tampered) returns None — fail-closed: 2FA cannot
    be completed, which blocks access rather than granting a bypass."""
    if stored is None:
        return None
    if not stored.startswith(_ENC_PREFIX):
        return stored  # legacy plaintext (pre-encryption or ENV-seeded)
    f = _fernet()
    if f is None:
        return None
    try:
        return f.decrypt(stored[len(_ENC_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception:
        logger.warning("twofa_secret failed to decrypt (wrong ENCRYPTION_KEY/"
                       "SESSION_SECRET or tampered ciphertext) — treating as absent.")
        return None


# --- serialization helpers --------------------------------------------------
def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def _user_dict(u) -> dict:
    # twofa_secret is stored encrypted at rest; hand callers back the plaintext base32
    # so auth.py is unchanged (it never sees ciphertext).
    return {
        "id": u.id,
        "username": u.username,
        "password_hash": u.password_hash,
        "role": u.role,
        "twofa_secret": _decrypt_secret(u.twofa_secret),
        "twofa_confirmed": u.twofa_confirmed,
        "disabled": u.disabled,
        "created_at": _iso(u.created_at),
    }


def _session_dict(x) -> dict:
    return {
        "id": x.id,
        "sid": x.sid,
        "username": x.username,
        "revoked": x.revoked,
        "user_agent": x.user_agent,
        "ip_hash": x.ip_hash,
        "created_at": _iso(x.created_at),
        "last_seen": _iso(x.last_seen),
    }


def _feedback_dict(f) -> dict:
    return {
        "id": f.id,
        "image_hash": f.image_hash,
        "label": f.label,
        "action": f.action,
        "reviewer": f.reviewer,
        "raw_score": f.raw_score,
        "image_source": f.image_source,
        "created_at": _iso(f.created_at),
    }


def _audit_dict(a) -> dict:
    return {
        "id": a.id,
        "actor": a.actor,
        "action": a.action,
        "path": a.path,
        "method": a.method,
        "ip_hash": a.ip_hash,
        "created_at": _iso(a.created_at),
    }


# A single, obvious marker for every not-yet-wired fallback so the migration phase
# can grep for it and knows exactly which existing mechanism to delegate to.
def _fallback(what: str, existing: str):
    raise NotImplementedError(
        f"store.{what}: DB-disabled fallback is wired in the migration phase; "
        f"route to the existing mechanism: {existing}"
    )


# ============================================================================
# Users
# ============================================================================
def get_user(username: str) -> Optional[dict]:
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import User

        with db.get_session() as s:
            row = s.exec(select(User).where(User.username == username)).first()
            return _user_dict(row) if row else None
    _fallback("get_user", "auth._USERS / auth._load_users() + auth._TOTP_SECRETS")


def list_users() -> list[dict]:
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import User

        with db.get_session() as s:
            return [_user_dict(u) for u in s.exec(select(User).order_by(User.id)).all()]
    _fallback("list_users", "auth._USERS.keys()")


def create_user(username: str, password_hash: str, role: str = "user",
                twofa_secret: Optional[str] = None, twofa_confirmed: bool = False,
                disabled: bool = False) -> dict:
    if db.is_enabled():
        from ..models.db_models import User

        with db.get_session() as s:
            u = User(username=username, password_hash=password_hash, role=role,
                     twofa_secret=_encrypt_secret(twofa_secret),
                     twofa_confirmed=twofa_confirmed, disabled=disabled)
            s.add(u)
            s.commit()
            s.refresh(u)
            return _user_dict(u)
    _fallback("create_user", "ENV-provisioned AUTH_USERS (no runtime creation today)")


def upsert_user(username: str, password_hash: str, role: str = "user",
                twofa_secret: Optional[str] = None, twofa_confirmed: bool = False,
                disabled: bool = False) -> dict:
    """Create the user, or update the existing row's fields. Handy for migrating the
    ENV-defined users into rows idempotently."""
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import User

        with db.get_session() as s:
            u = s.exec(select(User).where(User.username == username)).first()
            if u is None:
                u = User(username=username)
            u.password_hash = password_hash
            u.role = role
            u.twofa_secret = _encrypt_secret(twofa_secret)
            u.twofa_confirmed = twofa_confirmed
            u.disabled = disabled
            s.add(u)
            s.commit()
            s.refresh(u)
            return _user_dict(u)
    _fallback("upsert_user", "ENV-provisioned AUTH_USERS (no runtime upsert today)")


def set_password(username: str, password_hash: str) -> Optional[dict]:
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import User

        with db.get_session() as s:
            u = s.exec(select(User).where(User.username == username)).first()
            if u is None:
                return None
            u.password_hash = password_hash
            s.add(u)
            s.commit()
            s.refresh(u)
            return _user_dict(u)
    _fallback("set_password", "auth._USERS (ENV; no runtime password change today)")


def set_twofa(username: str, secret: Optional[str], confirmed: bool) -> Optional[dict]:
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import User

        with db.get_session() as s:
            u = s.exec(select(User).where(User.username == username)).first()
            if u is None:
                return None
            u.twofa_secret = _encrypt_secret(secret)
            u.twofa_confirmed = confirmed
            s.add(u)
            s.commit()
            s.refresh(u)
            return _user_dict(u)
    _fallback("set_twofa", "auth._TOTP_SECRETS (in-memory enrollment dict)")


def set_disabled(username: str, disabled: bool) -> Optional[dict]:
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import User

        with db.get_session() as s:
            u = s.exec(select(User).where(User.username == username)).first()
            if u is None:
                return None
            u.disabled = disabled
            s.add(u)
            s.commit()
            s.refresh(u)
            return _user_dict(u)
    _fallback("set_disabled", "N/A today (no disable flag in the ENV user model)")


# ============================================================================
# Feedback
# ============================================================================
def add_feedback(image_hash: str, label: str, action: str,
                 reviewer: Optional[str] = None,
                 raw_score: Optional[float] = None,
                 image_source: Optional[str] = None) -> dict:
    if db.is_enabled():
        from ..models.db_models import FeedbackEvent

        with db.get_session() as s:
            f = FeedbackEvent(image_hash=image_hash, label=label, action=action,
                              reviewer=reviewer, raw_score=raw_score,
                              image_source=image_source)
            s.add(f)
            s.commit()
            s.refresh(f)
            return _feedback_dict(f)
    _fallback("add_feedback",
              "routers/feedback.py append to config.FEEDBACK_DIR/feedback.jsonl")


def list_feedback(limit: Optional[int] = None) -> list[dict]:
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import FeedbackEvent

        with db.get_session() as s:
            q = select(FeedbackEvent).order_by(FeedbackEvent.id)
            if limit is not None:
                q = q.limit(limit)
            return [_feedback_dict(f) for f in s.exec(q).all()]
    _fallback("list_feedback",
              "services/feedback_stats.load_events(config.FEEDBACK_DIR/feedback.jsonl)")


# ============================================================================
# Audit
# ============================================================================
def add_audit(actor: Optional[str], action: str, path: Optional[str] = None,
              method: Optional[str] = None, ip_hash: Optional[str] = None) -> dict:
    if db.is_enabled():
        from ..models.db_models import AuditLog

        with db.get_session() as s:
            a = AuditLog(actor=actor, action=action, path=path, method=method,
                         ip_hash=ip_hash)
            s.add(a)
            s.commit()
            s.refresh(a)
            return _audit_dict(a)
    _fallback("add_audit", "services/audit.log_event(...) append to audit.jsonl")


def list_audit(limit: Optional[int] = None) -> list[dict]:
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import AuditLog

        with db.get_session() as s:
            q = select(AuditLog).order_by(AuditLog.id.desc())
            if limit is not None:
                q = q.limit(limit)
            return [_audit_dict(a) for a in s.exec(q).all()]
    _fallback("list_audit", "read config.AUDIT_DIR/audit.jsonl (JSONL)")


# ============================================================================
# Sessions (DB-backed revocation)
# ============================================================================
# These have NO legacy fallback: server-side sessions only exist when the DB is on.
# When the DB is off the app is stateless (signed cookie only), so every caller gates
# on db.is_enabled() first and these DB branches are the only path. The fallback
# branches are deliberately BENIGN (stateless semantics: is_session_active -> True,
# the mutators -> no-op) so a mis-gated call degrades to "stateless as today" and can
# never crash the zero-config demo.
def create_session(sid: str, username: str, user_agent: Optional[str] = None,
                   ip_hash: Optional[str] = None) -> Optional[dict]:
    """Record + activate a session by its signed-cookie `sid`. Idempotent on `sid`:
    re-recording an existing sid re-activates it (revoked -> False) and refreshes its
    metadata, so a rotated login can reuse semantics cleanly."""
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import AuthSession, _utcnow

        with db.get_session() as s:
            row = s.exec(select(AuthSession).where(AuthSession.sid == sid)).first()
            if row is None:
                row = AuthSession(sid=sid, username=username)
            row.username = username
            row.revoked = False
            row.user_agent = user_agent
            row.ip_hash = ip_hash
            row.last_seen = _utcnow()
            s.add(row)
            s.commit()
            s.refresh(row)
            return _session_dict(row)
    return None  # stateless: no server-side session to record


def touch_session(sid: str) -> Optional[dict]:
    """Bump last_seen on genuine activity (sliding-window bookkeeping). No-op if the
    session is missing or revoked (an active check is a separate call)."""
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import AuthSession, _utcnow

        with db.get_session() as s:
            row = s.exec(select(AuthSession).where(AuthSession.sid == sid)).first()
            if row is None or row.revoked:
                return None
            row.last_seen = _utcnow()
            s.add(row)
            s.commit()
            s.refresh(row)
            return _session_dict(row)
    return None


def revoke_session(sid: str) -> bool:
    """Mark a single session revoked (logout / admin kill). Returns True if a matching
    live session was revoked, False if it was missing or already revoked."""
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import AuthSession

        with db.get_session() as s:
            row = s.exec(select(AuthSession).where(AuthSession.sid == sid)).first()
            if row is None or row.revoked:
                return False
            row.revoked = True
            s.add(row)
            s.commit()
            return True
    return False


def is_session_active(sid: str) -> bool:
    """True iff `sid` names a recorded, non-revoked session. A sid the table has never
    seen is INACTIVE (fail-closed) — so a signed cookie whose session was never
    recorded, or was revoked, is rejected."""
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import AuthSession

        with db.get_session() as s:
            row = s.exec(select(AuthSession).where(AuthSession.sid == sid)).first()
            return bool(row) and not row.revoked
    return True  # stateless: no server-side revocation, cookie signature is the anchor


def list_sessions(username: Optional[str] = None,
                  include_revoked: bool = True) -> list[dict]:
    """All sessions (newest first), optionally filtered to one user. Admin view."""
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import AuthSession

        with db.get_session() as s:
            q = select(AuthSession)
            if username is not None:
                q = q.where(AuthSession.username == username)
            if not include_revoked:
                q = q.where(AuthSession.revoked == False)  # noqa: E712
            q = q.order_by(AuthSession.id.desc())
            return [_session_dict(x) for x in s.exec(q).all()]
    return []


def revoke_all_for_user(username: str) -> int:
    """Revoke every live session for a user (admin lockout / credential rotation).
    Returns the number of sessions revoked."""
    if db.is_enabled():
        from sqlmodel import select
        from ..models.db_models import AuthSession

        with db.get_session() as s:
            rows = s.exec(
                select(AuthSession).where(AuthSession.username == username,
                                          AuthSession.revoked == False)  # noqa: E712
            ).all()
            n = 0
            for row in rows:
                row.revoked = True
                s.add(row)
                n += 1
            s.commit()
            return n
    return 0
