"""
inputs.py — Requirement input endpoints (Phase 2).

WHY THIS FILE EXISTS:
  Before the AI can extract requirements, it needs something to work with.
  This file handles accepting raw business input in two forms:
    1. Text / transcript — the user types or pastes text directly into the UI
    2. File upload       — the user uploads a PDF or DOCX document

  After a file is uploaded, text extraction runs as a BACKGROUND TASK so
  the API response is immediate — the user does NOT wait for PDF parsing.
  The `is_processed` flag on the DB record tells the UI when extraction is done.

ENDPOINTS IN THIS FILE:
  POST   /projects/{id}/inputs/text      → Submit plain text or meeting transcript
  POST   /projects/{id}/inputs/upload    → Upload a PDF, DOCX, or TXT file
  GET    /projects/{id}/inputs/          → List all inputs for a project
  GET    /projects/{id}/inputs/{id}      → Get one specific input (check processing status)
  DELETE /projects/{id}/inputs/{id}      → Delete an input submission

BACKGROUND TASK PATTERN (why it matters):
  Parsing a 50-page PDF can take 3–10 seconds.
  If we parsed it synchronously (inside the request handler), the API would
  hang for 10 seconds before responding — a bad user experience.

  Instead:
    Step 1 → User uploads PDF
    Step 2 → We save the file to disk and create the DB record (is_processed=False)
    Step 3 → We return 201 IMMEDIATELY
    Step 4 → FastAPI runs _process_file_extraction() AFTER the response is sent
    Step 5 → When done, the DB record is updated (is_processed=True, extracted_text=...)
    Step 6 → The frontend polls GET /inputs/{id} until is_processed is True

  FastAPI's BackgroundTasks is perfect for this pattern.
"""

# uuid — Python's standard library for generating universally unique IDs
import uuid

# os — operating system utilities (not used directly here but imported by convention)
import os

# Path — modern Python way to work with file paths (much better than string concatenation)
from pathlib import Path

# FastAPI building blocks:
#   APIRouter      — groups these endpoints into a mini-app with shared prefix
#   Depends        — declares a dependency FastAPI will resolve automatically
#   HTTPException  — raises structured HTTP error responses (with status code + message)
#   UploadFile     — FastAPI's type for multipart file uploads
#   File           — marker telling FastAPI this parameter comes from a multipart form
#   Form           — marker for regular form fields (not used directly here)
#   BackgroundTasks — FastAPI's mechanism for running code AFTER a response is sent
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks

# Async database session — used for all DB operations in async functions
from sqlalchemy.ext.asyncio import AsyncSession

# select() — builds a SQL SELECT statement as a Python expression
from sqlalchemy import select

# get_db — FastAPI dependency that provides a DB session per request
from app.core.database import get_db

# Application settings (upload directory path, max file size, etc.)
from app.core.config import settings

# ORM models — these map to database tables
from app.models.user import User
from app.models.project import Project
from app.models.requirement_input import RequirementInput, InputType

# Pydantic schemas — define what the request body looks like and what we return
from app.schemas.input import InputOut, TextInputCreate

# get_current_user — a dependency that decodes the JWT and returns the logged-in User
from app.api.v1.endpoints.auth import get_current_user

# The service that actually parses PDFs and DOCX files into plain text
from app.services.document_parser import extract_text_from_file

# Create the router for this group of endpoints.
# It gets mounted in router.py with the prefix /projects/{project_id}/inputs
router = APIRouter()

# File extensions we allow for upload.
# Any other extension (e.g., .exe, .jpg, .csv) is rejected with a 400 error.
# We validate this BEFORE saving the file to disk — fail fast and cheap.
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


# ── SHARED HELPER ──────────────────────────────────────────────────────────────

async def _get_project_or_404(
    project_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Project:
    """
    Fetch a project, verifying it belongs to the current user.
    If it doesn't exist OR belongs to someone else, raise HTTP 404.

    WHY 404 AND NOT 403 FOR "WRONG OWNER"?
      If we returned 403 (Forbidden) for "not your project", an attacker could
      enumerate valid project UUIDs by watching for 403 vs 404 responses.
      Returning 404 in both cases prevents this information leak.

    This helper is used by every endpoint in this file to enforce ownership.
    """
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.id,  # <-- Ownership enforcement
        )
    )
    p = result.scalar_one_or_none()  # Returns None if no row matched
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


# ── SUBMIT TEXT INPUT ──────────────────────────────────────────────────────────

@router.post("/text", response_model=InputOut, status_code=201)
async def submit_text_input(
    project_id: uuid.UUID,             # Extracted from the URL path by FastAPI
    payload: TextInputCreate,          # JSON request body: {text: "...", is_transcript: bool}
    background_tasks: BackgroundTasks, # Injected automatically by FastAPI
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit a plain-text business description or meeting transcript.

    WHY NO BACKGROUND TASK HERE?
      Text is already text — no parsing needed. We can store it immediately
      and set is_processed=True right away without any async work.

    WHY DISTINGUISH text FROM transcript?
      Both are plain text, but:
      - text      → a structured business description written by an analyst
      - transcript → raw meeting dialogue (more informal, lots of non-requirement chatter)
      The AI pipeline may apply different extraction strategies depending on the type.
      The is_transcript flag preserves this distinction for downstream processing.
    """
    # Verify project belongs to this user before creating the input
    await _get_project_or_404(project_id, current_user, db)

    # Decide the input type based on whether the user flagged it as a transcript
    input_type = InputType.transcript if payload.is_transcript else InputType.text

    # Create the RequirementInput row.
    # Text inputs are immediately processable — no background parsing needed.
    req_input = RequirementInput(
        project_id=project_id,
        input_type=input_type,
        raw_text=payload.text,  # The actual text content — stored directly
        is_processed=True,      # Text is already ready for the AI pipeline
    )
    db.add(req_input)
    await db.flush()   # Execute INSERT so we get the UUID back
    return req_input


# ── UPLOAD DOCUMENT ────────────────────────────────────────────────────────────

@router.post("/upload", response_model=InputOut, status_code=201)
async def upload_document(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),  # UploadFile wraps the multipart file stream
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a PDF, DOCX, or TXT file for requirement analysis.

    STEP-BY-STEP FLOW:
      1. Validate the file extension — reject unsupported types immediately
      2. Read file contents into memory for size check
      3. Reject if file is too large (prevents DOS attacks and parser overloads)
      4. Save the file to disk in a project-specific subdirectory
      5. Create the RequirementInput record with is_processed=False
      6. Queue text extraction as a background task
      7. Return 201 IMMEDIATELY — the user doesn't wait for parsing

    WHY SAVE TO DISK INSTEAD OF MEMORY?
      The parsing libraries (pdfplumber, python-docx) work with file paths,
      not byte streams. Also, disk storage survives app restarts — if the
      background task fails, we can retry without re-uploading.

    WHY GENERATE A NEW FILENAME WITH uuid4()?
      Two different users might upload files with the same name ("brief.pdf").
      A UUID prefix guarantees no collisions in the upload directory.
    """
    # First verify the project belongs to this user
    await _get_project_or_404(project_id, current_user, db)

    # Extract and normalize the file extension (e.g., ".PDF" → ".pdf")
    ext = Path(file.filename).suffix.lower()

    # Reject unsupported file types before doing any more work
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {ALLOWED_EXTENSIONS}",
        )

    # Build the path for this project's upload directory.
    # Each project gets its own subfolder: /tmp/req_uploads/{project_id}/
    # mkdir(parents=True) creates all intermediate directories.
    # exist_ok=True means no error if the directory already exists.
    upload_dir = Path(settings.UPLOAD_DIR) / str(project_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate a UUID-prefixed filename to avoid collisions.
    # Example: /tmp/req_uploads/abc123.../f8e9d7c6...pdf
    dest_path = upload_dir / f"{uuid.uuid4()}{ext}"

    # Read the entire file into memory.
    # We need the bytes both for the size check AND to write to disk.
    contents = await file.read()

    # Enforce the maximum upload size. Multiply MB by 1024*1024 to get bytes.
    # 413 = "Payload Too Large" — the standard HTTP status code for this.
    if len(contents) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    # Write the file to disk.
    # "wb" = write binary mode — PDF and DOCX are binary formats, not text.
    with open(dest_path, "wb") as f:
        f.write(contents)

    # Map the file extension to the input type enum value
    input_type = InputType.pdf if ext == ".pdf" else InputType.docx

    # Create the DB record. Note is_processed=False — the background task handles parsing.
    req_input = RequirementInput(
        project_id=project_id,
        input_type=input_type,
        file_name=file.filename,           # Original name for display ("brief.pdf")
        file_path=str(dest_path),          # Where we saved it for the parser
        file_size_bytes=len(contents),     # File size in bytes (for UI display "2.4 MB")
        is_processed=False,                # Extraction hasn't run yet
    )
    db.add(req_input)
    await db.flush()  # Execute INSERT to get the UUID assigned before passing to background task

    # Queue the text extraction to run AFTER this response is sent.
    # background_tasks.add_task(fn, arg1, arg2) calls fn(arg1, arg2) after the response.
    # This returns the response immediately while parsing happens in the background.
    background_tasks.add_task(
        _process_file_extraction,
        req_input.id,     # ID of the DB record to update when done
        str(dest_path),   # File location for the parser
        ext,              # Extension tells us which parser to use
    )

    # Return the record immediately — is_processed is still False.
    # The frontend can poll GET /inputs/{id} to check when it becomes True.
    return req_input


# ── LIST ALL INPUTS ────────────────────────────────────────────────────────────

@router.get("/", response_model=list[InputOut])
async def list_inputs(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all input submissions for a project, newest first.

    The frontend uses this to show the analyst what they've submitted:
    - The input type (text, PDF, transcript)
    - The filename (for uploads) or a text preview
    - Whether processing is complete (is_processed flag)
    - Any processing errors (processing_error field)

    Results are ordered newest-first so recent submissions appear at the top.
    """
    await _get_project_or_404(project_id, current_user, db)

    result = await db.execute(
        select(RequirementInput)
        .where(RequirementInput.project_id == project_id)  # Only this project's inputs
        .order_by(RequirementInput.created_at.desc())       # Newest first
    )
    return result.scalars().all()


# ── GET SINGLE INPUT ───────────────────────────────────────────────────────────

@router.get("/{input_id}", response_model=InputOut)
async def get_input(
    project_id: uuid.UUID,
    input_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a specific input by its UUID.

    PRIMARY USE: Polling for processing status after a file upload.

    After uploading a PDF, the frontend can call this endpoint periodically
    to check if `is_processed` has become True (extraction complete) or if
    `processing_error` is set (something went wrong during parsing).

    WHY FILTER BY BOTH input_id AND project_id?
      Security: an input_id alone would work for finding the row,
      but filtering on project_id too ensures the input belongs to a project
      the current user owns. Without this, a user could read other users' inputs
      by guessing input UUIDs.
    """
    await _get_project_or_404(project_id, current_user, db)

    result = await db.execute(
        select(RequirementInput).where(
            RequirementInput.id == input_id,
            RequirementInput.project_id == project_id,  # Security: must belong to this project
        )
    )
    inp = result.scalar_one_or_none()

    if not inp:
        raise HTTPException(status_code=404, detail="Input not found")

    return inp


# ── DELETE INPUT ───────────────────────────────────────────────────────────────

@router.delete("/{input_id}", status_code=204)
async def delete_input(
    project_id: uuid.UUID,
    input_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a specific input submission.

    IMPORTANT — what this does NOT do:
      Deleting an input does NOT remove requirements that were already extracted
      from it. Once the AI has analyzed an input and stored requirements in the DB,
      those requirements are independent. You'd need to re-run analysis to remove them.

    What DOES get deleted:
      The RequirementInput row (including file_name, file_path, extracted_text).
      The uploaded file on disk is NOT deleted here (that would need a cleanup job).

    Returns 204 No Content on success (standard for DELETE endpoints).
    """
    await _get_project_or_404(project_id, current_user, db)

    result = await db.execute(
        select(RequirementInput).where(
            RequirementInput.id == input_id,
            RequirementInput.project_id == project_id,
        )
    )
    inp = result.scalar_one_or_none()

    if not inp:
        raise HTTPException(status_code=404, detail="Input not found")

    await db.delete(inp)  # Hard delete — the row is removed from the DB


# ── BACKGROUND TASK: TEXT EXTRACTION ──────────────────────────────────────────

async def _process_file_extraction(
    input_id: uuid.UUID,
    file_path: str,
    ext: str,
):
    """
    Background task: parse a file and save extracted text to the database.

    This function runs AFTER the HTTP response for the upload has already been sent.
    The user sees their upload as "pending" (is_processed=False) until this completes.

    WHY IT CAN'T USE THE REQUEST'S DB SESSION:
      FastAPI's get_db dependency creates a session tied to the HTTP request lifecycle.
      When the request ends (response sent), that session is closed and committed.
      Background tasks run AFTER the request ends, so the session is already gone.
      We must open a NEW session here using AsyncSessionLocal directly.

    STEPS:
      1. Open a fresh database session
      2. Look up the RequirementInput row by its UUID
      3. Call the appropriate parser (pdfplumber for PDF, python-docx for DOCX)
      4. On success: save extracted_text, set is_processed=True
      5. On failure: save the error message to processing_error
      6. Commit and close

    After this runs, the frontend's polling of GET /inputs/{id} will see
    is_processed=True and know it's safe to trigger the AI analysis pipeline.
    """
    # Import here (inside the function) to avoid circular imports.
    # If we imported at the top of the file, we'd get circular import errors
    # because database.py and this file indirectly depend on each other.
    from app.core.database import AsyncSessionLocal

    # Open a brand-new database session — independent of any HTTP request
    async with AsyncSessionLocal() as db:
        # Re-fetch the RequirementInput row we created during the upload
        result = await db.execute(
            select(RequirementInput).where(RequirementInput.id == input_id)
        )
        req_input = result.scalar_one_or_none()

        # If the record was deleted between upload and processing, do nothing
        if not req_input:
            return

        try:
            # Call the document parser service.
            # - For .pdf: uses pdfplumber to extract text page by page
            # - For .docx: uses python-docx to extract paragraph text
            # - For .txt: reads the file directly
            # This is run in a thread pool (asyncio.to_thread) because
            # pdfplumber/python-docx are synchronous libraries.
            extracted = await extract_text_from_file(file_path, ext)

            # Save the extracted text — this is what the AI pipeline will read
            req_input.extracted_text = extracted
            req_input.is_processed = True   # Signal to the frontend: "ready to analyze"

        except Exception as e:
            # Store the error so the user can see what went wrong
            # (e.g., "PDF is password protected", "Corrupted DOCX file")
            req_input.processing_error = str(e)
            # is_processed stays False — the AI pipeline will skip this input

        # Commit the changes (either extracted text or the error message)
        await db.commit()
