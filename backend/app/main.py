"""
main.py — The entry point for the entire FastAPI backend application.

Think of this file as the "front door" of our server. Every HTTP request
from the browser or any API client comes in here first.

What this file does:
  1. Creates the FastAPI application object
  2. Attaches middleware (like CORS, which lets the browser talk to our API)
  3. Registers all the URL routes (e.g., /api/v1/projects, /api/v1/auth)
  4. Handles application startup (creating DB tables) and shutdown (cleanup)

Author: Ezitech | AI-017
"""

# FastAPI is the web framework we use to build the REST API.
# It automatically generates interactive documentation at /api/docs.
from fastapi import FastAPI

# CORSMiddleware solves a browser security rule called "same-origin policy".
# Without this, a webpage on http://localhost:3000 cannot call an API
# on http://localhost:8000 — the browser blocks it. CORS middleware
# tells the browser "yes, this frontend is allowed to talk to this API."
from fastapi.middleware.cors import CORSMiddleware

# asynccontextmanager lets us write startup/shutdown logic in a single function
# using Python's async "with" statement pattern.
from contextlib import asynccontextmanager

# Import our app's settings (reads from the .env file)
from app.core.config import settings

# Import the database engine and the Base class that all models inherit from.
# We need Base.metadata to create database tables on startup.
from app.core.database import engine, Base

# Import the master router that connects all sub-routers (auth, projects, etc.)
from app.api.v1.router import api_router

# Import our logging setup function
from app.core.logging import setup_logging

# Seed function — populates ChromaDB with SE knowledge base documents on startup.
# Imported here so it runs during the lifespan startup sequence below.
from app.services.rag_service import seed_knowledge_base

# Set up logging immediately so all log messages are formatted consistently
# from the moment the application starts.
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan manager — runs code BEFORE the server starts accepting requests
    and AFTER it stops.

    The code before `yield` runs on startup.
    The code after `yield` runs on shutdown.

    WHY: We need to create database tables before any request arrives.
    In production you'd use Alembic migrations instead of create_all,
    but create_all is safe for development because it only creates tables
    that don't already exist — it never drops data.
    """
    # --- STARTUP ---
    # 1. Create all database tables defined in our ORM models.
    #    `run_sync` is needed because SQLAlchemy's create_all is synchronous
    #    but we're running in an async context here.
    #    create_all is safe to call repeatedly — it only creates tables that
    #    don't already exist and never drops or modifies existing data.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Seed the ChromaDB knowledge base with software engineering best practices.
    #    This must run before the first AI analysis request arrives, otherwise
    #    the RAG pipeline returns empty context and GPT-4o gets no guidance.
    #    seed_knowledge_base() is idempotent — it checks whether content already
    #    exists before inserting, so calling it on every startup is safe.
    #    We wrap in try/except so a ChromaDB connection issue on startup does not
    #    prevent the API from starting (the API still works without RAG context,
    #    just with lower-quality AI output until ChromaDB is available).
    try:
        await seed_knowledge_base()
    except Exception as e:
        # Log but don't crash — the API can still operate without RAG seeding.
        # ChromaDB may be starting up and become available shortly after.
        import logging
        logging.getLogger("reqeng").warning(
            f"ChromaDB knowledge base seeding skipped on startup: {e}. "
            "RAG context will be empty until ChromaDB is reachable."
        )

    # `yield` hands control back to FastAPI — the server is now live and
    # accepting requests.
    yield

    # --- SHUTDOWN ---
    # Close all open database connections cleanly.
    # This prevents connection leaks when the server restarts.
    await engine.dispose()


# Create the main FastAPI application object.
# All the metadata here (title, description, version) shows up in the
# auto-generated Swagger documentation at /api/docs.
app = FastAPI(
    title="AI Requirement Engineering Platform",
    description=(
        "Automates the entire requirement engineering lifecycle — from raw business idea "
        "to structured SRS documents, UML diagrams, and software planning artifacts. "
        "Built by Ezitech (AI-017)."
    ),
    version="1.0.0",
    contact={
        "name": "Ezitech",
        "url": "https://ezitech.io",
    },
    license_info={"name": "Proprietary"},
    # Pass the lifespan function so FastAPI knows to run startup/shutdown logic
    lifespan=lifespan,
    # These are the URLs where the auto-generated docs live
    docs_url="/api/docs",       # Swagger UI (interactive)
    redoc_url="/api/redoc",     # ReDoc (read-only, cleaner layout)
    openapi_url="/api/openapi.json",  # Raw OpenAPI schema (JSON)
)

# --- CORS Middleware ---
# CORS = Cross-Origin Resource Sharing.
# We build the allowed-origins list at startup so it includes:
#   - the hardcoded localhost origins (for local Docker development)
#   - FRONTEND_URL from .env (the real production Vercel/Render domain)
# This way you never need to rebuild the container just to change the
# allowed frontend URL — just update the env var and restart.
_cors_origins = list(settings.CORS_ORIGINS)
if settings.FRONTEND_URL and settings.FRONTEND_URL not in _cors_origins:
    # Strip trailing slash so "https://app.vercel.app/" and
    # "https://app.vercel.app" are treated as the same origin.
    _cors_origins.append(settings.FRONTEND_URL.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Router ---
# Instead of defining every endpoint in this file (which would make it huge),
# we import a single "master router" that contains references to all sub-routers.
# prefix="/api/v1" means every URL in the system starts with /api/v1/...
# This is good practice — if we ever build v2, we just add another prefix.
app.include_router(api_router, prefix="/api/v1")


# --- Health Check Endpoint ---
# A health check is a simple URL that returns "I'm alive" — used by Docker,
# Kubernetes, load balancers, and monitoring tools to know the server is running.
# It should be fast (no DB queries) and always return 200 if the process is up.
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Liveness probe — confirms the API process is running.
    Called by Docker healthcheck every 15 seconds.
    Returns 200 OK if the server is alive.
    """
    return {
        "status": "healthy",
        "service": "AI Requirement Engineering Platform",
        "version": "1.0.0",
    }


# --- Root Endpoint ---
# A friendly landing page when someone visits the API URL directly.
# Tells them where the documentation is.
@app.get("/", tags=["Root"])
async def root():
    """Welcome message for anyone who hits the API root URL."""
    return {
        "message": "AI Requirement Engineering Platform API",
        "docs": "/api/docs",   # Point developers to the interactive docs
    }
