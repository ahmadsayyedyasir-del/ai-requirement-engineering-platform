"""
services/llm_client.py — Central LLM client factory supporting Groq and OpenAI.

WHY THIS FILE EXISTS:
  Every AI service (requirement_analysis, document_generator, planning_generator,
  diagram_generator, review_engine, moscow_prioritizer) calls get_llm() to get
  a LangChain chat model instance. All provider selection logic lives HERE so:
    - Switching providers means changing ONE setting in .env, not touching service code
    - Every service gets the same model instance configuration automatically
    - Adding a new provider (Anthropic, Azure, etc.) only touches this one file

LLM PROVIDER SELECTION (controlled by LLM_PROVIDER in .env):
  "groq"   → ChatGroq using GROQ_API_KEY and GROQ_MODEL
             Groq provides extremely fast inference via their LPU hardware.
             Recommended model: llama-3.3-70b-versatile (best JSON output quality)
  "openai" → ChatOpenAI using OPENAI_API_KEY and OPENAI_MODEL
             Original provider — GPT-4o gives excellent structured JSON output.

EMBEDDINGS:
  Embeddings are used by the RAG pipeline (rag_service.py) to store and search
  requirements in ChromaDB. Groq does not provide embedding models, so embeddings
  always use OpenAI's text-embedding-3-small when OPENAI_API_KEY is set.
  If OPENAI_API_KEY is empty (Groq-only setup), we use a local sentence-transformers
  model as fallback so RAG still works without an OpenAI key.

TEMPERATURE GUIDE (used across all AI services):
  0.1 → Very deterministic — used for structured JSON extraction and Mermaid diagrams
  0.2 → Default — good balance for document generation
  0.3 → Slightly creative — used for planning artifacts that need judgment
"""

import asyncio
import logging
import random

from app.core.config import settings

logger = logging.getLogger("reqeng.llm")


def _is_rate_limit_error(exc: Exception) -> bool:
    """Best-effort detection of a rate-limit / transient-server error."""
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("rate limit", "429", "too many requests", "503", "timeout", "timed out")
    )


# ── GLOBAL CONCURRENCY CAP ──────────────────────────────────────────────────────
#
# WHY THIS EXISTS:
#   document_generator.py, planning_generator.py, and diagram_generator.py each
#   had their OWN independent semaphore (e.g. 3 concurrent calls each). That
#   looked safe in isolation, but "Generate Everything" starts all three
#   sections at once — so 3 + 3 + 3 = up to 9 simultaneous Groq calls.
#
#   Groq's free tier caps usage at 12,000 tokens/minute (TPM) for this model.
#   Each call here uses roughly 2,000-3,500 tokens. 9 calls at once blows
#   through that budget in a couple of requests, which is exactly what the
#   "Rate limit reached... tokens per minute (TPM): Limit 12000, Used 9132"
#   errors show. Retrying doesn't help much when EVERY concurrent call is
#   also getting rate-limited at the same time.
#
#   This semaphore is defined ONCE here and shared by every caller of
#   ainvoke_with_retry() — no matter which file or which section (documents/
#   planning/diagrams/analysis) is calling it, only 2 Groq requests are ever
#   in flight across the ENTIRE application at once. That keeps total usage
#   safely under the free-tier budget instead of each section pretending it
#   has the whole budget to itself.
_GLOBAL_LLM_SEMAPHORE = asyncio.Semaphore(2)


async def ainvoke_with_retry(chain, inputs: dict, max_retries: int = 4, base_delay: float = 6.0):
    """
    RATE-LIMIT-AWARE RETRY HELPER.

    WHY THIS EXISTS:
      Every generator (documents, planning, diagrams, requirement analysis) used
      to protect itself from Groq's free-tier rate limit with a blind
      `asyncio.sleep(5)` after every single call, and would silently DROP an
      item entirely if the call still failed (rate limit hit, transient
      network error, etc.).

      That produced two symptoms:
        1. "Generate Everything" took minutes even when nothing went wrong,
           because every call paid the fixed sleep cost regardless of need.
        2. Whichever item happened to hit the rate limit on a given run
           silently disappeared — a different item each time — which is why
           the output "pattern" felt inconsistent between runs.

      This helper replaces the blind sleep: it only waits when a call actually
      fails, retries with exponential backoff + jitter, and re-raises after
      exhausting retries so the caller can record a real failure instead of
      silently losing the item.

    Call chain.ainvoke(inputs) with exponential backoff + jitter on rate-limit
    or transient errors. Non-transient errors (bad prompt, auth failure, etc.)
    are raised immediately — retrying those would just waste time.

    Args:
        chain:       A LangChain runnable (e.g. `prompt | llm`).
        inputs:      The dict of template variables for .ainvoke().
        max_retries: How many attempts before giving up (default 4).
        base_delay:  Base seconds for exponential backoff (delay doubles each retry).

    Raises:
        The last exception encountered, if all retries are exhausted.
    """
    last_exc: Exception | None = None
    async with _GLOBAL_LLM_SEMAPHORE:
        for attempt in range(max_retries):
            try:
                return await chain.ainvoke(inputs)
            except Exception as e:
                last_exc = e
                if not _is_rate_limit_error(e) or attempt == max_retries - 1:
                    raise
                # Exponential backoff with jitter: 6-9s, 12-16s, 24-29s, ...
                delay = base_delay * (2 ** attempt) + random.uniform(0, 3)
                logger.warning(
                    f"Rate-limited / transient error (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {delay:.1f}s: {e}"
                )
                await asyncio.sleep(delay)
    raise last_exc  # pragma: no cover — loop always returns or raises above


def get_llm(temperature: float = 0.2, max_tokens: int = 8000):
    """
    Return a LangChain chat model instance for the configured provider.

    Reads LLM_PROVIDER from settings and returns the appropriate LangChain class:
      - "groq"   → ChatGroq  (langchain-groq package)
      - "openai" → ChatOpenAI (langchain-openai package)

    The returned object is duck-typed — all LangChain chat models share the
    same interface (.invoke(), .ainvoke(), pipe with | operator), so service
    code does not need to change when the provider changes.

    Args:
        temperature: Output randomness (0.0 = deterministic, 1.0 = creative).
                     Lower values produce more consistent structured JSON.
        max_tokens:  Maximum tokens in the response. WHY THIS MATTERS: without an
                     explicit cap, some providers fall back to a low default
                     completion length. Our documents/planning/diagram prompts ask
                     for fairly large structured JSON objects — if the response gets
                     cut off mid-JSON, parsing fails and the item is silently lost
                     or falls back to raw, unstructured text. 8000 tokens gives
                     enough headroom for the largest documents (SRS, functional spec).

    Returns:
        A LangChain BaseChatModel instance ready for chaining with prompts.

    Raises:
        ValueError: If LLM_PROVIDER is set to an unsupported value.
        ImportError: If the required LangChain provider package is not installed.
    """
    provider = settings.LLM_PROVIDER.lower().strip()

    if provider == "groq":
        # ── Groq provider ────────────────────────────────────────────────────
        # langchain-groq wraps the Groq REST API.
        # Groq's LPU hardware delivers extremely fast inference (~500 tokens/sec)
        # making it ideal for the long AI generation pipeline in this project.
        try:
            from langchain_groq import ChatGroq
        except ImportError:
            raise ImportError(
                "langchain-groq is not installed. "
                "Add 'langchain-groq' to requirements.txt and rebuild the container."
            )

        if not settings.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not set in .env. "
                "Set LLM_PROVIDER=openai and OPENAI_API_KEY, or add a valid GROQ_API_KEY."
            )

        logger.debug(
            f"Using Groq model: {settings.GROQ_MODEL} "
            f"(temperature={temperature}, max_tokens={max_tokens})"
        )
        return ChatGroq(
            model=settings.GROQ_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=60,  # Fail fast instead of hanging indefinitely on a stalled request
            api_key=settings.GROQ_API_KEY,  # Read from .env — never logged or printed
        )

    elif provider == "openai":
        # ── OpenAI provider ───────────────────────────────────────────────────
        from langchain_openai import ChatOpenAI

        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is not set in .env. "
                "Set a valid OPENAI_API_KEY or switch LLM_PROVIDER=groq."
            )

        logger.debug(
            f"Using OpenAI model: {settings.OPENAI_MODEL} "
            f"(temperature={temperature}, max_tokens={max_tokens})"
        )
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=60,
            api_key=settings.OPENAI_API_KEY,  # Read from .env — never logged or printed
        )

    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: '{provider}'. "
            "Supported values: 'groq', 'openai'. Set LLM_PROVIDER in backend/.env."
        )


def get_embeddings():
    """
    Return a LangChain embeddings instance for ChromaDB vector storage.

    WHY EMBEDDINGS ARE ALWAYS OPENAI (even when chat uses Groq):
      Groq does not offer an embedding API — only chat/completion endpoints.
      Embeddings are used by rag_service.py to convert text into vectors for
      storage and semantic search in ChromaDB.

    FALLBACK FOR GROQ-ONLY SETUPS (no OPENAI_API_KEY):
      If OPENAI_API_KEY is empty, we use HuggingFaceEmbeddings with the
      'all-MiniLM-L6-v2' model — a small (80MB), fast, locally-running model
      that produces good enough embeddings for the SE knowledge base search.
      This means RAG works even without any OpenAI key.

    Returns:
        A LangChain Embeddings instance compatible with langchain-chroma.
    """
    if settings.OPENAI_API_KEY:
        # ── OpenAI embeddings (preferred — best quality) ──────────────────────
        from langchain_openai import OpenAIEmbeddings
        logger.debug(f"Using OpenAI embeddings: {settings.OPENAI_EMBEDDING_MODEL}")
        return OpenAIEmbeddings(
            model=settings.OPENAI_EMBEDDING_MODEL,
            api_key=settings.OPENAI_API_KEY,
        )
    else:
        # ── Local HuggingFace embeddings fallback (no OpenAI key needed) ───────
        # sentence-transformers/all-MiniLM-L6-v2 runs entirely locally.
        # First run downloads ~80MB model weights from HuggingFace (cached after).
        # Quality is lower than OpenAI embeddings but fully functional for RAG.
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
        except ImportError:
            raise ImportError(
                "sentence-transformers is not installed and OPENAI_API_KEY is not set. "
                "Either set OPENAI_API_KEY in .env, or add 'sentence-transformers' "
                "and 'langchain-community' to requirements.txt."
            )
        logger.info(
            "OPENAI_API_KEY not set — using local HuggingFace embeddings (all-MiniLM-L6-v2). "
            "Set OPENAI_API_KEY for higher-quality RAG context."
        )
        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")