"""
schemas/project.py — Pydantic schemas for project create / update / response.

WHAT ARE SCHEMAS?
  Schemas define the "contract" between the API and its clients.
  They specify what fields a request body must contain (ProjectCreate),
  what fields are optional for partial updates (ProjectUpdate),
  and what fields a response will include (ProjectOut).

  Important: ProjectOut does NOT include owner_id (privacy) and does NOT
  expose internal fields like relationships to children (inputs, requirements).
  Clients get what they need, nothing more.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    """
    Request body for POST /projects/.

    Minimum required: just a name.
    description and domain are optional extras that help the AI tailor its analysis.
    """
    name: str = Field(
        min_length=2,    # At least 2 characters — "x" alone is not a useful project name
        max_length=255,  # Matches the DB column length
    )
    description: str | None = None   # Optional project overview text
    domain: str | None = Field(
        default=None,
        max_length=100,  # Short domain tag: "fintech", "healthcare", "ecommerce"
    )


class ProjectUpdate(BaseModel):
    """
    Request body for PATCH /projects/{id}.

    All fields are optional — PATCH = partial update.
    Only include the fields you want to change.
    Note: status is NOT here because it's managed internally by the AI pipeline,
    not set directly by users.
    """
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    domain: str | None = None


class ProjectOut(BaseModel):
    """
    Response body whenever a project is returned.

    Includes everything a UI needs to display a project:
    - ID (for building URLs like /projects/{id}/requirements)
    - Name and description (for display)
    - Domain (for the tag pill)
    - Status (for the status badge and pipeline progression UI)
    - Timestamps (for "created 2 days ago" display)

    Intentionally excludes: owner_id (not needed by the client, slight privacy benefit).
    from_attributes=True allows building from SQLAlchemy ORM objects.
    """
    id: uuid.UUID
    name: str
    description: str | None
    domain: str | None
    status: ProjectStatus      # draft → analyzing → analyzed → completed
    # Per-item outcome of the last "Generate Everything" run, e.g.
    # {"documents": {"srs": "ok", "brd": "failed: ..."}, "planning": {...}, "diagrams": {...}}
    # Empty dict until generation has run at least once.
    generation_errors: dict = {}
    created_at: datetime       # Used for sorting "newest first" in the dashboard
    updated_at: datetime       # Used for "last modified X ago" display

    model_config = {"from_attributes": True}