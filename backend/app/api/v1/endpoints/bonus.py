"""bonus.py — Bonus features: MoSCoW AI, version diff, scope comparator."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.document import DocumentType
from app.api.v1.endpoints.auth import get_current_user
from app.services.moscow_prioritizer import run_moscow_prioritization
from app.services.diff_service import get_document_diff, compare_requirement_sets

router = APIRouter()


async def _get_project_or_404(project_id: uuid.UUID, user: User, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.post("/projects/{project_id}/prioritize/moscow")
async def moscow_prioritize(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-evaluate all requirement priorities using AI (MoSCoW framework)."""
    await _get_project_or_404(project_id, current_user, db)
    return await run_moscow_prioritization(project_id)


@router.get("/projects/{project_id}/documents/{doc_type}/diff")
async def document_diff(
    project_id: uuid.UUID,
    doc_type: DocumentType,
    version_a: int,
    version_b: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Line-level diff between two versions of a document."""
    await _get_project_or_404(project_id, current_user, db)
    try:
        return await get_document_diff(project_id, doc_type, version_a, version_b)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class RequirementSnapshot(BaseModel):
    req_id: str
    title: str
    description: str
    priority: str
    category: str


class CompareRequest(BaseModel):
    snapshot_a: list[RequirementSnapshot]
    snapshot_b: list[RequirementSnapshot]


@router.post("/projects/{project_id}/requirements/compare")
async def compare_requirements(
    project_id: uuid.UUID,
    payload: CompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compare two requirement snapshots to identify scope changes."""
    await _get_project_or_404(project_id, current_user, db)
    return await compare_requirement_sets(
        project_id,
        [s.model_dump() for s in payload.snapshot_a],
        [s.model_dump() for s in payload.snapshot_b],
    )
