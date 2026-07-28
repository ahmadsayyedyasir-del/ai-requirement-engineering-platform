"""diagrams.py — Mermaid.js diagram generation and retrieval (Phase 6)."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.diagram import Diagram, DiagramType
from app.schemas import DiagramOut, GenerateDiagramsRequest
from app.api.v1.endpoints.auth import get_current_user
from app.services.diagram_generator import generate_diagrams
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
async def generate_project_diagrams(
    project_id: uuid.UUID,
    payload: GenerateDiagramsRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(project_id, current_user, db)

    diagram_types = payload.diagram_types
    if payload.retry_failed_only:
        failed = failed_items(project.generation_errors, "diagrams")
        if not failed:
            return {"message": "Nothing to retry.", "diagram_types": []}
        diagram_types = [DiagramType(name) for name in failed]

    background_tasks.add_task(generate_diagrams, project_id=project_id, diagram_types=diagram_types)
    return {
        "message": "Diagram generation started",
        "project_id": str(project_id),
        "diagram_types": [d.value for d in diagram_types] if diagram_types else "all",
    }


@router.get("/", response_model=list[DiagramOut])
async def list_diagrams(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(Diagram).where(Diagram.project_id == project_id).order_by(Diagram.diagram_type)
    )
    return result.scalars().all()


@router.get("/{diagram_type}", response_model=DiagramOut)
async def get_diagram(
    project_id: uuid.UUID,
    diagram_type: DiagramType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(Diagram).where(Diagram.project_id == project_id, Diagram.diagram_type == diagram_type)
    )
    diagram = result.scalar_one_or_none()
    if not diagram:
        raise HTTPException(status_code=404, detail=f"Diagram '{diagram_type}' not generated yet.")
    return diagram
