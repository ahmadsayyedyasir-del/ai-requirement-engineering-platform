"""planning.py — Planning artifact generation and retrieval (Phase 5)."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.planning import PlanningArtifact, PlanningType
from app.schemas import PlanningArtifactOut, GeneratePlanningRequest
from app.api.v1.endpoints.auth import get_current_user
from app.services.planning_generator import generate_planning
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
async def generate_planning_artifacts(
    project_id: uuid.UUID,
    payload: GeneratePlanningRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(project_id, current_user, db)

    planning_types = payload.planning_types
    if payload.retry_failed_only:
        failed = failed_items(project.generation_errors, "planning")
        if not failed:
            return {"message": "Nothing to retry.", "planning_types": []}
        planning_types = [PlanningType(name) for name in failed]

    background_tasks.add_task(generate_planning, project_id=project_id, planning_types=planning_types)
    return {
        "message": "Planning generation started",
        "project_id": str(project_id),
        "planning_types": [p.value for p in planning_types] if planning_types else "all",
    }


@router.get("/", response_model=list[PlanningArtifactOut])
async def list_planning(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(PlanningArtifact)
        .where(PlanningArtifact.project_id == project_id)
        .order_by(PlanningArtifact.planning_type)
    )
    return result.scalars().all()


@router.get("/{planning_type}", response_model=PlanningArtifactOut)
async def get_planning_artifact(
    project_id: uuid.UUID,
    planning_type: PlanningType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(PlanningArtifact).where(
            PlanningArtifact.project_id == project_id,
            PlanningArtifact.planning_type == planning_type,
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Planning artifact '{planning_type}' not generated yet.")
    return artifact
