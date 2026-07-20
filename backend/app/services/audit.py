"""Audit trail (HIPAA §164.312(b)) — a PHI-free record of who accessed which
PHI-adjacent action, when, and from where.

Deliberately minimal and PHI-FREE by construction: it logs the authenticated
username, HTTP method, the request PATH (which contains only de-identified server
ids, never patient data), the client IP, and the response status. No request body,
no findings, no patient identifiers. Appended as JSONL to a PRIVATE (non-served)
directory. This is a demo-grade audit stub that closes the loop with the attestation
gate; a real deployment needs tamper-evident, retained, access-controlled logs.

When DATABASE_URL is set (db.is_enabled()), events are instead routed through the
storage adapter into the AuditLog table, and the client IP is HASHED (never stored
raw) before it leaves this module — the DB is PHI-free by construction. When the DB
is disabled the legacy flat-file JSONL behaviour below is byte-for-byte unchanged,
so the zero-config demo is untouched.
"""
import hashlib
import hmac
import json
import logging
import os
import threading
import time

from .. import config, db
from . import store

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_SINK = config.AUDIT_DIR / "audit.jsonl"


def _hash_ip(ip: str | None) -> str | None:
    """One-way HMAC-SHA256 of the client IP so the durable store never holds a raw
    address. Salted with SESSION_SECRET (falls back to a fixed label when unset) so
    the digest is stable across restarts yet not a bare, rainbow-table-able sha256."""
    if not ip:
        return None
    salt = os.getenv("SESSION_SECRET", "").strip().encode("utf-8") or b"radassist-audit"
    return hmac.new(salt, ip.encode("utf-8"), hashlib.sha256).hexdigest()


def log_event(user: str | None, action: str, resource: str, ip: str,
              status: int | None = None) -> None:
    if not config.AUDIT_ENABLED:
        return
    # DB-backed path: route the PHI-free record through the storage adapter with a
    # HASHED IP. A durable-store failure must never break the request being audited.
    if db.is_enabled():
        try:
            store.add_audit(
                actor=(user or None),
                action=(action or "")[:32],
                path=(resource or None),
                method=None,
                ip_hash=_hash_ip(ip),
            )
        except Exception:
            logger.exception("audit DB write failed")
        return
    rec = {
        "ts": int(time.time()),
        "user": (user or "-")[:64],
        "action": (action or "")[:8],
        "resource": (resource or "")[:200],  # path only; ids here are de-identified
        "ip": (ip or "")[:64],
        "status": status,
    }
    try:
        with _lock:
            with open(_SINK, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
    except Exception:
        logger.exception("audit write failed")
