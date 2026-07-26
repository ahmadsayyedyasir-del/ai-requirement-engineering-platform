"""
database.py — Database connection setup and session management.

WHY THIS FILE EXISTS:
  Every request that needs to read or write data needs a "database session" —
  think of it like opening a conversation with the database. This file:
    1. Creates the async database engine (the underlying connection pool)
    2. Creates a session factory (a blueprint for making sessions)
    3. Defines the Base class that all our ORM models inherit from
    4. Provides a FastAPI "dependency" function that hands a session to each
       request and ensures it's properly committed or rolled back.

ASYNC vs SYNC:
  Traditional Python database code is synchronous — it blocks the program
  while waiting for the database to respond. Since our AI pipeline can take
  30-60 seconds, we use async database access so other requests can be
  handled while one is waiting. `asyncpg` is the async PostgreSQL driver.

SQLAlchemy ORM:
  Instead of writing raw SQL, we define Python classes (models) that map to
  database tables. SQLAlchemy translates operations on those classes into SQL.
"""

# AsyncSession is the async version of SQLAlchemy's session.
# create_async_engine creates a pool of database connections.
# async_sessionmaker creates a factory for making AsyncSession objects.
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# DeclarativeBase is the base class for all our ORM models.
# Any class that inherits from Base gets tracked by SQLAlchemy
# and maps to a database table.
from sqlalchemy.orm import DeclarativeBase

# Import settings to get the DATABASE_URL
from app.core.config import settings


# --- Database Engine ---
# The engine manages the connection pool — a set of reusable database connections.
# Instead of opening/closing a connection for every query, we keep a pool open.
#
# pool_size=10: Keep 10 connections open at all times (ready to use).
# max_overflow=20: Allow up to 20 EXTRA connections when the pool is full.
# pool_pre_ping=True: Before using a connection from the pool, send a quick
#   "are you alive?" ping. This prevents errors when the DB server restarted.
# echo=settings.DEBUG: In development, print every SQL query to the console.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# --- Session Factory ---
# AsyncSessionLocal is a "session factory" — a blueprint for creating sessions.
# Calling AsyncSessionLocal() creates a new session object.
#
# expire_on_commit=False: Normally SQLAlchemy "expires" all objects after a commit,
#   meaning you'd have to re-query the DB to read their attributes. Setting False
#   lets us read object attributes after committing — useful in async code.
# autoflush=False: Don't automatically flush (write) pending changes to the DB
#   before every query. We control flushes manually.
# autocommit=False: We manually call commit(). This gives us explicit transaction control.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# --- ORM Base Class ---
# All database models in the `models/` folder inherit from this class.
# SQLAlchemy uses it to track which classes map to which tables.
# Example: class User(Base) → SQLAlchemy knows "User" maps to a DB table.
class Base(DeclarativeBase):
    pass


# --- FastAPI Dependency: get_db ---
# This is a "dependency" — a function that FastAPI calls automatically before
# each endpoint handler that declares `db: AsyncSession = Depends(get_db)`.
#
# HOW IT WORKS:
#   1. Opens a new session from the pool
#   2. Yields it to the endpoint handler (the handler uses it to query the DB)
#   3. After the handler returns, commits the transaction (saves changes)
#   4. If anything raised an exception, rolls back (undoes all changes)
#   5. Always closes the session (returns the connection to the pool)
#
# WHY `yield` INSTEAD OF `return`:
#   Using `yield` turns this into a "generator function" — code after `yield`
#   runs after the endpoint finishes (like a try/finally block). This is how
#   FastAPI implements cleanup logic in dependencies.
async def get_db() -> AsyncSession:
    """
    FastAPI dependency — yields a database session per request.

    Usage in an endpoint:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session            # Hand the session to the endpoint
            await session.commit()   # Save all changes if no error occurred
        except Exception:
            await session.rollback() # Undo all changes if something went wrong
            raise                    # Re-raise the exception so FastAPI can handle it
        finally:
            await session.close()    # Always return the connection to the pool
