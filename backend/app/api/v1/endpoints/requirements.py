"""
requirements.py — Requirement analysis trigger and requirement management endpoints (Phase 3).

WHY THIS FILE EXISTS:
  This is the gateway to the most important feature in the platform — the AI
  requirement analysis pipeline. It exposes two things:
    1. A way to TRIGGER the AI pipeline    (POST /analyze → returns 202 immediately)
    2. A way to READ and MANAGE the results (GET / PATCH / DELETE requirements)

  The actual AI work happens in services/requirement_analysis.py. This file
  just validates requests, queues background tasks, and serves results from DB.

HTTP 202 vs 200:
  200 OK       = "I did the work, here's the result"
  202 Accepted = "I received your request and started work — check back later"
  We use 202 because GPT-4o can take 30–60 seconds, so we never make the
  client wait synchronously for a response.

ENDPOINTS:
  POST  /analyze           → Start the AI pipeline (background task, returns 202)
  GET   /                  → List all requirements (optional ?category= filter)
  GET   /{id}              → Get one requirement by UUID or req_id like "FR-001"
  PATCH /{id}              → Manually edit a requirement's title / description / priority
  DELETE /{id}             → Soft-delete (sets is_active=False, keeps the row)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project, ProjectStatus
from app.models.requirement import Requirement, RequirementCategory
from app.schemas.requirement import RequirementOut, RequirementUpdate, AnalysisRequest
from app.api.v1.endpoints.auth import get_current_user

# The LangGraph AI pipeline — called as a background task so the API
# returns instantly without waiting for GPT-4o to finish
from app.services.requirement_analysis import run_requirement_analysis

router = APIRouter()


# ── SHARED HELPER ──────────────────────────────────────────────────────────────

async def _get_project_or_404(
    project_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Project:
    """
    Fetch a project owned by the current user, or raise HTTP 404.

    WHY NOT 403 FOR "WRONG OWNER"?
      If we returned 403 (Forbidden) for "not your project" and 404 for "doesn't
      exist", an attacker could enumerate valid project UUIDs by watching which
      error code they get back. Always returning 404 prevents that information leak.
    """
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.id,  # Security: user can only access their own projects
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


# ── TRIGGER AI ANALYSIS ────────────────────────────────────────────────────────

@router.post("/analyze", status_code=202)
async def trigger_analysis(
    project_id: uuid.UUID,
    payload: AnalysisRequest,            # Optional: {input_ids: [...]} or null = use all
    background_tasks: BackgroundTasks,   # FastAPI's built-in background task runner
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Kick off the 5-node LangGraph AI requirement analysis pipeline.

    WHAT HAPPENS STEP BY STEP:
      1. This endpoint verifies ownership and checks no analysis is already running
      2. Sets project.status = "analyzing" so the UI can show a spinner
      3. Queues the background task (the heavy AI work)
      4. Returns 202 IMMEDIATELY — the client doesn't wait for GPT-4o

    WHAT THE BACKGROUND PIPELINE DOES (over the next 30–60 seconds):
      node 1 — Loads all raw text from RequirementInput rows for this project
      node 2 — Queries ChromaDB for relevant SE knowledge (RAG context)
      node 3 — Sends everything to GPT-4o with a structured extraction prompt
      node 4 — Parses the JSON response, assigns FR-001/NFR-003 style IDs
      node 5 — Saves all requirements to PostgreSQL, updates project to "analyzed"

    HOW TO KNOW WHEN IT'S DONE:
      Poll GET /projects/{id} — when status becomes "analyzed", the pipeline finished.
      Then call GET /requirements/ to see all extracted requirements.

    ERROR HANDLING:
      If the pipeline fails, project status reverts to "draft" and the error
      is logged. The user can try again by calling this endpoint again.
    """
    project = await _get_project_or_404(project_id, current_user, db)

    # Guard against running two analyses simultaneously — they would write
    # conflicting requirement rows for the same project.
    if project.status == ProjectStatus.analyzing:
        raise HTTPException(
            status_code=409,  # 409 Conflict = resource is in an incompatible state
            detail="Analysis already in progress",
        )

    # Update status immediately so the frontend can show a "Analyzing…" indicator.
    # This is flushed (written to DB) before the response is sent.
    project.status = ProjectStatus.analyzing
    await db.flush()

    # Queue the AI pipeline. This runs AFTER the 202 response is sent.
    # input_ids=None means "use ALL inputs belonging to this project"
    background_tasks.add_task(
        run_requirement_analysis,
        project_id=project_id,
        input_ids=payload.input_ids,  # Pass specific input IDs if the user selected some
    )

    return {"message": "Analysis started", "project_id": str(project_id)}


# ── LIST REQUIREMENTS ──────────────────────────────────────────────────────────

@router.get("/", response_model=list[RequirementOut])
async def list_requirements(
    project_id: uuid.UUID,
    # Optional query string filter: GET /requirements/?category=functional
    # Query(default=None) means the parameter is optional — omitting it returns everything
    category: RequirementCategory | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all active requirements for a project.

    Returns ALL 8 requirement categories by default (functional, non_functional,
    user_role, business_rule, constraint, assumption, risk, dependency).

    Filter by a single category using: ?category=functional

    Soft-deleted requirements (is_active=False) are never included.
    Results are ordered by category then req_id so FR-001, FR-002, FR-003
    always appear in logical order across all categories.
    """
    await _get_project_or_404(project_id, current_user, db)

    # Base query: all active requirements for this project
    query = (
        select(Requirement)
        .where(
            Requirement.project_id == project_id,
            Requirement.is_active == True,  # Exclude soft-deleted requirements
        )
        .order_by(Requirement.category, Requirement.req_id)  # Sort for consistent display
    )

    # If a category filter was passed, narrow the results
    if category:
        query = query.where(Requirement.category == category)

    result = await db.execute(query)
    return result.scalars().all()


# ── GET ONE REQUIREMENT ────────────────────────────────────────────────────────

@router.get("/{req_id_or_uuid}", response_model=RequirementOut)
async def get_requirement(
    project_id: uuid.UUID,
    # This path parameter accepts EITHER a UUID ("3f2504e0-...") OR "FR-001"
    req_id_or_uuid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch one requirement — accepts either its UUID or its human-readable ID.

    WHY SUPPORT BOTH FORMATS?
      Internal code references requirements by UUID (stable, globally unique).
      Documentation and human conversation uses "FR-001" format.
      Both should work for easy use from any context.

    Implementation: try to parse as UUID first.
    If that fails (ValueError), treat the string as a req_id like "FR-001".
    """
    await _get_project_or_404(project_id, current_user, db)

    try:
        # Attempt to parse as UUID — raises ValueError if it's not valid UUID format
        rid = uuid.UUID(req_id_or_uuid)
        clause = Requirement.id == rid               # Search by database UUID column
    except ValueError:
        # Not a UUID, so treat it as a human-readable req_id string
        clause = Requirement.req_id == req_id_or_uuid   # Search by req_id like "FR-001"

    result = await db.execute(
        select(Requirement).where(
            Requirement.project_id == project_id,
            clause,  # Dynamic WHERE condition chosen above
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req


# ── MANUALLY UPDATE A REQUIREMENT ─────────────────────────────────────────────

@router.patch("/{requirement_id}", response_model=RequirementOut)
async def update_requirement(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    payload: RequirementUpdate,  # All fields optional: title | description | priority
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually edit an AI-generated requirement.

    WHY ALLOW MANUAL EDITING?
      The AI is not always perfect. An analyst may need to:
        - Fix an imprecise or ambiguous description
        - Upgrade priority ("this should be must_have, not could_have")
        - Add missing implementation details

    PATCH = partial update — only send the fields you want to change.
    The `version` counter increments with each edit, so you can track
    how many times a requirement has been modified since the AI generated it.
    """
    await _get_project_or_404(project_id, current_user, db)

    result = await db.execute(
        select(Requirement).where(
            Requirement.id == requirement_id,
            Requirement.project_id == project_id,
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # Only update the fields that were explicitly provided — skip None fields
    if payload.title is not None:
        req.title = payload.title
    if payload.description is not None:
        req.description = payload.description
    if payload.priority is not None:
        req.priority = payload.priority

    # Track edit history: how many human edits since AI generation?
    req.version += 1

    await db.flush()  # Stage the UPDATE; get_db commits after the request finishes
    return req


# ── SOFT-DELETE A REQUIREMENT ──────────────────────────────────────────────────

@router.delete("/{requirement_id}", status_code=204)
async def delete_requirement(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Soft-delete a requirement (marks it inactive without removing the row).

    WHY SOFT DELETE INSTEAD OF HARD DELETE?
      Hard deleting a requirement could break document traceability. If SRS
      references "FR-007" and we hard-delete it, the document becomes inconsistent.

      Soft delete keeps the row (for audit) while hiding it from normal queries
      (all reads filter on is_active=True). An admin could even restore it later
      by setting is_active=True again.

    Returns 204 No Content on success — standard HTTP for "deleted, nothing to return".
    """
    await _get_project_or_404(project_id, current_user, db)

    result = await db.execute(
        select(Requirement).where(
            Requirement.id == requirement_id,
            Requirement.project_id == project_id,
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # Soft delete: flip the flag — the row stays in the DB
    req.is_active = False
    await db.flush()
    # Normal GET /requirements/ queries always filter is_active=True, so this
    # requirement will no longer appear to the user.
