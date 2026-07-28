"""
main.py — FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, Base
from app.core.logging import setup_logging
from app.api.v1.router import api_router
from app.services.rag_service import seed_knowledge_base

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all DB tables (idempotent — safe to run every startup)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed ChromaDB knowledge base (no-op if already seeded or no OpenAI key)
    try:
        await seed_knowledge_base()
    except Exception as e:
        import logging
        logging.getLogger("reqeng").warning(f"ChromaDB seeding skipped: {e}")

    yield
    await engine.dispose()


app = FastAPI(
    title="AI Requirement Engineering Platform",
    description="Automates requirement engineering — raw idea → SRS, diagrams, sprint plan.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS: localhost origins always allowed; FRONTEND_URL adds the production Vercel domain
_cors_origins = list(settings.CORS_ORIGINS)
if settings.FRONTEND_URL and settings.FRONTEND_URL not in _cors_origins:
    _cors_origins.append(settings.FRONTEND_URL.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "AI Requirement Engineering Platform", "version": "1.0.0"}


@app.get("/", tags=["Root"])
async def root():
    return {"message": "AI Requirement Engineering Platform API", "docs": "/api/docs"}
