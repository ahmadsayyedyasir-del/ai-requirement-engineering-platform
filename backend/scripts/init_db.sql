-- ─────────────────────────────────────────────────────────────────────────────
-- init_db.sql — PostgreSQL initialisation script.
--
-- WHY THIS FILE EXISTS:
--   When a PostgreSQL Docker container starts for the FIRST TIME, it looks for
--   .sql files in /docker-entrypoint-initdb.d/ and runs them in alphabetical order.
--   (See docker-compose.yml: volumes: ./backend/scripts/init_db.sql → /docker-entrypoint-initdb.d/init.sql)
--
--   This script runs ONCE — not on every restart, only when the volume is empty
--   (i.e., the first time you run `docker compose up` on a fresh machine).
--
--   IMPORTANT: The main tables are created by SQLAlchemy's Base.metadata.create_all()
--   in main.py (on startup) and by Alembic migrations in production.
--   This file only handles PostgreSQL-level extensions that must exist before
--   the application starts.
--
-- WHAT THIS FILE DOES:
--   1. Enables the uuid-ossp extension for native UUID generation in PostgreSQL.
--      Our models use uuid4() from Python, but having this extension available
--      allows us to also use gen_random_uuid() in raw SQL if needed.
--
--   2. Prints a confirmation that initialisation ran (visible in Docker logs).
-- ─────────────────────────────────────────────────────────────────────────────

-- Enable UUID generation functions.
-- uuid_generate_v4() → a random UUID (same as Python's uuid.uuid4())
-- IF NOT EXISTS: prevents an error if the extension is already installed
--   (e.g., if this script is run twice or the extension was pre-installed).
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Confirmation message — visible in `docker compose logs db` on first run.
-- This helps confirm the init script ran successfully.
SELECT 'reqeng_db initialised successfully' AS status;
