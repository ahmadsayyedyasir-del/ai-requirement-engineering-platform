"""
services/rag_service.py — ChromaDB vector store integration for RAG (Phase 3).

WHAT IS RAG?
  RAG = Retrieval-Augmented Generation.
  Before prompting the LLM, we search a knowledge base for relevant SE
  best practices and inject them into the prompt as context — helping
  the AI produce better-structured, more complete requirements.

GROQ-ONLY MODE (no OPENAI_API_KEY set):
  Embeddings need a vector model. OpenAI provides one; Groq does not.
  When OPENAI_API_KEY is empty, ALL RAG functions return silently without
  crashing. The LLM (Groq llama-3.3-70b) is powerful enough to extract
  good requirements on its own — RAG is an enhancement, not a requirement.

  To enable full RAG: add a valid OPENAI_API_KEY to backend/.env.
  The embedding cost is negligible (fractions of a cent per analysis run).
"""

import logging
from typing import Optional
from langchain_core.documents import Document
from app.core.config import settings

logger = logging.getLogger("reqeng.rag")

# ── RAG enabled flag ──────────────────────────────────────────────────────────
# RAG requires OpenAI embeddings. Skip silently when key is missing/placeholder.
_RAG_ENABLED: bool = bool(
    settings.OPENAI_API_KEY
    and settings.OPENAI_API_KEY.strip()
    and settings.OPENAI_API_KEY not in ("sk-your-openai-api-key-here", "")
)

if _RAG_ENABLED:
    logger.info("RAG enabled — using OpenAI embeddings with ChromaDB.")
else:
    logger.info(
        "RAG disabled — OPENAI_API_KEY not set. "
        "AI analysis runs without knowledge base context. "
        "Set OPENAI_API_KEY in backend/.env to enable RAG."
    )

# Singletons — only initialised when RAG is enabled
_chroma_client = None
_knowledge_store = None
_project_store = None


def _get_chroma_client():
    """Return singleton ChromaDB HTTP client. Only called when RAG is enabled."""
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        _chroma_client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,  # "chroma" in Docker
            port=settings.CHROMA_PORT,  # 8000 in Docker
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def _get_embeddings():
    """Return OpenAI embeddings. Only called when RAG is enabled."""
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(
        model=settings.OPENAI_EMBEDDING_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )


def get_knowledge_store():
    """Return LangChain Chroma wrapper for the SE knowledge base."""
    global _knowledge_store
    if _knowledge_store is None:
        from langchain_chroma import Chroma
        _knowledge_store = Chroma(
            client=_get_chroma_client(),
            collection_name=settings.CHROMA_COLLECTION_KNOWLEDGE,
            embedding_function=_get_embeddings(),
        )
    return _knowledge_store


def get_project_store():
    """Return LangChain Chroma wrapper for project requirement embeddings."""
    global _project_store
    if _project_store is None:
        from langchain_chroma import Chroma
        _project_store = Chroma(
            client=_get_chroma_client(),
            collection_name=settings.CHROMA_COLLECTION_PROJECTS,
            embedding_function=_get_embeddings(),
        )
    return _project_store


async def search_knowledge_base(query: str, k: int = 5) -> list[Document]:
    """
    Search the SE knowledge base for relevant context.
    Returns empty list silently when RAG is disabled — the pipeline handles
    empty context gracefully and Groq still produces good results.
    """
    if not _RAG_ENABLED:
        return []  # Silent no-op — LLM works fine without RAG context

    try:
        import asyncio
        return await asyncio.to_thread(
            get_knowledge_store().similarity_search, query, k=k
        )
    except Exception as e:
        logger.warning(f"RAG search failed (continuing without context): {e}")
        return []


async def index_project_requirements(
    project_id: str,
    requirements: list[dict],
) -> None:
    """
    Index extracted requirements in ChromaDB for future cross-project RAG.
    Silently skips when RAG is disabled.
    """
    if not _RAG_ENABLED:
        return  # Silent no-op

    try:
        import asyncio
        docs = [
            Document(
                page_content=f"{r['req_id']}: {r['title']}\n{r['description']}",
                metadata={
                    "project_id": project_id,
                    "req_id": r["req_id"],
                    "category": r["category"],
                },
            )
            for r in requirements
        ]
        await asyncio.to_thread(get_project_store().add_documents, docs)
        logger.info(f"Indexed {len(docs)} requirements for project {project_id}")
    except Exception as e:
        logger.warning(f"Failed to index requirements: {e}")


async def seed_knowledge_base() -> None:
    """
    Seed ChromaDB with SE best-practice documents.
    Silently skips when OPENAI_API_KEY is not configured — no crash, no error.
    """
    if not _RAG_ENABLED:
        logger.info("RAG seeding skipped — OPENAI_API_KEY not configured.")
        return  # Clean no-op

    try:
        import asyncio
        store = get_knowledge_store()

        # Check if already seeded — idempotent
        existing = await asyncio.to_thread(
            store.similarity_search, "functional requirements", k=1
        )
        if existing:
            logger.info("Knowledge base already seeded, skipping.")
            return

        seed_docs = [
            Document(
                page_content=(
                    "Functional requirements describe what the system should DO: "
                    "features, capabilities, behaviors the system must exhibit. "
                    "Example: 'Users shall be able to reset their password via email.'"
                ),
                metadata={"type": "definition", "topic": "functional_requirements"},
            ),
            Document(
                page_content=(
                    "Non-functional requirements specify HOW WELL the system performs: "
                    "performance, scalability, security, reliability, usability, maintainability. "
                    "Example: 'Login page loads in under 2 seconds for 95% of requests.'"
                ),
                metadata={"type": "definition", "topic": "non_functional_requirements"},
            ),
            Document(
                page_content=(
                    "User stories: 'As a [role], I want [goal], so that [benefit]'. "
                    "Story points: 1=trivial, 3=medium, 5=large, 8=complex, 13=epic (split)."
                ),
                metadata={"type": "template", "topic": "user_stories"},
            ),
            Document(
                page_content=(
                    "Acceptance criteria — Gherkin format: "
                    "Given [precondition] When [action] Then [expected outcome]. "
                    "Write at least 2 scenarios per requirement."
                ),
                metadata={"type": "template", "topic": "acceptance_criteria"},
            ),
            Document(
                page_content=(
                    "SRS structure: Introduction, Overall Description, "
                    "Functional Requirements (each with ID, description, priority), "
                    "Non-Functional Requirements, System Constraints, Appendix."
                ),
                metadata={"type": "structure", "topic": "srs"},
            ),
            Document(
                page_content=(
                    "MoSCoW prioritization: Must Have (MVP critical), "
                    "Should Have (important but not blocking launch), "
                    "Could Have (nice-to-have), Won't Have (deferred)."
                ),
                metadata={"type": "methodology", "topic": "prioritization"},
            ),
            Document(
                page_content=(
                    "Sprint planning: 2-week iterations, each delivering working software. "
                    "Team velocity: 20-30 story points per developer per sprint."
                ),
                metadata={"type": "methodology", "topic": "sprint_planning"},
            ),
            Document(
                page_content=(
                    "Cost estimation: 1 story point = 4-8 hours. Add 20% contingency. "
                    "Include: labor, infrastructure, licenses, QA, project management."
                ),
                metadata={"type": "methodology", "topic": "cost_estimation"},
            ),
            Document(
                page_content=(
                    "Risk categories: Technical (new tech, integration complexity), "
                    "Schedule (unclear requirements, scope creep), "
                    "Resource (skills gaps), Business (regulatory, market risk)."
                ),
                metadata={"type": "methodology", "topic": "risk_assessment"},
            ),
        ]

        await asyncio.to_thread(store.add_documents, seed_docs)
        logger.info(f"Seeded knowledge base with {len(seed_docs)} documents.")

    except Exception as e:
        logger.warning(f"Knowledge base seeding failed: {e}. RAG context will be empty.")
