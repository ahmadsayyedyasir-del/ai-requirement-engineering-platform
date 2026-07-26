"""
schemas/input.py — Pydantic schemas for requirement input submission and response.

WHAT ARE THESE FOR?
  Two schemas cover the two input endpoints:
    TextInputCreate  → used by POST /inputs/text (the request body)
    InputOut         → used as the response for ALL input endpoints

  Notice InputOut does NOT include extracted_text (which can be very large)
  or file_path (an internal server detail clients don't need).
  It DOES include is_processed and processing_error so the frontend
  can show the user the processing status of their upload.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.requirement_input import InputType


class TextInputCreate(BaseModel):
    """
    Request body for POST /inputs/text.

    Only two fields — the text content and whether it's a meeting transcript.
    min_length=10 rejects trivially short inputs that the AI can't work with.
    """
    text: str = Field(
        min_length=10,  # Reject "hi" or empty strings — need meaningful content
        description="Business description or meeting transcript text",
    )
    is_transcript: bool = False  # Default: regular description. Set True for meeting notes.


class InputOut(BaseModel):
    """
    Response schema for ALL input-related endpoints (text, upload, list, get).

    Shows the client what we know about their submitted input:
    - For text inputs: raw_text is populated, file fields are None
    - For file uploads: file_name and file_size_bytes are populated, raw_text is None
    - is_processed tells the frontend "can this be used in analysis yet?"
    - processing_error shows what went wrong if parsing failed

    Intentionally OMITS:
    - file_path (internal server path — clients don't need this)
    - extracted_text (can be very large — clients fetch it via analysis results instead)

    from_attributes=True allows building from SQLAlchemy ORM objects directly.
    """
    id: uuid.UUID
    project_id: uuid.UUID
    input_type: InputType          # text | pdf | docx | transcript | voice
    raw_text: str | None           # The text content (for text/transcript inputs)
    file_name: str | None          # Original filename (for file uploads)
    file_size_bytes: int | None    # File size in bytes (display "2.4 MB" in UI)
    is_processed: bool             # True = ready for AI analysis
    processing_error: str | None   # If parsing failed, the error message
    created_at: datetime           # When this input was submitted

    model_config = {"from_attributes": True}
