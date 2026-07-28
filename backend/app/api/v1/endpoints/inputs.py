"""inputs.py — Requirement input endpoints: text submit + file upload (Phase 2)."""

import uuid
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.project import Project
from app.models.requirement_input import RequirementInput, InputType
from app.schemas import InputOut, TextInputCreate
from app.api.v1.endpoints.auth import get_current_user
from app.services.document_parser import extract_text_from_file

router = APIRouter()
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


async def _get_project_or_404(project_id: uuid.UUID, user: User, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.post("/text", response_model=InputOut, status_code=201)
async def submit_text_input(
    project_id: uuid.UUID,
    payload: TextInputCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    req_input = RequirementInput(
        project_id=project_id,
        input_type=InputType.transcript if payload.is_transcript else InputType.text,
        raw_text=payload.text,
        is_processed=True,
    )
    db.add(req_input)
    await db.flush()
    return req_input


@router.post("/upload", response_model=InputOut, status_code=201)
async def upload_document(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload PDF/DOCX/TXT. Text extraction runs as a background task."""
    await _get_project_or_404(project_id, current_user, db)

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Allowed: {ALLOWED_EXTENSIONS}")

    upload_dir = Path(settings.UPLOAD_DIR) / str(project_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest_path = upload_dir / f"{uuid.uuid4()}{ext}"

    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit")

    with open(dest_path, "wb") as f:
        f.write(contents)

    req_input = RequirementInput(
        project_id=project_id,
        input_type=InputType.pdf if ext == ".pdf" else InputType.docx,
        file_name=file.filename,
        file_path=str(dest_path),
        file_size_bytes=len(contents),
        is_processed=False,
    )
    db.add(req_input)
    await db.flush()
    background_tasks.add_task(_process_file_extraction, req_input.id, str(dest_path), ext)
    return req_input


@router.get("/", response_model=list[InputOut])
async def list_inputs(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(RequirementInput)
        .where(RequirementInput.project_id == project_id)
        .order_by(RequirementInput.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{input_id}", response_model=InputOut)
async def get_input(
    project_id: uuid.UUID,
    input_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    return inp


@router.delete("/{input_id}", status_code=204)
async def delete_input(
    project_id: uuid.UUID,
    input_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    await db.delete(inp)


async def _process_file_extraction(input_id: uuid.UUID, file_path: str, ext: str):
    """Background task: extract text from uploaded file and persist to DB."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(RequirementInput).where(RequirementInput.id == input_id))
        req_input = result.scalar_one_or_none()
        if not req_input:
            return
        try:
            req_input.extracted_text = await extract_text_from_file(file_path, ext)
            req_input.is_processed = True
        except Exception as e:
            req_input.processing_error = str(e)
        await db.commit()
