"""
alembic/env.py — Alembic migration environment configuration.

WHY THIS FILE EXISTS:
  Alembic is a database migration tool for SQLAlchemy. It generates and runs
  SQL scripts ("migrations") that evolve the database schema over time.

  Instead of manually writing ALTER TABLE statements when you add a new column,
  you change the SQLAlchemy model (Python class) and run:
      alembic revision --autogenerate -m "add_column_X"
  Alembic compares the current DB schema to the model definitions and generates
  the SQL migration automatically.

  This file tells Alembic:
    1. Where to find the SQLAlchemy metadata (all model classes)
    2. How to connect to the database
    3. Whether to run in "online" mode (connected DB) or "offline" mode (generate SQL files)

WHY ASYNC?
  Our application uses async SQLAlchemy (asyncpg driver). Alembic was originally
  designed for synchronous SQLAlchemy, but supports async via `async_engine_from_config`
  and running migrations inside `asyncio.run()`.

  do_run_migrations() is synchronous and called with connection.run_sync() —
  the actual migration DDL (ALTER TABLE etc.) is still synchronous under the hood.

OFFLINE vs ONLINE MODE:
  Offline: Generates SQL scripts without connecting to the DB.
           Useful for generating scripts to review or run in a CI pipeline.
  Online:  Connects to the DB and runs migrations directly.
           What you use in development: `alembic upgrade head`
"""

import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Add the backend directory to sys.path so imports like `from app.models import ...` work.
# Alembic runs from the project root, not the backend directory.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the declarative Base so Alembic sees all table definitions.
from app.core.database import Base

# Import ALL models — this registers their table metadata with Base.
# Without this, Alembic would see an empty schema and generate DROP TABLE migrations!
# The `*` import also registers the SQLAlchemy relationships between models.
from app.models import *  # noqa: F401,F403 — F401 = imported but unused (they ARE used by Base)

# `context.config` holds the alembic.ini configuration (database URL, etc.)
config = context.config

# Set up Python's logging using the settings in alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `target_metadata` tells Alembic what the schema SHOULD look like.
# Alembic diffs this against the actual DB schema to generate migrations.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in offline mode — generate SQL without connecting to the DB.

    WHEN TO USE:
      When you want to review the SQL before applying it, or when the DB
      isn't accessible from your local machine (e.g., production DB behind a firewall).
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,                        # Inline literal values in SQL
        dialect_opts={"paramstyle": "named"},       # Named parameter style (:param)
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations given an open database connection.

    This is the sync inner function — called inside an async context via run_sync().
    context.configure ties the migration engine to our model metadata.
    context.run_migrations() executes the migration scripts.
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create an async engine and run migrations using async SQLAlchemy.

    async_engine_from_config reads the sqlalchemy.url from alembic.ini.
    NullPool: don't maintain a connection pool — each migration run opens and
    closes one connection cleanly (appropriate for one-time migration runs).
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Single connection, no pool needed for migrations
    )

    async with connectable.connect() as connection:
        # run_sync wraps the sync do_run_migrations inside an async context
        await connection.run_sync(do_run_migrations)

    # Dispose the engine (close the connection) when done
    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Entry point for online mode — runs the async migration pipeline.

    asyncio.run() creates a new event loop, runs the coroutine, and exits.
    This is the right way to run async code from synchronous Alembic entry points.
    """
    asyncio.run(run_async_migrations())


# Choose offline or online based on the context Alembic was invoked in.
# `alembic upgrade head` → online mode (connected DB)
# `alembic upgrade head --sql` → offline mode (generate SQL file)
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
