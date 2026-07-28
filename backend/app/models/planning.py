"""
planning.py â€” Stores AI-generated software planning artifacts.

WHY THIS FILE EXISTS:
  After requirements are extracted, a software project still needs a plan:
  how long will it take? how much will it cost? who do we hire? what do we build first?
  The AI generates eight different planning artifacts to answer these questions.

  Each artifact is stored as a separate row in this table with its own type,
  structured JSON content, and a human-readable markdown summary.

DESIGN DECISION â€” ONE TABLE, MANY TYPES:
  Instead of 8 separate tables (one for roadmap, one for sprints, etc.),
  we use a single `planning_artifacts` table with a `planning_type` column.
  This is simpler and the artifacts have the same structure regardless of type:
  they all have content_json and summary_markdown.

TABLE STRUCTURE:
  id               UUID        Primary key
  project_id       UUID        FK â†’ projects.id
  planning_type    ENUM        module_breakdown | roadmap | sprints | ...
  title            VARCHAR     Human-readable artifact name
  content          JSON        Full structured AI output (the queryable form)
  summary_markdown TEXT        Rendered markdown for UI display
  created_at       TIMESTAMP
  updated_at       TIMESTAMP
"""

import uuid
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.core.database import Base
from app.models import TimestampMixin


class PlanningType(str, enum.Enum):
  
    module_breakdown = "module_breakdown"
    roadmap = "roadmap"
    sprints = "sprints"
    team_composition = "team_composition"
    tech_stack = "tech_stack"
    timeline = "timeline"
    cost_estimation = "cost_estimation"
    risk_assessment = "risk_assessment"


class PlanningArtifact(Base, TimestampMixin):
    """
    ORM model for the `planning_artifacts` table.

    Each row is one planning artifact for one project.
    There should be at most one row per planning_type per project
    (the generator upserts â€” updates if exists, inserts if not).
    """

    __tablename__ = "planning_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Which project this planning artifact belongs to
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # What type of planning artifact this is
    # index=True for fast queries like "give me the roadmap for project X"
    planning_type: Mapped[PlanningType] = mapped_column(
        SAEnum(PlanningType), nullable=False, index=True
    )

    # Auto-generated display title from the planning type
    # Example: PlanningType.cost_estimation â†’ "Cost Estimation"
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # The full structured AI output stored as JSON.
    # WHY JSON: Each planning type has a different structure, and JSON
    # accommodates all of them in one column without needing schema changes.
    # Example for sprints: {"total_sprints": 12, "sprints": [...]}
    # Example for cost: {"labor_costs": [...], "total_estimate": 45000}
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Rendered markdown version of the content for display in the UI.
    # The planning_generator.py service builds this alongside the JSON.
    # Example: "# Development Roadmap\n## Phase 1 â€” Foundation (4 weeks)\n..."
    summary_markdown: Mapped[str] = mapped_column(Text, nullable=True)

    # Relationship back to the parent project
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="planning_artifacts"
    )

    def __repr__(self) -> str:
        return f"<PlanningArtifact [{self.planning_type}] project={self.project_id}>"
