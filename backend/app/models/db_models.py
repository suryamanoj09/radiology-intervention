"""SQLModel table definitions for the OPT-IN persistence layer.

These tables are only ever created/used when DATABASE_URL is set (see app/db.py).
When it is unset the whole DB layer is dormant and the app keeps its zero-config
env/file/in-memory behaviour, so importing this module is always side-effect free
(it only registers table metadata; it never opens a connection).

PHI SAFETY (hard rule): NONE of these tables may hold raw pixels or patient
identifiers. Feedback is keyed by a de-identified image hash; audit rows carry a
hashed IP and a de-identified server path only. Patient identifiers stay
client-side, exactly as today.

Tables in this phase — User, AuthSession, FeedbackEvent, AuditLog. Adding a
column later is a schema migration; keep this minimal and PHI-free by construction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive local timestamp)."""
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    """An authenticated account. Mirrors what auth.py derives from ENV today, so a
    migration can move AUTH_USERS/AUTH_2FA_SECRETS into rows without changing the
    auth semantics. `password_hash` is the SAME scrypt string format auth.py emits
    (`scrypt$<salt_hex>$<dk_hex>`); no plaintext is ever stored."""

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=128)
    password_hash: str = Field(max_length=256)
    role: str = Field(default="user", max_length=32)
    twofa_secret: Optional[str] = Field(default=None, max_length=128)
    twofa_confirmed: bool = Field(default=False)
    disabled: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class AuthSession(SQLModel, table=True):
    """Server-side session record for DB-backed revocation. Stateless signed cookies
    alone cannot be force-revoked (a stolen cookie stays valid until idle/absolute
    expiry); this table lets logout AND an admin kill a live session by its `sid`.

    Only ever consulted when DATABASE_URL is set — when the DB is disabled sessions
    stay purely stateless (byte-for-byte the legacy demo), so this table is dormant.

    PHI-free: `sid` is the random per-session id already carried in the signed cookie
    (never a secret on its own — the cookie's HMAC is still the trust anchor). No
    password, no token, no cookie value is stored. `ip_hash` is a hash of the client
    IP (never the raw address); `user_agent` is a coarse client string, not an
    identifier. `revoked` flips the session dead without deleting the audit trail."""

    __tablename__ = "sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    sid: str = Field(index=True, unique=True, max_length=64)
    username: str = Field(index=True, max_length=128)
    revoked: bool = Field(default=False)
    user_agent: Optional[str] = Field(default=None, max_length=256)
    ip_hash: Optional[str] = Field(default=None, max_length=128)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    last_seen: datetime = Field(default_factory=_utcnow, nullable=False)


class FeedbackEvent(SQLModel, table=True):
    """A single reviewer confirm/dismiss (or thumbs) signal, keyed by a de-identified
    image hash so it survives artifact TTL and carries NO PHI. `raw_score` is the
    model's banded score (uncalibrated) at the time of review. Distinct from the
    Pydantic request model models.schemas.FeedbackEvent (that is the wire schema; this
    is the normalized storage row)."""

    __tablename__ = "feedback_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    image_hash: str = Field(index=True, max_length=128)
    label: str = Field(max_length=128)
    action: str = Field(max_length=32)
    reviewer: Optional[str] = Field(default=None, max_length=128)
    raw_score: Optional[float] = Field(default=None)
    # De-identified provenance enum (nih|openi|user_upload|ct-detect|mr-detect). NOT PHI.
    # Carried so the DB-computed feedback summary can reproduce the CXR/research-CADe
    # split exactly (research-CADe feedback must never refit the CXR operating point).
    image_source: Optional[str] = Field(default=None, max_length=32)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class AuditLog(SQLModel, table=True):
    """PHI-free access record (HIPAA §164.312(b)): who did what, where, when. `path`
    holds a de-identified server path only (ids in it are opaque); `ip_hash` is a
    hash of the client IP, never the raw address."""

    __tablename__ = "audit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    actor: Optional[str] = Field(default=None, max_length=128)
    action: str = Field(max_length=32)
    path: Optional[str] = Field(default=None, max_length=256)
    method: Optional[str] = Field(default=None, max_length=16)
    ip_hash: Optional[str] = Field(default=None, max_length=128)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
