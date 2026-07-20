"""Opt-in persistence core (engine + session factory + init).

ZERO-CONFIG CONTRACT
--------------------
The database is OPT-IN via the DATABASE_URL environment variable.

  * DATABASE_URL UNSET  -> is_enabled() is False. This module creates NO engine,
    opens NO connection, touches NO disk. Every caller (via app/services/store.py)
    falls back to today's env/file/in-memory behaviour, so the zero-config demo is
    byte-for-byte unchanged.
  * DATABASE_URL SET    -> is_enabled() is True. On first use we build one shared
    engine + session factory. init_db() creates the tables. The default engine is
    SQLite (a single file, still zero external services), e.g.
        DATABASE_URL=sqlite:///./radassist.db
    Switching to Postgres is ONLY a DATABASE_URL change, e.g.
        DATABASE_URL=postgresql+psycopg://user:pass@host:5432/radassist
    No engine-specific code lives in the callers — that is the point of the seam.

Import-safety: importing this module (or the whole app) with DATABASE_URL unset is
side-effect free. The engine is built lazily on first get_engine()/init_db() call,
and only when enabled.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# One process-wide engine, built lazily under a lock. Never created at import.
_engine = None
_engine_lock = threading.Lock()
_initialized = False


def database_url() -> str:
    """The configured DATABASE_URL (read live from the env each call, so tests and
    startup order don't depend on import timing). Empty string means 'unset'."""
    return os.getenv("DATABASE_URL", "").strip()


def is_enabled() -> bool:
    """True iff a DATABASE_URL is configured. When False the DB layer is fully
    dormant and callers must use their existing (env/file/in-memory) fallback."""
    return bool(database_url())


def _ensure_sqlite_dir(url: str) -> None:
    """For a file-backed SQLite URL, make sure the parent directory exists so the
    engine can create the file. No-op for :memory:, non-sqlite, or bare filenames."""
    try:
        from sqlalchemy.engine import make_url

        u = make_url(url)
        if not u.drivername.startswith("sqlite"):
            return
        db_path = u.database
        if not db_path or db_path == ":memory:":
            return
        parent = Path(db_path).resolve().parent
        parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Directory prep is best-effort; the engine will surface a real error if the
        # path is truly unusable.
        logger.debug("sqlite dir prep skipped for %r", url, exc_info=True)


def _make_engine():
    """Build the shared engine for the configured URL. SQLite gets the FastAPI-safe
    connect args (cross-thread sharing); other backends use their driver defaults."""
    from sqlmodel import create_engine

    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set; DB engine must not be created")

    connect_args: dict = {}
    kwargs: dict = {"echo": False, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        _ensure_sqlite_dir(url)
        # A threaded server (FastAPI/anyio) shares the connection across threads; the
        # session usage is still serialized per-request so this is safe here.
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, **kwargs)


def get_engine():
    """The shared engine, or None when the DB is disabled. Built once, lazily."""
    global _engine
    if not is_enabled():
        return None
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = _make_engine()
    return _engine


def init_db() -> bool:
    """Create all tables. Returns True if the DB is enabled and tables were ensured,
    False (no-op) when disabled. Safe to call repeatedly (create_all is idempotent)."""
    global _initialized
    if not is_enabled():
        return False
    from sqlmodel import SQLModel

    # Import registers the table classes on SQLModel.metadata before create_all.
    from .models import db_models  # noqa: F401

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _initialized = True
    return True


@contextmanager
def get_session() -> Iterator["object"]:
    """Session context manager: `with db.get_session() as s: ...`.

    Also usable as a FastAPI dependency via a thin wrapper, but the context-manager
    form is what the store repositories use. Raises if called while disabled — callers
    must gate on is_enabled() first (the store layer does).
    """
    from sqlmodel import Session

    engine = get_engine()
    if engine is None:
        raise RuntimeError("get_session() called while the DB is disabled (DATABASE_URL unset)")
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def reset_engine_for_tests() -> None:
    """Dispose and forget the cached engine (test helper only). Lets a test flip
    DATABASE_URL and rebuild a fresh engine. Not used in production paths."""
    global _engine, _initialized
    with _engine_lock:
        if _engine is not None:
            try:
                _engine.dispose()
            except Exception:
                pass
        _engine = None
        _initialized = False
