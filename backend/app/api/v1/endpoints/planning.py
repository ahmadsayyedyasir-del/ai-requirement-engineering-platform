"""
planning.py — Planning artifact generation and retrieval endpoints (Phase 5).

WHY THIS FILE EXISTS:
  After requirements are extracted, a project still needs a software plan.
  This file triggers the AI planning generator and serves the results.
  The AI produces 8 distinct planning artifacts (see PlanningType enum).

WHAT GETS GENERATED:
  module_breakdown  — What software modules/components are needed?
  roadmap           — What are the development phases and milestones?
  sprints           — How is work divided into 2-week Agile sprints?
  team_composition  — What team roles and headcount are needed?
  tech_stack        — What technologies are recommended and why?
  timeline          — How many total weeks will the project take?
  cost_estimation   — What is the estimated budget (labor + infrastructure)?
  risk_assessment   — What are the key risks and mitigation strategies?

ENDPOINTS:
  POST  /generate           → Generate all planning artifacts (returns 202)
  GET   /                   → List all generated planning artifacts
  GET   /{planning_type}    → Get one specific artifact (e.g., /planning/roadmap)
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.planning import PlanningArtifact, PlanningType
from app.schemas.planning import PlanningArtifactOut, GeneratePlanningRequest
from app.api.v1.endpoints.auth import get_current_user
from app.services.planning_generator import generate_planning
from app.services.generation_tracker import failed_items

router = APIRouter()


async def _get_project_or_404(project_id: uuid.UUID, user: User, db: AsyncSession) -> Project:
    """Verify project ownership and return it, or raise 404."""
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
    """
    Generate planning artifacts for the project — all 8 types by default.

    RUNS IN THE BACKGROUND — returns 202 immediately.
    Poll GET /planning/ to see artifacts appear one by one as they complete.

    Prerequisites: requirements must be analyzed first (project status = "analyzed").
    The planning generator reads requirements from the DB to produce its output.

    RETRY FAILED ONLY:
      Pass retry_failed_only=true to regenerate just the artifact types that
      failed on the previous "Generate Everything" run, instead of everything.
    """
    project = await _get_project_or_404(project_id, current_user, db)

    planning_types = payload.planning_types
    if payload.retry_failed_only:
        failed = failed_items(project.generation_errors, "planning")
        if not failed:
            return {"message": "Nothing to retry — no failed planning artifacts on record.", "planning_types": []}
        planning_types = [PlanningType(name) for name in failed]

    background_tasks.add_task(
        generate_planning, project_id=project_id, planning_types=planning_types
    )

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
    """
    List all planning artifacts that have been generated for this project.

    Because generation runs in the background, this list grows over time
    as each artifact completes. You can poll this endpoint to watch progress.
    Results are ordered alphabetically by planning_type for consistent display.
    """
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
    planning_type: PlanningType,  # FastAPI validates this against the PlanningType enum
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get one specific planning artifact by its type.

    Example: GET /planning/cost_estimation returns the cost breakdown.
    Example: GET /planning/roadmap returns the phased development roadmap.

    Returns 404 if that artifact hasn't been generated yet.
    Each artifact includes both content (structured JSON) and summary_markdown
    (rendered markdown for display).
    """
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(PlanningArtifact).where(
            PlanningArtifact.project_id == project_id,
            PlanningArtifact.planning_type == planning_type,
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(
            status_code=404,
            detail=f"Planning artifact '{planning_type}' not generated yet.",
        )
    return artifact