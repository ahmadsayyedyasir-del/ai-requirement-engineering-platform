"""
project.py — The Project database model (maps to the `projects` table).

WHY THIS FILE EXISTS:
  A "project" is the top-level container for everything the platform produces.
  All requirement inputs, extracted requirements, generated documents, diagrams,
  planning artifacts, and review reports belong to a project.

  Think of a project as a folder: "Online Food Delivery App" is a project,
  and inside it lives the SRS, the sprint plan, the ER diagram, etc.

TABLE STRUCTURE:
  id              UUID        Primary key
  owner_id        UUID        Foreign key → users.id (who created this project)
  name            VARCHAR     Human-readable project name
  description     TEXT        Optional longer description
  domain          VARCHAR     Industry domain (fintech, healthcare, ecommerce...)
  status          ENUM        Current lifecycle stage (draft → analyzing → completed)
  created_at      TIMESTAMP   From TimestampMixin
  updated_at      TIMESTAMP   From TimestampMixin

STATUS LIFECYCLE:
  draft      → User created the project but hasn't submitted input yet
  analyzing  → AI pipeline is currently running (may take 30–60 seconds)
  analyzed   → Requirements extracted successfully, ready to generate docs
  generating → Document/diagram generation in progress
  completed  → All artifacts generated
  archived   → Project is no longer active (hidden from main list)
"""

import uuid
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.core.database import Base
from app.models.base_mixin import TimestampMixin


class ProjectStatus(str, enum.Enum):
    """
    Tracks where a project is in the AI pipeline lifecycle.

    Each status corresponds to a step the user has completed:
      draft      — just created, no input yet
      analyzing  — AI is currently extracting requirements (async background job)
      analyzed   — requirements are in the DB, ready for doc generation
      generating — document/planning/diagram generation is running
      completed  — everything is done, all tabs have content
      archived   — project is kept for reference but won't appear in active list
    """
    draft = "draft"
    analyzing = "analyzing"
    analyzed = "analyzed"
    generating = "generating"
    completed = "completed"
    archived = "archived"


class Project(Base, TimestampMixin):
    """
    ORM model for the `projects` table.

    This is the central entity of the whole system — every other model
    links back to a project via a foreign key.
    """

    __tablename__ = "projects"

    # Primary key — unique identifier for each project
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign key to users.id — every project has exactly one owner.
    # ondelete="CASCADE" means: if the owner User is deleted, delete all their projects.
    # index=True speeds up queries like "give me all projects owned by user X".
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The display name for the project (e.g., "Online Food Delivery App")
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # A longer description of what the project is about.
    # Text allows much more content than String(255) — no practical length limit.
    # nullable=True means it's optional.
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Industry domain — helps the AI tailor its analysis.
    # Optional context clue: a "fintech" project might need different NFRs than "healthcare".
    domain: Mapped[str] = mapped_column(String(100), nullable=True)

    # Current status in the pipeline lifecycle (see ProjectStatus enum above)
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus), default=ProjectStatus.draft, nullable=False
    )

    # Tracks the outcome of the LAST "Generate Everything" run, per item.
    # Shape: {"documents": {"srs": "ok", "brd": "failed: <error>"}, "planning": {...}, "diagrams": {...}}
    # WHY THIS EXISTS: previously, if a document/planning artifact/diagram failed
    # to generate (e.g. rate limit), it was only written to the server log — the
    # UI and the user had no way to know anything was missing, let alone which
    # item or why. This column makes failures visible so the UI can show exactly
    # what succeeded/failed and offer a "Retry Failed Only" action.
    generation_errors: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # ── RELATIONSHIPS ────────────────────────────────────────────────────────

    # The user who owns this project. Accessed as project.owner.
    # back_populates="projects" connects to User.projects (the other side of the relationship).
    owner: Mapped["User"] = relationship("User", back_populates="projects")  # noqa: F821

    # All raw inputs submitted for this project (text, PDF uploads, transcripts).
    # Accessed as project.inputs. Cascade deletes all inputs if project is deleted.
    inputs: Mapped[list["RequirementInput"]] = relationship(  # noqa: F821
        "RequirementInput", back_populates="project", cascade="all, delete-orphan"
    )

    # All structured requirements extracted by the AI from this project's inputs.
    # Accessed as project.requirements.
    requirements: Mapped[list["Requirement"]] = relationship(  # noqa: F821
        "Requirement", back_populates="project", cascade="all, delete-orphan"
    )

    # All generated documents (SRS, BRD, User Stories, etc.) for this project.
    # Each document also has versions — see the Document model.
    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        "Document", back_populates="project", cascade="all, delete-orphan"
    )

    # All planning artifacts (roadmap, sprint plan, cost estimate, etc.)
    planning_artifacts: Mapped[list["PlanningArtifact"]] = relationship(  # noqa: F821
        "PlanningArtifact", back_populates="project", cascade="all, delete-orphan"
    )

    # All Mermaid.js diagrams generated for this project
    diagrams: Mapped[list["Diagram"]] = relationship(  # noqa: F821
        "Diagram", back_populates="project", cascade="all, delete-orphan"
    )

    # All AI review reports for this project (one per review run, keeps history)
    review_reports: Mapped[list["ReviewReport"]] = relationship(  # noqa: F821
        "ReviewReport", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project {self.name} [{self.status}]>"