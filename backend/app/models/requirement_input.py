"""
requirement_input.py — Stores all RAW business input submitted by the user.

WHY THIS FILE EXISTS:
  Before the AI can extract requirements, it needs source material. That material
  can come in several forms: a typed description, an uploaded PDF, a DOCX file,
  or a pasted meeting transcript. This model stores all of them.

  We keep the raw input separate from the extracted requirements because:
    1. TRACEABILITY: You can always trace a requirement back to its source.
    2. RE-ANALYSIS: If you want to re-run the AI pipeline with different settings,
       you still have the original input — you don't need to re-upload.
    3. AUDIT: Stakeholders can verify what the AI was given to work with.

TABLE STRUCTURE:
  id               UUID        Primary key
  project_id       UUID        Foreign key → projects.id
  input_type       ENUM        text | pdf | docx | transcript | voice
  raw_text         TEXT        For text/transcript inputs — the text itself
  file_name        VARCHAR     Original filename (e.g., "requirements_v2.pdf")
  file_path        VARCHAR     Where the file is stored on disk
  file_size_bytes  BIGINT      File size — used for validation and display
  extracted_text   TEXT        Text parsed OUT of the file by our document parser
  is_processed     BOOLEAN     True once text has been extracted from the file
  processing_error TEXT        Error message if text extraction failed
  created_at       TIMESTAMP   From TimestampMixin
  updated_at       TIMESTAMP   From TimestampMixin

HOW TEXT EXTRACTION WORKS:
  1. User uploads a PDF → file is saved to disk → RequirementInput row is created
  2. A background task (FastAPI BackgroundTasks) runs _extract_text_from_file()
  3. The extracted text is saved to extracted_text column
  4. is_processed is set to True (or processing_error is set if it failed)
  5. The AI pipeline then uses extracted_text as input
"""

import uuid
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.core.database import Base
from app.models.base_mixin import TimestampMixin


class InputType(str, enum.Enum):
    """
    The format of the raw input submitted by the user.

    text       — User typed or pasted a plain text description directly
    pdf        — User uploaded a PDF document (e.g., an existing requirements doc)
    docx       — User uploaded a Microsoft Word document
    transcript — User pasted a meeting transcript (treated like text but flagged differently)
    voice      — (Future) User uploaded a voice recording to be transcribed
    """
    text = "text"
    pdf = "pdf"
    docx = "docx"
    transcript = "transcript"
    voice = "voice"


class RequirementInput(Base, TimestampMixin):
    """
    ORM model for the `requirement_inputs` table.

    One project can have MULTIPLE inputs. For example:
    - First, the analyst pastes the initial business idea (text input)
    - Later, they upload a meeting transcript from a stakeholder call (transcript input)
    - Then they add a competitor analysis PDF (pdf input)
    All of these feed into the AI pipeline together.
    """

    __tablename__ = "requirement_inputs"

    # Unique ID for this specific input submission
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Which project this input belongs to.
    # ondelete="CASCADE" — if the project is deleted, delete all its inputs too.
    # index=True — we often query "all inputs for project X", so an index speeds this up.
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # What kind of input this is (text, PDF, DOCX, transcript)
    input_type: Mapped[InputType] = mapped_column(SAEnum(InputType), nullable=False)

    # For text/transcript inputs: the actual text content submitted by the user.
    # Text column has no length limit — business descriptions can be very long.
    # nullable=True because file uploads don't have raw_text.
    raw_text: Mapped[str] = mapped_column(Text, nullable=True)

    # For file uploads: the original filename the user uploaded (e.g., "brief.pdf").
    # We display this in the UI so the user knows what they uploaded.
    file_name: Mapped[str] = mapped_column(String(512), nullable=True)

    # The full path where we stored the uploaded file on disk.
    # We need this to run the text extraction parser later.
    file_path: Mapped[str] = mapped_column(String(1024), nullable=True)

    # File size in bytes. BigInteger supports very large files (up to ~9 exabytes).
    # Used to check against MAX_UPLOAD_SIZE_MB and display "2.4 MB" in the UI.
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=True)

    # The text extracted from the uploaded file by pdfplumber (PDF) or python-docx (DOCX).
    # This is what the AI pipeline actually reads — not the raw file.
    # NULL until the background extraction task completes.
    extracted_text: Mapped[str] = mapped_column(Text, nullable=True)

    # True once the background text-extraction task has completed successfully.
    # The AI pipeline checks this before including an input in analysis.
    is_processed: Mapped[bool] = mapped_column(default=False, nullable=False)

    # If text extraction fails (e.g., password-protected PDF, corrupted file),
    # the error message is stored here so the user can see what went wrong.
    processing_error: Mapped[str] = mapped_column(Text, nullable=True)

    # Relationship back to the parent Project (access as input.project)
    project: Mapped["Project"] = relationship("Project", back_populates="inputs")  # noqa: F821

    def get_content(self) -> str:
        """
        Returns the best available text content for this input.

        WHY THIS METHOD:
          Depending on input type, the text lives in different columns:
          - For text inputs: raw_text has the content
          - For file uploads: extracted_text has the parsed content
          - Either could be None if something went wrong

          This method provides a safe way to get whatever text is available
          without the caller having to know which column to check.
        """
        # Prefer extracted_text (from file parsing), fall back to raw_text,
        # fall back to empty string if both are None.
        return self.extracted_text or self.raw_text or ""

    def __repr__(self) -> str:
        return f"<RequirementInput [{self.input_type}] project={self.project_id}>"
