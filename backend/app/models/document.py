"""
document.py — Stores AI-generated documentation artifacts with full version history.

WHY THIS FILE EXISTS:
  After requirements are extracted (Phase 3), the AI generates professional
  documents: SRS, BRD, User Stories, etc. (Phase 4). This module stores those
  documents and keeps a full history of every version ever generated.

  VERSION HISTORY IS IMPORTANT BECAUSE:
    - Documents get regenerated as requirements evolve
    - Stakeholders may want to compare "what changed between v1 and v2"
    - You need to be able to roll back to a previous version
    - The diff viewer bonus feature relies on having multiple versions

TWO-TABLE DESIGN:
  We use TWO tables to implement versioning:

  1. `documents` table — one row per document TYPE per project.
     Example: one row for "project X's SRS" regardless of how many times it's regenerated.
     This row tracks the current version number and document type.

  2. `document_versions` table — one row per version of each document.
     Example: SRS v1, SRS v2, SRS v3 are separate rows linked to the same Document row.
     Each version has its own full content (JSON + Markdown).

  This way: `Document.versions` gives you all historical versions.
            `Document.current_version` tells you the latest version number.

TABLE: documents
  id               UUID        Primary key
  project_id       UUID        FK → projects.id
  doc_type         ENUM        srs | brd | user_stories | ...
  title            VARCHAR     Human-readable title ("Software Requirements Spec")
  current_version  INTEGER     The latest version number
  created_at       TIMESTAMP
  updated_at       TIMESTAMP

TABLE: document_versions
  id               UUID        Primary key
  document_id      UUID        FK → documents.id
  version_number   INTEGER     1, 2, 3, ... (incremented on each regeneration)
  content_json     JSON        Structured content (the canonical, queryable form)
  content_markdown TEXT        Rendered markdown (for display in the UI)
  export_path      VARCHAR     Path to a PDF/DOCX export (optional)
  change_summary   TEXT        Brief note about what changed in this version
  created_at       TIMESTAMP
  updated_at       TIMESTAMP
"""

import uuid
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.core.database import Base
from app.models.base_mixin import TimestampMixin


class DocumentType(str, enum.Enum):
    """
    The types of documents this platform can generate.

    srs                  — Software Requirements Specification: the master technical document
                           that describes the complete system requirements for developers.
    brd                  — Business Requirements Document: business-focused, describes
                           the business problem, stakeholders, and success criteria.
    user_stories         — Agile user stories: "As a [role], I want [goal], so that [benefit]"
                           with story points and acceptance criteria.
    use_cases            — Detailed use cases: actors, preconditions, step-by-step flows,
                           alternative paths, and postconditions.
    acceptance_criteria  — Gherkin-format scenarios (Given/When/Then) for each requirement.
    glossary             — Definitions of domain-specific terms so everyone speaks the same language.
    functional_spec      — Detailed feature-by-feature spec: inputs, outputs, business logic.
    non_functional_spec  — Quality attribute requirements: performance targets, security
                           requirements, availability SLAs, etc.
    """
    srs = "srs"
    brd = "brd"
    user_stories = "user_stories"
    use_cases = "use_cases"
    acceptance_criteria = "acceptance_criteria"
    glossary = "glossary"
    functional_spec = "functional_spec"
    non_functional_spec = "non_functional_spec"


class Document(Base, TimestampMixin):
    """
    The "header" row for a document — one per document type per project.

    This row doesn't contain the actual content. Content lives in DocumentVersion rows.
    Think of this as the "binder label" and DocumentVersion rows as the pages inside.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Which project this document belongs to
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # What type of document this is (srs, brd, user_stories, etc.)
    # index=True because we often query "give me the SRS for project X"
    doc_type: Mapped[DocumentType] = mapped_column(
        SAEnum(DocumentType), nullable=False, index=True
    )

    # Human-readable title stored for display purposes
    # Example: "Software Requirements Specification"
    title: Mapped[str] = mapped_column(String(512), nullable=False)

    # The version number of the MOST RECENT version.
    # Starts at 1, incremented every time the document is regenerated.
    # When the UI wants the latest content, it fetches the DocumentVersion
    # with version_number == current_version.
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationship to the parent project
    project: Mapped["Project"] = relationship("Project", back_populates="documents")  # noqa: F821

    # All version rows for this document.
    # order_by="DocumentVersion.version_number.desc()" means the first element
    # in document.versions is always the LATEST version — convenient for display.
    versions: Mapped[list["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number.desc()",
    )

    def __repr__(self) -> str:
        return f"<Document [{self.doc_type}] v{self.current_version}>"


class DocumentVersion(Base, TimestampMixin):
    """
    One specific version of a generated document.

    Every time a document is regenerated (the user clicks "Regenerate"),
    a new DocumentVersion row is created. The old version is kept.

    This enables:
      - Version history: "show me all versions of this SRS"
      - Diff viewing: "what changed between v1 and v2?"
      - Rollback: "go back to the v1 SRS"
    """

    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Which Document (header row) this version belongs to
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Sequential version number: 1, 2, 3, ...
    # Combined with document_id, uniquely identifies any version of any document.
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # The STRUCTURED content as a JSON dict — this is the canonical form.
    # WHY JSON: The AI produces structured data (lists of requirements, sections, etc.).
    # Storing as JSON lets us query individual parts programmatically.
    # Example: {"sections": {"introduction": {...}, "functional_requirements": [...]}}
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # The RENDERED content as Markdown text — this is what the UI displays.
    # WHY MARKDOWN: The frontend renders this with react-markdown into formatted HTML.
    # It's also human-readable if someone accesses the API directly.
    content_markdown: Mapped[str] = mapped_column(Text, nullable=True)

    # Optional path to an exported PDF or DOCX file on disk.
    # Populated if the user triggers an export (bonus feature territory).
    export_path: Mapped[str] = mapped_column(String(1024), nullable=True)

    # A brief note describing what changed in this version.
    # Auto-populated as "AI-generated version N" but could be user-edited.
    change_summary: Mapped[str] = mapped_column(Text, nullable=True)

    # Relationship back to the Document header row
    document: Mapped["Document"] = relationship("Document", back_populates="versions")

    def __repr__(self) -> str:
        return f"<DocumentVersion doc={self.document_id} v{self.version_number}>"
