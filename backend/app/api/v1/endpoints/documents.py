"""
documents.py — Document generation and version history endpoints (Phase 4).

WHY THIS FILE EXISTS:
  After the AI has extracted requirements (Phase 3), this file provides endpoints
  to GENERATE professional documents from those requirements (Phase 4), and to
  RETRIEVE those documents — including all historical versions.

  The actual generation logic (prompting GPT-4o, rendering markdown) lives in
  services/document_generator.py. This file handles:
    - Triggering generation as a background task (returns 202 immediately)
    - Fetching the latest version of any document type
    - Listing all historical versions (every regeneration creates a new version)
    - Fetching a specific version by number (for the diff viewer)

DOCUMENT TYPES SUPPORTED:
  srs, brd, user_stories, use_cases, acceptance_criteria,
  glossary, functional_spec, non_functional_spec

VERSIONING DESIGN:
  Each document type has:
    - ONE Document row (the "header" — tracks current_version number)
    - MANY DocumentVersion rows (one per generation — full content each time)
  This allows: history, diff comparison, and regeneration without data loss.

ENDPOINTS:
  POST  /generate                       → Generate one or all document types (202)
  GET   /                               → List all generated document headers
  GET   /{doc_type}                     → Get the LATEST version of a document
  GET   /{doc_type}/versions            → List ALL versions (for history/diff)
  GET   /{doc_type}/versions/{number}   → Get one specific version
  POST  /{doc_type}/regenerate          → Create a new version (preserves history)
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# selectinload tells SQLAlchemy to load the `versions` relationship in the same
# query (eager loading) instead of lazily on first access. Without this,
# accessing doc.versions in an async context would fail because the session is closed.
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.document import Document, DocumentVersion, DocumentType
from app.schemas.document import DocumentOut, DocumentVersionOut, GenerateDocumentRequest
from app.api.v1.endpoints.auth import get_current_user

# The service that does the actual AI document generation
from app.services.document_generator import generate_document
from app.services.generation_tracker import failed_items

router = APIRouter()


async def _get_project_or_404(
    project_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Project:
    """
    Verify the project belongs to the current user, or raise 404.
    Returning 404 (not 403) for wrong-owner prevents UUID enumeration attacks.
    """
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.id,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


# ── TRIGGER GENERATION ─────────────────────────────────────────────────────────

@router.post("/generate", status_code=202)
async def generate_documents(
    project_id: uuid.UUID,
    payload: GenerateDocumentRequest,  # {doc_types: [...]} or null = generate ALL types
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger AI document generation as a background task.

    HOW IT WORKS:
      - Returns 202 Accepted immediately (does NOT wait for generation to finish)
      - Generation runs in the background for each document type
      - Each type takes ~5–15 seconds (one GPT-4o call per document)
      - Poll GET /documents/ to see when documents appear

    WHAT GETS GENERATED (if doc_types is None = all):
      SRS, BRD, User Stories, Use Cases, Acceptance Criteria, Glossary,
      Functional Spec, Non-Functional Spec

    PARTIAL GENERATION:
      Pass doc_types=["srs", "brd"] to generate only specific documents.
      Useful for regenerating just one document after requirements change.

    RETRY FAILED ONLY:
      Pass retry_failed_only=true to regenerate just the document types that
      failed on the previous "Generate Everything" run, instead of everything.
    """
    project = await _get_project_or_404(project_id, current_user, db)

    doc_types = payload.doc_types
    if payload.retry_failed_only:
        failed = failed_items(project.generation_errors, "documents")
        if not failed:
            return {"message": "Nothing to retry — no failed documents on record.", "doc_types": []}
        doc_types = [DocumentType(name) for name in failed]

    # Queue the generator — it runs after this response returns
    background_tasks.add_task(
        generate_document,
        project_id=project_id,
        doc_types=doc_types,  # None = generate all 8 document types
    )
    return {
        "message": "Document generation started",
        "doc_types": [d.value for d in doc_types] if doc_types else "all",
    }


# ── LIST ALL GENERATED DOCUMENTS ──────────────────────────────────────────────

@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all document headers for a project.

    Returns one entry per document TYPE that has been generated.
    Each entry shows the document type, title, and current version number.

    The `selectinload` preloads the versions relationship efficiently:
    without it, accessing doc.versions after the session closes raises an error.
    Ordered alphabetically by doc_type for consistent UI display.
    """
    await _get_project_or_404(project_id, current_user, db)

    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))  # Eagerly load version list
        .where(Document.project_id == project_id)
        .order_by(Document.doc_type)               # Alphabetical order
    )
    return result.scalars().all()


# ── GET LATEST VERSION OF A DOCUMENT ──────────────────────────────────────────

@router.get("/{doc_type}", response_model=DocumentVersionOut)
async def get_document_latest(
    project_id: uuid.UUID,
    doc_type: DocumentType,     # FastAPI validates this against the DocumentType enum
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the LATEST (most recently generated) version of a specific document.

    This is what the Documents page in the frontend calls to display content.
    Returns the full document: both content_json (structured) and
    content_markdown (rendered, for display with react-markdown).

    WHY doc.versions[0]?
      The `versions` relationship is ordered by version_number DESC.
      So index [0] is always the highest version number = the most recent.
    """
    await _get_project_or_404(project_id, current_user, db)

    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(
            Document.project_id == project_id,
            Document.doc_type == doc_type,
        )
    )
    doc = result.scalar_one_or_none()

    # 404 if this document type hasn't been generated yet for this project
    if not doc or not doc.versions:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{doc_type}' not generated yet. Trigger generation first.",
        )

    # versions is ordered DESC — first element is the latest
    return doc.versions[0]


# ── LIST ALL VERSIONS OF A DOCUMENT ───────────────────────────────────────────

@router.get("/{doc_type}/versions", response_model=list[DocumentVersionOut])
async def list_document_versions(
    project_id: uuid.UUID,
    doc_type: DocumentType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List ALL historical versions of a specific document type.

    Use this endpoint to populate a "version history" UI or to find
    two version numbers to pass to the diff endpoint.

    Versions are ordered newest first (version 3, 2, 1).
    Each version includes its full content — useful for rollback UI.
    """
    await _get_project_or_404(project_id, current_user, db)

    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(
            Document.project_id == project_id,
            Document.doc_type == doc_type,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{doc_type}' not found",
        )
    return doc.versions  # Ordered DESC by version_number


# ── GET ONE SPECIFIC VERSION ───────────────────────────────────────────────────

@router.get("/{doc_type}/versions/{version_number}", response_model=DocumentVersionOut)
async def get_document_version(
    project_id: uuid.UUID,
    doc_type: DocumentType,
    version_number: int,        # e.g., 1, 2, 3 — the specific version to retrieve
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get one specific version of a document by its version number.

    Used by the diff viewer (bonus feature) which needs to fetch version N
    and version M to compute a diff between them.

    For example: GET /documents/srs/versions/1 returns the very first
    generated SRS, even if it has been regenerated 5 times since.
    """
    await _get_project_or_404(project_id, current_user, db)

    # First, find the document header row
    result = await db.execute(
        select(Document).where(
            Document.project_id == project_id,
            Document.doc_type == doc_type,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Then find the specific version row by its number
    ver_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.version_number == version_number,
        )
    )
    version = ver_result.scalar_one_or_none()
    if not version:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version_number} not found",
        )
    return version


# ── REGENERATE A DOCUMENT ──────────────────────────────────────────────────────

@router.post("/{doc_type}/regenerate", status_code=202)
async def regenerate_document(
    project_id: uuid.UUID,
    doc_type: DocumentType,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Regenerate a single document type, creating a new version.

    WHY REGENERATE?
      After editing requirements manually (e.g., changing priorities or descriptions),
      the documents may be out of date. Regenerating creates a new version (v2, v3...)
      with the updated content while keeping the old version in history.

    This way you can always compare the old version vs new version in the diff viewer.
    Returns 202 — generation is asynchronous.
    """
    await _get_project_or_404(project_id, current_user, db)

    # Queue regeneration of just this one document type
    background_tasks.add_task(
        generate_document,
        project_id=project_id,
        doc_types=[doc_type],  # Regenerate this type only
    )
    return {
        "message": f"Regenerating {doc_type}",
        "project_id": str(project_id),
    }