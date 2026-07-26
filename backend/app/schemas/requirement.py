"""
schemas/requirement.py — Pydantic schemas for requirement analysis and management.

THREE SCHEMAS HERE:
  AnalysisRequest  → optional parameters for triggering the AI pipeline
  RequirementOut   → full requirement data for the API response
  RequirementUpdate → partial update body (all fields optional)
"""

import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.requirement import RequirementCategory, RequirementPriority


class AnalysisRequest(BaseModel):
    """
    Optional request body for POST /requirements/analyze.

    input_ids: If provided, only analyze these specific inputs.
               If None (omitted), the pipeline uses ALL inputs for the project.

    WHY OPTIONAL?
      Most of the time you want to analyze everything. But if you added
      one new input and only want to re-run analysis on that new one,
      you can pass just its ID.
    """
    input_ids: list[uuid.UUID] | None = None  # None = use all project inputs


class RequirementOut(BaseModel):
    """
    Full requirement data returned by all requirement endpoints.

    Contains everything a developer, analyst, or downstream service needs:
    - req_id: the human-readable ID (e.g., "FR-001") for traceability
    - category: what kind of requirement this is
    - priority: MoSCoW value (must_have, should_have, could_have, wont_have)
    - title + description: the actual content
    - metadata: extra fields the AI extracted (e.g., risk impact/likelihood)
    - version: how many times this requirement has been manually edited
    - is_active: False if soft-deleted (active reqs always have True)
    - timestamps: when created and last modified
    """
    id: uuid.UUID
    project_id: uuid.UUID
    category: RequirementCategory       # functional | non_functional | risk | ...
    priority: RequirementPriority       # must_have | should_have | could_have | wont_have
    req_id: str                         # "FR-001", "NFR-003", "RSK-002" etc.
    title: str                          # Short title (≤10 words)
    description: str                    # Full detailed description
    # Renamed from "metadata" — SQLAlchemy reserves that name on Declarative Base classes.
    # Contains extra AI-extracted fields (e.g., risk impact/likelihood for RSK- requirements).
    extra_metadata: dict | None         # Extra AI-extracted data (risk scores, etc.)
    version: int                        # 1 = AI-generated, 2+ = manually edited
    is_active: bool                     # False = soft-deleted
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RequirementUpdate(BaseModel):
    """
    Request body for PATCH /requirements/{id}.

    All fields are optional — only include what you want to change.
    An analyst might update just the priority, or just fix the description —
    they don't need to re-send fields they're not changing.
    """
    title: str | None = None                    # New title, or None to keep current
    description: str | None = None              # New description, or None to keep current
    priority: RequirementPriority | None = None # New MoSCoW priority, or None to keep current
