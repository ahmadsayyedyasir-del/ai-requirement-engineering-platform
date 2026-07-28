"""
schemas.py — All Pydantic request/response schemas for the API.

Consolidated from 8 separate schema files. Each class is a Pydantic model that
defines the shape of data entering or leaving the API — NOT database tables.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole
from app.models.project import ProjectStatus
from app.models.requirement_input import InputType
from app.models.requirement import RequirementCategory, RequirementPriority
from app.models.document import DocumentType
from app.models.planning import PlanningType
from app.models.diagram import DiagramType, DiagramFormat


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    full_name: str | None = None
    # Only admins can change is_active — enforced in the endpoint
    is_active: bool | None = None


# ── Projects ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    domain: str | None = Field(default=None, max_length=100)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    domain: str | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    domain: str | None
    status: ProjectStatus
    # Per-item outcome of the last "Generate Everything" run.
    # e.g. {"documents": {"srs": "ok", "brd": "failed: ..."}, ...}
    generation_errors: dict = {}
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Inputs ────────────────────────────────────────────────────────────────────

class TextInputCreate(BaseModel):
    text: str = Field(min_length=10)
    is_transcript: bool = False


class InputOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    input_type: InputType
    raw_text: str | None
    file_name: str | None
    file_size_bytes: int | None
    is_processed: bool
    processing_error: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Requirements ──────────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    # If None, use all inputs for the project
    input_ids: list[uuid.UUID] | None = None


class RequirementOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    category: RequirementCategory
    priority: RequirementPriority
    req_id: str
    title: str
    description: str
    # Renamed from "metadata" — SQLAlchemy reserves that attribute name on Base classes
    extra_metadata: dict | None
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class RequirementUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: RequirementPriority | None = None


# ── Documents ─────────────────────────────────────────────────────────────────

class GenerateDocumentRequest(BaseModel):
    doc_types: list[DocumentType] | None = None
    # If True, regenerates only the types that failed on the last run
    retry_failed_only: bool = False


class DocumentOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    doc_type: DocumentType
    title: str
    current_version: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class DocumentVersionOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    content_json: dict
    content_markdown: str | None
    change_summary: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Planning ──────────────────────────────────────────────────────────────────

class GeneratePlanningRequest(BaseModel):
    planning_types: list[PlanningType] | None = None
    retry_failed_only: bool = False


class PlanningArtifactOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    planning_type: PlanningType
    title: str
    content: dict
    summary_markdown: str | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Diagrams ──────────────────────────────────────────────────────────────────

class GenerateDiagramsRequest(BaseModel):
    diagram_types: list[DiagramType] | None = None
    retry_failed_only: bool = False


class DiagramOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    diagram_type: DiagramType
    diagram_format: DiagramFormat
    title: str
    source_code: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Review ────────────────────────────────────────────────────────────────────

class ReviewReportOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    issues: list[dict]
    quality_score: int | None
    summary: str | None
    report_markdown: str | None
    created_at: datetime
    model_config = {"from_attributes": True}
