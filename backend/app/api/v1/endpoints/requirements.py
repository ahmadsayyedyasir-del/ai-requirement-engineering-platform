"""requirements.py — AI analysis trigger + requirement CRUD (Phase 3)."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project, ProjectStatus
from app.models.requirement import Requirement, RequirementCategory
from app.schemas import RequirementOut, RequirementUpdate, AnalysisRequest
from app.api.v1.endpoints.auth import get_current_user
from app.services.requirement_analysis import run_requirement_analysis

router = APIRouter()


async def _get_project_or_404(project_id: uuid.UUID, user: User, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.post("/analyze", status_code=202)
async def trigger_analysis(
    project_id: uuid.UUID,
    payload: AnalysisRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start the 5-node LangGraph pipeline. Returns 202 immediately."""
    project = await _get_project_or_404(project_id, current_user, db)
    if project.status == ProjectStatus.analyzing:
        raise HTTPException(status_code=409, detail="Analysis already in progress")
    project.status = ProjectStatus.analyzing
    await db.flush()
    background_tasks.add_task(run_requirement_analysis, project_id=project_id, input_ids=payload.input_ids)
    return {"message": "Analysis started", "project_id": str(project_id)}


@router.get("/", response_model=list[RequirementOut])
async def list_requirements(
    project_id: uuid.UUID,
    category: RequirementCategory | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    query = (
        select(Requirement)
        .where(Requirement.project_id == project_id, Requirement.is_active == True)
        .order_by(Requirement.category, Requirement.req_id)
    )
    if category:
        query = query.where(Requirement.category == category)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{req_id_or_uuid}", response_model=RequirementOut)
async def get_requirement(
    project_id: uuid.UUID,
    req_id_or_uuid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    try:
        clause = Requirement.id == uuid.UUID(req_id_or_uuid)
    except ValueError:
        clause = Requirement.req_id == req_id_or_uuid
    result = await db.execute(select(Requirement).where(Requirement.project_id == project_id, clause))
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req


@router.patch("/{requirement_id}", response_model=RequirementOut)
async def update_requirement(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    payload: RequirementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == project_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if payload.title is not None:
        req.title = payload.title
    if payload.description is not None:
        req.description = payload.description
    if payload.priority is not None:
        req.priority = payload.priority
    req.version += 1
    await db.flush()
    return req


@router.delete("/{requirement_id}", status_code=204)
async def delete_requirement(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete — sets is_active=False so document traceability is preserved."""
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == project_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    req.is_active = False
    await db.flush()
