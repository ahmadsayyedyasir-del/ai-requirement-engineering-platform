"""
models/__init__.py — ORM models + shared TimestampMixin.

TimestampMixin is defined here (not in a separate file) because it's tiny,
always imported alongside the models, and has no value as a standalone file.
"""

from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds server-managed created_at / updated_at to any model."""

    # server_default=func.now(): the DB generates this on INSERT (not Python),
    # ensuring consistent timestamps across multiple app instances.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # onupdate=func.now(): DB auto-refreshes this on every UPDATE row.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# Import all models so SQLAlchemy's metadata registry is fully populated
# before create_all or Alembic migrations run.
from app.models.user import User                           # noqa: F401
from app.models.project import Project                     # noqa: F401
from app.models.requirement_input import RequirementInput  # noqa: F401
from app.models.requirement import Requirement             # noqa: F401
from app.models.document import Document, DocumentVersion  # noqa: F401
from app.models.planning import PlanningArtifact           # noqa: F401
from app.models.diagram import Diagram                     # noqa: F401
from app.models.review import ReviewReport                 # noqa: F401

__all__ = [
    "TimestampMixin",
    "User", "Project", "RequirementInput", "Requirement",
    "Document", "DocumentVersion", "PlanningArtifact", "Diagram", "ReviewReport",
]
