"""
requirement.py â€” Stores structured, AI-extracted requirements in the database.

WHY THIS FILE EXISTS:
  This is the most important model in the system. The whole point of the platform
  is to turn vague business text into structured, traceable software requirements.

  A requirement is NOT just a line of text from the AI. It's a structured record with:
    - A unique ID (FR-001, NFR-003, etc.) for traceability
    - A category (functional, non-functional, business rule, etc.)
    - A MoSCoW priority (must_have, should_have, could_have, wont_have)
    - A title (short, 10-word summary)
    - A description (detailed explanation)
    - Metadata (any extra fields the AI extracted, like impact level for risks)
    - Source traceability (which input document it came from)
    - A version number (incremented when a user edits it)

TABLE STRUCTURE:
  id                UUID        Primary key
  project_id        UUID        FK â†’ projects.id
  category          ENUM        functional | non_functional | user_role | ...
  priority          ENUM        must_have | should_have | could_have | wont_have
  req_id            VARCHAR     Human-readable ID: FR-001, NFR-003, BR-007
  title             VARCHAR     Short title (â‰¤10 words)
  description       TEXT        Full description
  extra_metadata    JSON        Extra AI-extracted data (e.g., risk impact, likelihood)
  source_input_id   UUID        FK â†’ requirement_inputs.id (traceability)
  version           INTEGER     How many times this requirement has been edited
  is_active         BOOLEAN     False = soft-deleted (filtered out of normal queries)
  created_at        TIMESTAMP
  updated_at        TIMESTAMP

WHY SOFT DELETE (is_active)?
  When a user deletes a requirement, we don't remove the row. Instead we set
  is_active=False. This preserves audit history: you can still see what was
  extracted even if the analyst decided it wasn't relevant.
"""

import uuid
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.core.database import Base
from app.models import TimestampMixin

 
class RequirementCategory(str, enum.Enum):
    """
    The eight categories of requirements the AI extracts.

    functional       â€” What the system must DO (features, capabilities)
                       Example: "Users shall be able to reset their password"
    non_functional   â€” How the system must PERFORM (quality attributes)
                       Example: "The login page shall load in under 2 seconds"
    user_role        â€” The types of people who use the system
                       Example: "Customer", "Restaurant Owner", "Delivery Rider"
    business_rule    â€” Policies and constraints from the business domain
                       Example: "Delivery fee is calculated as $2 + $0.50 per km"
    constraint       â€” Hard technical or regulatory limits
                       Example: "Must be GDPR compliant for EU users"
    assumption       â€” Things we're assuming to be true (should be validated)
                       Example: "Assumed that payment gateway integration is available"
    risk             â€” Potential problems that could derail the project
                       Example: "Third-party mapping API may have downtime"
    dependency       â€” External systems or services this project relies on
                       Example: "Depends on Stripe API for payment processing"
    """
    functional = "functional"
    non_functional = "non_functional"
    user_role = "user_role"
    business_rule = "business_rule"
    constraint = "constraint"
    assumption = "assumption"
    risk = "risk"
    dependency = "dependency"


class RequirementPriority(str, enum.Enum):
    """
    MoSCoW prioritisation framework â€” the industry standard for requirement priority.

    WHY MOSCOW?
      MoSCoW helps teams decide what to build FIRST. Without it, everything
      feels equally important and scope creep becomes unmanageable.

    must_have    â€” Without this, the product FAILS. These go in the MVP.
                   Example: "Users must be able to log in"
    should_have  â€” High value but not critical for launch. Include if possible.
                   Example: "Users should receive email confirmations"
    could_have   â€” Nice to have. Cut if time/budget is tight.
                   Example: "Users could see their order history graph"
    wont_have    â€” Explicitly OUT of scope for this version. Not forgotten â€” deferred.
                   Example: "Multi-language support will not be in v1"
    """
    must_have = "must_have"
    should_have = "should_have"
    could_have = "could_have"
    wont_have = "wont_have"


class Requirement(Base, TimestampMixin):
    """
    ORM model for the `requirements` table.

    Each row represents one atomic software requirement extracted by the AI,
    validated, and stored with a unique ID (FR-001, NFR-003, etc.).
    """

    __tablename__ = "requirements"

    # Unique database ID for this requirement row
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Which project this requirement belongs to
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,   # index because we frequently query "all requirements for project X"
    )

    # The category of this requirement (functional, non_functional, risk, etc.)
    # index=True because we often filter by category (e.g., "show only functional reqs")
    category: Mapped[RequirementCategory] = mapped_column(
        SAEnum(RequirementCategory), nullable=False, index=True
    )

    # MoSCoW priority â€” set by the AI during extraction, can be changed manually
    # or re-assigned by the MoSCoW AI prioritizer (bonus feature)
    priority: Mapped[RequirementPriority] = mapped_column(
        SAEnum(RequirementPriority), default=RequirementPriority.must_have, nullable=False
    )

    # Human-readable requirement identifier used in documents and traceability matrices.
    # Format: {PREFIX}-{NUMBER} where PREFIX is:
    #   FR  = Functional Requirement
    #   NFR = Non-Functional Requirement
    #   UR  = User Role
    #   BR  = Business Rule
    #   CON = Constraint
    #   ASM = Assumption
    #   RSK = Risk
    #   DEP = Dependency
    req_id: Mapped[str] = mapped_column(String(20), nullable=False)

    # Short, searchable title â€” max 10 words, max 512 characters
    title: Mapped[str] = mapped_column(String(512), nullable=False)

    # Full description with all the detail needed for a developer to implement it.
    # Text = no length limit.
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Additional AI-extracted data stored as a flexible JSON blob.
    # For risks: {"impact": "high", "likelihood": "medium"}
    # For user roles: {"access_level": "authenticated"}
    # Using JSON instead of separate columns keeps the schema flexible.
    #
    # WHY "extra_metadata" AND NOT "metadata":
    #   SQLAlchemy's Declarative API reserves the attribute name "metadata" on every
    #   model class for its own internal MetaData object (used by create_all, Alembic, etc.).
    #   Naming a column "metadata" raises InvalidRequestError on startup.
    #   "extra_metadata" is the direct replacement â€” same purpose, no conflict.
    extra_metadata: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)

    # Traceability: which raw input document did this requirement come from?
    # SET NULL on delete means if the input is deleted, this requirement stays
    # but loses its source reference (the requirement is still valid).
    source_input_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requirement_inputs.id", ondelete="SET NULL"),
        nullable=True,  # nullable because we don't always track source
    )

    # Version counter â€” incremented each time a user manually edits this requirement.
    # Starts at 1 (set by the AI during initial extraction).
    # Allows us to see "this requirement has been edited 3 times".
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Soft delete flag â€” False means the user has "deleted" this requirement.
    # We keep the row for audit purposes but exclude it from normal queries
    # by always filtering with Requirement.is_active == True.
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationship back to the parent project
    project: Mapped["Project"] = relationship("Project", back_populates="requirements")  # noqa: F821

    def __repr__(self) -> str:
        # Shows like: <Requirement FR-001: Allow users to register an account>
        return f"<Requirement {self.req_id}: {self.title[:50]}>"
