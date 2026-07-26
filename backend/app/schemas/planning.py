"""
schemas/planning.py — Pydantic schemas for planning artifact generation and response.

WHY THIS FILE EXISTS:
  Planning artifacts are generated in bulk (one call generates all 8 types),
  but retrieved individually (one per planning_type per project).
  These two schemas handle both patterns.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.planning import PlanningType


class GeneratePlanningRequest(BaseModel):
    """
    Request body for POST /planning/generate.

    By default, generates ALL 8 artifact types from the project's existing
    requirements — the artifacts are interdependent (cost estimation needs
    team composition, sprints need module breakdown, etc.) so generating them
    together keeps them consistent.

    planning_types:     Optional subset to (re)generate instead of all 8.
    retry_failed_only:   If True, ignores planning_types and instead
                         regenerates only the artifact types that failed on
                         the last run (read from Project.generation_errors).
    """
    planning_types: list[PlanningType] | None = None
    retry_failed_only: bool = False


class PlanningArtifactOut(BaseModel):
    """
    Response schema for individual planning artifact endpoints.

    DUAL FORMAT (same pattern as DocumentVersionOut):
      content          → structured dict (the queryable, programmatic form)
      summary_markdown → rendered markdown for display in the Planning tab

    Examples of content per type:
      roadmap:   {"phases": [{"phase_number": 1, "name": "Foundation", "duration_weeks": 4}]}
      sprints:   {"total_sprints": 12, "sprints": [{"sprint_number": 1, "goal": "..."}]}
      cost:      {"total_estimate": 95000, "labor_costs": [...], "contingency_amount": 15833}
      team:      {"total_headcount": 6, "recommended_team": [...]}
    """
    id: uuid.UUID
    project_id: uuid.UUID
    planning_type: PlanningType      # module_breakdown | roadmap | sprints | ...
    title: str                       # Human-readable name, e.g., "Cost Estimation"
    content: dict                    # Full structured AI output as JSON
    summary_markdown: str | None     # Rendered markdown for the Planning page
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}