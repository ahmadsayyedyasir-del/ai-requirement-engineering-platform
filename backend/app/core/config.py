"""
config.py — Central configuration for the entire backend application.

WHY THIS FILE EXISTS:
  Hard-coding values like API keys or database URLs directly in code is dangerous
  (they end up in version control) and inflexible (changing environments means
  changing code). Instead, all configurable values live in a `.env` file that is
  NEVER committed to git, and are read here by Pydantic's BaseSettings.

  Every other file imports the singleton `settings` object from this module:
      from app.core.config import settings
      print(settings.LLM_PROVIDER)  # "groq" or "openai"

HOW PYDANTIC SETTINGS WORKS:
  Pydantic reads each attribute name as an environment variable name (case-insensitive).
  If the variable is present in .env or the shell environment, its value is used.
  If absent, the Field(default=...) value is used.
  If a variable has no default and is missing, Pydantic raises a ValidationError
  at startup — much better than a silent failure mid-request.

LLM PROVIDER SWITCHING:
  The system now supports two LLM providers:
    - "groq"   → uses the Groq API (fast inference, Llama/Mixtral models)
    - "openai" → uses the OpenAI API (GPT-4o)
  Set LLM_PROVIDER in .env to choose. llm_client.py reads this setting.
  Embeddings always use OpenAI (Groq does not provide embedding models).
  If OPENAI_API_KEY is empty and provider is "groq", embeddings use a
  lightweight local fallback so ChromaDB RAG still works.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    """
    All application configuration in one place.

    Attributes map 1-to-1 with environment variable names (case-insensitive).
    In production, every setting with a default should still be explicitly set.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ───────────────────────────────────────────────────────────

    APP_NAME: str = "AI Requirement Engineering Platform"

    # "development" enables debug logging; "production" tightens security settings
    ENVIRONMENT: str = Field(default="development")

    # When True, SQLAlchemy prints every SQL query — NEVER enable in production
    DEBUG: bool = Field(default=True)

    # Signs JWT tokens — generate with: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str = Field(default="change-me-in-production-32-chars-minimum")

    # Login session lifetime in minutes (default 24 hours)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # ── Database (PostgreSQL) ─────────────────────────────────────────────────

    # asyncpg is the async PostgreSQL driver — required for FastAPI's async I/O.
    # In Docker, host is "db" (the service name). Locally, use "localhost".
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://reqeng:reqeng_pass@localhost:5432/reqeng_db"
    )

    # ── Redis ─────────────────────────────────────────────────────────────────

    # Used as the Celery broker and optional API cache.
    # In Docker, host is "redis". Locally, use "localhost".
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # ── ChromaDB (Vector Database for RAG) ───────────────────────────────────

    # ChromaDB stores text embeddings for the RAG knowledge base.
    # In Docker, host is "chroma". Locally, use "localhost".
    CHROMA_HOST: str = Field(default="localhost")
    CHROMA_PORT: int = Field(default=8001)
    CHROMA_COLLECTION_KNOWLEDGE: str = "knowledge_base"   # SE best-practice documents
    CHROMA_COLLECTION_PROJECTS: str   = "project_embeddings"  # Per-project requirement vectors

    # ── LLM Provider Selection ────────────────────────────────────────────────

    # Which LLM provider to use for all AI generation tasks.
    # "groq"   → Groq API (fast Llama/Mixtral inference, GROQ_API_KEY required)
    # "openai" → OpenAI API (GPT-4o, OPENAI_API_KEY required)
    # This is read by llm_client.py to decide which LangChain class to instantiate.
    LLM_PROVIDER: str = Field(default="groq")

    # ── Groq Settings ─────────────────────────────────────────────────────────

    # Groq API key — set in .env as GROQ_API_KEY=gsk_...
    # Never hard-code this value. The .env file is excluded from git via .gitignore.
    GROQ_API_KEY: str = Field(default="")

    # Groq model to use.
    # "llama-3.3-70b-versatile" gives the best structured JSON output quality on Groq.
    # Other options: "llama-3.1-8b-instant" (faster/cheaper), "mixtral-8x7b-32768"
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile")

    # ── OpenAI Settings ───────────────────────────────────────────────────────

    # OpenAI API key — required if LLM_PROVIDER="openai" OR for embeddings.
    # If using Groq for chat and no OPENAI_API_KEY is set, embeddings fall back
    # to a lightweight local model (see llm_client.py).
    OPENAI_API_KEY: str = Field(default="")

    # OpenAI chat model — only used when LLM_PROVIDER="openai"
    OPENAI_MODEL: str = Field(default="gpt-4o")

    # Embedding model — used for ChromaDB RAG regardless of LLM_PROVIDER.
    # Only active when OPENAI_API_KEY is set.
    OPENAI_EMBEDDING_MODEL: str = Field(default="text-embedding-3-small")

    # ── File Uploads ──────────────────────────────────────────────────────────

    # Where uploaded PDF/DOCX files are saved. In Docker this is a named volume.
    # In production, swap with an S3 or Azure Blob Storage path.
    UPLOAD_DIR: str = Field(default="/tmp/req_uploads")

    # Maximum upload size in megabytes — protects against oversized files
    MAX_UPLOAD_SIZE_MB: int = 50

    # ── CORS ──────────────────────────────────────────────────────────────────

    # FRONTEND_URL: the single production origin of your deployed frontend.
    # Example: https://your-app.vercel.app
    # In development this is empty — the defaults below cover localhost.
    # In production set this env var to your Vercel/Render URL so CORS
    # only allows requests from your real frontend domain.
    FRONTEND_URL: str = Field(default="")

    # CORS_ORIGINS is the full list used by the FastAPI middleware.
    # The localhost entries are kept so local Docker development still works
    # without having to set FRONTEND_URL.
    # If FRONTEND_URL is set it is appended dynamically in main.py.
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"]
    )

    # ── Celery ────────────────────────────────────────────────────────────────

    # Redis database 1 = Celery task broker (tasks are sent here)
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")

    # Redis database 2 = Celery result backend (task results stored here)
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")


# Single global instance — imported everywhere as:
#   from app.core.config import settings
settings = Settings()
