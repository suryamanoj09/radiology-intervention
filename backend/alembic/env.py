"""Alembic environment for RadAssist's opt-in persistence layer.

Wiring notes (kept deliberately small):
  * The database URL is taken from the DATABASE_URL environment variable — the SAME
    variable the app uses (app/db.py). This keeps one source of truth: SQLite for the
    demo (``sqlite:///./radassist.db``) and Postgres for a real deploy by changing only
    that URL. The alembic.ini ``sqlalchemy.url`` is left blank and overridden here.
  * ``target_metadata`` is SQLModel.metadata AFTER importing app.models.db_models, so
    ``alembic revision --autogenerate`` sees the User / FeedbackEvent / AuditLog tables.
  * The demo path still uses ``SQLModel.metadata.create_all`` (app/db.init_db); Alembic
    is the versioned path for Postgres. The initial migration mirrors create_all exactly.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the `app` package importable when alembic is run from the backend/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import SQLModel  # noqa: E402
from app.models import db_models  # noqa: E402,F401  (registers tables on the metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The URL comes from the environment (never hard-coded), so migrations target the same
# database the app does. Fall back to the file-based demo SQLite when unset.
_DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or "sqlite:///./radassist.db"
config.set_main_option("sqlalchemy.url", _DATABASE_URL)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Emit SQL for the configured URL without a live DBAPI connection."""
    context.configure(
        url=_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # batch mode makes ALTERs work on SQLite too (Postgres ignores it).
        render_as_batch=_DATABASE_URL.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection built from the env URL."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_DATABASE_URL.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
