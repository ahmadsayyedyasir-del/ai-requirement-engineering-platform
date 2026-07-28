"""review.py — AI Review Engine endpoints (Phase 7)."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.review import ReviewReport
from app.schemas import ReviewReportOut
from app.api.v1.endpoints.auth import get_current_user
from app.services.review_engine import run_review

router = APIRouter()


async def _get_project_or_404(project_id: uuid.UUID, user: User, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.post("/run", status_code=202)
async def trigger_review(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run the second-pass AI quality review. Returns 202 immediately."""
    await _get_project_or_404(project_id, current_user, db)
    background_tasks.add_task(run_review, project_id=project_id)
    return {"message": "Review started", "project_id": str(project_id)}


@router.get("/", response_model=list[ReviewReportOut])
async def list_reviews(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(ReviewReport)
        .where(ReviewReport.project_id == project_id)
        .order_by(ReviewReport.version.desc())
    )
    return result.scalars().all()


@router.get("/latest", response_model=ReviewReportOut)
async def get_latest_review(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(ReviewReport)
        .where(ReviewReport.project_id == project_id)
        .order_by(ReviewReport.version.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="No review report found. Run POST /review/run first.")
    return report


@router.get("/{report_id}", response_model=ReviewReportOut)
async def get_review(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(ReviewReport).where(ReviewReport.id == report_id, ReviewReport.project_id == project_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Review report not found")
    return report
