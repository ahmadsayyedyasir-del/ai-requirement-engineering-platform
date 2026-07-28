"""documents.py — Document generation and version history endpoints (Phase 4)."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload  # eager-loads versions so they're accessible after session closes

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.document import Document, DocumentVersion, DocumentType
from app.schemas import DocumentOut, DocumentVersionOut, GenerateDocumentRequest
from app.api.v1.endpoints.auth import get_current_user
from app.services.document_generator import generate_document
from app.core.generation_tracker import failed_items

router = APIRouter()


async def _get_project_or_404(project_id: uuid.UUID, user: User, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.post("/generate", status_code=202)
async def generate_documents(
    project_id: uuid.UUID,
    payload: GenerateDocumentRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(project_id, current_user, db)

    doc_types = payload.doc_types
    if payload.retry_failed_only:
        failed = failed_items(project.generation_errors, "documents")
        if not failed:
            return {"message": "Nothing to retry.", "doc_types": []}
        doc_types = [DocumentType(name) for name in failed]

    background_tasks.add_task(generate_document, project_id=project_id, doc_types=doc_types)
    return {"message": "Document generation started", "doc_types": [d.value for d in doc_types] if doc_types else "all"}


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.project_id == project_id)
        .order_by(Document.doc_type)
    )
    return result.scalars().all()


@router.get("/{doc_type}", response_model=DocumentVersionOut)
async def get_document_latest(
    project_id: uuid.UUID,
    doc_type: DocumentType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns the most recently generated version. versions is ordered DESC so [0] = latest."""
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.project_id == project_id, Document.doc_type == doc_type)
    )
    doc = result.scalar_one_or_none()
    if not doc or not doc.versions:
        raise HTTPException(status_code=404, detail=f"Document '{doc_type}' not generated yet.")
    return doc.versions[0]


@router.get("/{doc_type}/versions", response_model=list[DocumentVersionOut])
async def list_document_versions(
    project_id: uuid.UUID,
    doc_type: DocumentType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.project_id == project_id, Document.doc_type == doc_type)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_type}' not found")
    return doc.versions


@router.get("/{doc_type}/versions/{version_number}", response_model=DocumentVersionOut)
async def get_document_version(
    project_id: uuid.UUID,
    doc_type: DocumentType,
    version_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(Document).where(Document.project_id == project_id, Document.doc_type == doc_type)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    ver = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.version_number == version_number,
        )
    )
    version = ver.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found")
    return version


@router.post("/{doc_type}/regenerate", status_code=202)
async def regenerate_document(
    project_id: uuid.UUID,
    doc_type: DocumentType,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    background_tasks.add_task(generate_document, project_id=project_id, doc_types=[doc_type])
    return {"message": f"Regenerating {doc_type}", "project_id": str(project_id)}
