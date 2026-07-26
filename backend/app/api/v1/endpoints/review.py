"""
review.py — AI Review Engine endpoints (Phase 7).

WHY THIS FILE EXISTS:
  Just because the AI generated requirements doesn't mean they're perfect.
  Phase 7 runs a SECOND AI pass — acting like a QA reviewer — that reads
  all requirements and documents and checks for quality issues.

  This file provides the endpoints to:
    1. TRIGGER the review (POST /run → 202 immediately)
    2. LIST all past review reports (every run creates a new version)
    3. GET the latest report (the one the Review page shows)
    4. GET a specific report by ID (for historical comparison)

WHAT THE REVIEW CHECKS FOR:
  - missing:     Requirements that obviously should exist but don't
  - conflict:    Two requirements that contradict each other
  - duplicate:   Two requirements saying the same thing differently
  - scope_gap:   Business areas mentioned in input but not covered by any requirement
  - risk:        Technical or business risks not captured as requirements
  - ambiguity:   Requirements too vague or subjective to implement

OUTPUT:
  A ReviewReport with:
    - quality_score (0–100): Overall requirement quality rating
    - summary: 2–3 sentence plain-English assessment
    - issues[]: List of specific problems, each with severity and suggestion
    - report_markdown: Full formatted report for the UI

VERSIONING:
  Every review run creates a NEW report (version 1, 2, 3...).
  History is preserved so you can see how quality improved after fixing issues.

ENDPOINTS:
  POST  /run          → Trigger the AI review (202 immediately)
  GET   /             → List all review reports for this project (history)
  GET   /latest       → Get the most recent review report
  GET   /{report_id}  → Get a specific review report by UUID
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.review import ReviewReport
from app.schemas.review import ReviewReportOut
from app.api.v1.endpoints.auth import get_current_user

# The second-pass AI reviewer service
from app.services.review_engine import run_review

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


@router.post("/run", status_code=202)
async def trigger_review(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run the AI second-pass quality review on this project's requirements.

    WHAT THIS TRIGGERS (in the background):
      1. Loads all active requirements from the DB
      2. Sends them to GPT-4o with a specialized reviewer prompt
      3. GPT-4o identifies issues (missing, conflicts, gaps, ambiguities)
      4. Assigns a quality score (0–100) and writes a detailed report
      5. Saves the ReviewReport to the DB (new version each run)

    Returns 202 immediately — poll GET /review/latest to see the result.
    Typical completion time: ~20–40 seconds.

    TIP: Run the review AFTER fixing requirements. Compare quality scores
    across runs to measure improvement (e.g., 58 → 72 → 85).
    """
    await _get_project_or_404(project_id, current_user, db)

    # Queue the review to run after this response is sent
    background_tasks.add_task(run_review, project_id=project_id)
    return {"message": "Review started", "project_id": str(project_id)}


@router.get("/", response_model=list[ReviewReportOut])
async def list_reviews(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all review reports for this project, newest first.

    Used to build a review history: "I ran the review 3 times and the
    quality score improved from 58 → 72 → 85 after fixing issues."
    """
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(ReviewReport)
        .where(ReviewReport.project_id == project_id)
        .order_by(ReviewReport.version.desc())  # Newest version first
    )
    return result.scalars().all()


@router.get("/latest", response_model=ReviewReportOut)
async def get_latest_review(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the most recently completed review report.

    This is what the Review page in the frontend displays by default.
    Uses ORDER BY version DESC LIMIT 1 — the most recent run.
    Returns 404 if no review has ever been run for this project.
    """
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(ReviewReport)
        .where(ReviewReport.project_id == project_id)
        .order_by(ReviewReport.version.desc())
        .limit(1)  # Only the latest one
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(
            status_code=404,
            detail="No review report found. Run POST /review/run first.",
        )
    return report


@router.get("/{report_id}", response_model=ReviewReportOut)
async def get_review(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a specific historical review report by its UUID.

    Used for comparing past reports: "what did the review say before we
    fixed the missing requirements?" Filter by project_id as a security check
    — users can only access reports from their own projects.
    """
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(ReviewReport).where(
            ReviewReport.id == report_id,
            ReviewReport.project_id == project_id,  # Security: must belong to this project
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Review report not found")
    return report
