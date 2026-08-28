"""
Alembic migration environment.
Connects to our database and imports all models
so autogenerate can detect schema changes.
"""
import sys
import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Make sure our project root is on the Python path ─────────
# This allows "from backend.xxx import yyy" to work inside migrations
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Import our app config and all models ─────────────────────
from backend.config import settings
from backend.database import Base
# Import all models so Alembic sees them:
import backend.models  # noqa: F401 — side-effect import

# ── Alembic config object ─────────────────────────────────────
config = context.config

# Override the sqlalchemy.url from alembic.ini with our .env value
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up Python logging from the alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata that autogenerate inspects for schema changes
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live DB connection (applies changes)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Render as batch for SQLite ALTER TABLE support
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
