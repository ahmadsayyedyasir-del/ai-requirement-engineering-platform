"""
projects.py — Project CRUD endpoints (Create, Read, Update, Delete).

WHY THIS FILE EXISTS:
  A "project" is the container for everything in the system. Before submitting
  requirements or generating documents, a user must first create a project.
  This file provides the standard CRUD operations for projects.

  Note: A user can only see/modify their OWN projects. The `owner_id`
  filter on every query enforces this — there's no admin override here
  because projects are personal workspaces.

ENDPOINTS:
  POST   /projects/              → Create a new project
  GET    /projects/              → List all my projects
  GET    /projects/{id}          → Get one project
  PATCH  /projects/{id}          → Update project name/description/domain
  DELETE /projects/{id}          → Delete project (and all its artifacts via CASCADE)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


# ── CREATE PROJECT ─────────────────────────────────────────────────────────────

@router.post("/", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,              # Request body: name, description, domain
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # Authenticated user
):
    """
    Create a new project for the authenticated user.

    The new project starts in "draft" status — no analysis has run yet.
    The owner_id is automatically set to the current user's ID.

    Returns the created project with its auto-generated UUID.
    """
    # Build the new project object. Note: owner_id comes from the authenticated
    # user — not from the request body. Users can't create projects for others.
    project = Project(
        owner_id=current_user.id,           # Tied to the authenticated user
        name=payload.name,
        description=payload.description,
        domain=payload.domain,
        status=ProjectStatus.draft,         # Always starts as draft
    )
    db.add(project)      # Stage the INSERT
    await db.flush()     # Execute INSERT to get the auto-generated UUID back
    return project


# ── LIST MY PROJECTS ───────────────────────────────────────────────────────────

@router.get("/", response_model=list[ProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return all projects owned by the current user, newest first.

    The WHERE clause `Project.owner_id == current_user.id` ensures users
    only see their own projects — not other analysts' work.
    """
    result = await db.execute(
        select(Project)
        .where(Project.owner_id == current_user.id)  # Ownership filter — security boundary
        .order_by(Project.created_at.desc())          # Newest first for the dashboard
    )
    return result.scalars().all()


# ── GET ONE PROJECT ────────────────────────────────────────────────────────────

@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the details of a single project.

    Uses the shared helper _get_project_or_404 which:
      1. Filters by both project_id AND owner_id (security: can't access others' projects)
      2. Returns 404 if not found (same error for "doesn't exist" and "not yours")

    WHY SAME ERROR FOR BOTH CASES?
      If we returned 403 for "not your project" and 404 for "doesn't exist",
      an attacker could enumerate valid project IDs by watching the error code change.
      Returning 404 in both cases prevents this.
    """
    project = await _get_project_or_404(project_id, current_user, db)
    return project


# ── UPDATE PROJECT ─────────────────────────────────────────────────────────────

@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,  # All fields optional — PATCH = partial update
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update a project's name, description, or domain.

    Does NOT allow changing the status directly — status is managed internally
    by the AI pipeline (draft → analyzing → analyzed → completed).

    Only updates fields that are present in the request (partial update pattern).
    """
    project = await _get_project_or_404(project_id, current_user, db)

    # Only update fields that were explicitly provided in the request body.
    # This prevents accidentally overwriting a field with None.
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    if payload.domain is not None:
        project.domain = payload.domain

    await db.flush()  # Stage the UPDATE
    return project


# ── DELETE PROJECT ─────────────────────────────────────────────────────────────

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Permanently delete a project and all its artifacts.

    CASCADES — Because every related table (requirements, documents, diagrams, etc.)
    has `ondelete="CASCADE"` on its project_id foreign key, deleting a project
    automatically deletes ALL of its:
      - requirement inputs
      - extracted requirements
      - generated documents (and all versions)
      - planning artifacts
      - diagrams
      - review reports

    Returns 204 No Content (success with no body) — the resource is gone.
    """
    project = await _get_project_or_404(project_id, current_user, db)
    await db.delete(project)  # The cascades handle everything else


# ── SHARED HELPER ─────────────────────────────────────────────────────────────

async def _get_project_or_404(
    project_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Project:
    """
    Fetch a project that belongs to the current user, or raise 404.

    WHY A HELPER FUNCTION?
      Every endpoint above needs: "find this project, verify it belongs to me."
      Extracting this into a helper avoids copy-pasting the same 5 lines.

    WHY FILTER BY BOTH project_id AND owner_id?
      The owner_id filter is the security boundary. Without it, knowing someone
      else's project UUID would allow you to access their data.
      By filtering on both, a user can only get 200 OK for their OWN projects.
    """
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id,  # <-- Security: ownership check
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        # 404 whether the project doesn't exist OR belongs to another user
        raise HTTPException(status_code=404, detail="Project not found")
    return project
