"""
config.py — Central application configuration via Pydantic BaseSettings.
Values are read from the .env file or environment variables at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "AI Requirement Engineering Platform"
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str = Field(default="change-me-in-production-32-chars-minimum")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Database — asyncpg is required for FastAPI's async I/O
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://reqeng:reqeng_pass@db:5432/reqeng_db"
    )

    # Redis — Celery broker + cache
    REDIS_URL: str = Field(default="redis://redis:6379/0")

    # ChromaDB — vector store for RAG
    CHROMA_HOST: str = Field(default="chroma")
    CHROMA_PORT: int = Field(default=8000)
    CHROMA_COLLECTION_KNOWLEDGE: str = "knowledge_base"
    CHROMA_COLLECTION_PROJECTS: str = "project_embeddings"

    # LLM provider: "groq" (default) or "openai"
    LLM_PROVIDER: str = Field(default="groq")

    # Groq — get a free key at https://console.groq.com
    GROQ_API_KEY: str = Field(default="")
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile")

    # OpenAI — required if LLM_PROVIDER=openai, or for ChromaDB embeddings
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_MODEL: str = Field(default="gpt-4o")
    OPENAI_EMBEDDING_MODEL: str = Field(default="text-embedding-3-small")

    # File uploads — use S3/Blob in production (disk is ephemeral on Railway/Render)
    UPLOAD_DIR: str = Field(default="/tmp/req_uploads")
    MAX_UPLOAD_SIZE_MB: int = 50

    # CORS — FRONTEND_URL is appended to allowed origins at startup (see main.py)
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"]
    )
    FRONTEND_URL: str = Field(default="")

    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://redis:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://redis:6379/2")


settings = Settings()
