"""
schemas/document.py — Pydantic schemas for document generation and versioning.

THREE SCHEMAS HERE:
  GenerateDocumentRequest  → request body for triggering generation
  DocumentOut              → document header (type, title, current version number)
  DocumentVersionOut       → a specific version with full content

WHY TWO SEPARATE SCHEMAS (DocumentOut vs DocumentVersionOut)?
  A Document header row and a DocumentVersion row serve different purposes:
  - DocumentOut: lightweight — used for the "list all documents" endpoint.
    Just tells you WHAT documents exist and what version number they're on.
  - DocumentVersionOut: full content — used when you actually READ a document.
    Contains the complete JSON and Markdown of one specific version.
  Separating them avoids loading large text content (thousands of characters)
  every time you just want to list document names.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.document import DocumentType


class GenerateDocumentRequest(BaseModel):
    """
    Optional request body for POST /documents/generate.

    doc_types: The specific types to generate.
    If None (omitted), all 8 document types are generated.
    Pass a subset to regenerate only specific documents.

    Example: {"doc_types": ["srs", "user_stories"]} generates only those two.

    retry_failed_only: If True, ignores doc_types and instead regenerates only
    the document types that failed on the last "Generate Everything" run
    (read from Project.generation_errors). Lets the user recover from a
    partial failure without regenerating everything from scratch.
    """
    doc_types: list[DocumentType] | None = None  # None = generate all 8 types
    retry_failed_only: bool = False


class DocumentOut(BaseModel):
    """
    Lightweight document header — returned when listing documents.

    Does NOT include content (that would be too large for a list response).
    Use DocumentVersionOut (from GET /{doc_type}) to get the actual content.

    current_version tells the UI which version number is the latest,
    useful for building "Version 3" labels and pagination controls.
    """
    id: uuid.UUID
    project_id: uuid.UUID
    doc_type: DocumentType      # srs | brd | user_stories | use_cases | ...
    title: str                  # e.g., "Software Requirements Specification"
    current_version: int        # The latest version number (1, 2, 3...)
    created_at: datetime        # When the document was first generated
    updated_at: datetime        # When it was last regenerated

    model_config = {"from_attributes": True}


class DocumentVersionOut(BaseModel):
    """
    Full content of one specific document version.

    Returned by:
      GET /documents/{doc_type}                   → latest version
      GET /documents/{doc_type}/versions/{number} → specific version

    DUAL FORMAT:
      content_json     → The structured AI output (dict). Good for programmatic use.
      content_markdown → The rendered markdown string. Good for display with react-markdown.

    The frontend uses content_markdown for display. content_json is available
    if someone wants to process the document structure programmatically.
    """
    id: uuid.UUID
    document_id: uuid.UUID           # Links back to the Document header row
    version_number: int              # 1, 2, 3... — used by the diff viewer
    content_json: dict               # Structured AI output (always present)
    content_markdown: str | None     # Rendered markdown for display (may be None if generation failed)
    change_summary: str | None       # Brief note about this version (e.g., "AI-generated version 2")
    created_at: datetime             # When this version was generated

    model_config = {"from_attributes": True}