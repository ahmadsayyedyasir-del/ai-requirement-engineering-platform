"""
models/__init__.py — Imports all ORM models into a single namespace.

WHY THIS FILE EXISTS:
  SQLAlchemy needs to "see" all model classes before it can:
    1. Create the database tables (Base.metadata.create_all)
    2. Resolve relationship references like "Project" (a string in quotes)
    3. Run Alembic migrations that detect schema changes

  By importing everything here, any other file can do:
      from app.models import User, Project, Requirement
  instead of importing from specific files:
      from app.models.user import User
      from app.models.project import Project

  It also means Alembic's env.py only needs to import this one file
  to get ALL models registered with SQLAlchemy's metadata.

  The `# noqa: F401` comments suppress "imported but unused" warnings —
  these imports ARE used (by SQLAlchemy's mapper), just not in this file directly.
"""

# Import all models so SQLAlchemy's metadata registry is fully populated
# before any table creation or migration happens.

from app.models.user import User                          # noqa: F401 — users table
from app.models.project import Project                    # noqa: F401 — projects table
from app.models.requirement_input import RequirementInput # noqa: F401 — raw inputs table
from app.models.requirement import Requirement            # noqa: F401 — extracted requirements table
from app.models.document import Document, DocumentVersion # noqa: F401 — docs + version history
from app.models.planning import PlanningArtifact          # noqa: F401 — planning artifacts table
from app.models.diagram import Diagram                    # noqa: F401 — mermaid diagrams table
from app.models.review import ReviewReport                # noqa: F401 — AI review reports table

# Export all models so external code can do `from app.models import User`
__all__ = [
    "User",
    "Project",
    "RequirementInput",
    "Requirement",
    "Document",
    "DocumentVersion",
    "PlanningArtifact",
    "Diagram",
    "ReviewReport",
]
