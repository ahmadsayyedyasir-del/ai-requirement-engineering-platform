"""
diagrams.py — Mermaid.js diagram generation and retrieval endpoints (Phase 6).

WHY THIS FILE EXISTS:
  Good software documentation always includes visual diagrams. This file
  triggers the AI diagram generator and serves the resulting Mermaid.js
  source code, which the frontend renders live in the browser.

WHY MERMAID.JS (not images)?
  - Stored as text → version-controllable, diff-friendly
  - Rendered in the browser → no server-side image generation needed
  - Portable → paste the code into GitHub, Notion, Confluence — it renders everywhere
  - Editable → users can copy the source and modify it in any Mermaid editor

DIAGRAMS GENERATED:
  use_case      — Actors and what they can do (UML Use Case)
  flowchart     — Step-by-step core process flow
  er_diagram    — Database entities and relationships
  sequence      — Component interaction over time for a key flow
  class_diagram — Domain object model (classes, attributes, methods)
  architecture  — High-level system architecture (frontend, API, DB, etc.)

ENDPOINTS:
  POST  /generate          → Generate all 6 diagrams (returns 202)
  GET   /                  → List all generated diagrams (source code)
  GET   /{diagram_type}    → Get one specific diagram's Mermaid source
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.diagram import Diagram, DiagramType
from app.schemas.diagram import DiagramOut, GenerateDiagramsRequest
from app.api.v1.endpoints.auth import get_current_user
from app.services.diagram_generator import generate_diagrams
from app.services.generation_tracker import failed_items

router = APIRouter()


async def _get_project_or_404(project_id: uuid.UUID, user: User, db: AsyncSession) -> Project:
    """Verify project ownership and return it, or raise 404."""
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.post("/generate", status_code=202)
async def generate_project_diagrams(
    project_id: uuid.UUID,
    payload: GenerateDiagramsRequest,  # Optional: specify diagram types to generate
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate diagrams for the project (returns 202) — all 6 types by default.

    Each diagram requires one LLM call that:
      1. Reads the project's extracted requirements
      2. Writes Mermaid.js source code describing the appropriate diagram
      3. Saves the source code to the `diagrams` table

    With controlled concurrency + retry, total time is now well under a
    minute for all 6 diagrams on a typical project.
    Poll GET /diagrams/ to see diagrams appear as each one completes.

    Prerequisites: requirements should be analyzed first so the AI has
    domain knowledge to generate accurate, project-specific diagrams.

    PARTIAL GENERATION:
      Pass diagram_types=["er_diagram"] to regenerate just one diagram.

    RETRY FAILED ONLY:
      Pass retry_failed_only=true to regenerate just the diagram types that
      failed on the previous run, instead of everything.
    """
    project = await _get_project_or_404(project_id, current_user, db)

    diagram_types = payload.diagram_types
    if payload.retry_failed_only:
        failed = failed_items(project.generation_errors, "diagrams")
        if not failed:
            return {"message": "Nothing to retry — no failed diagrams on record.",
                    "diagram_types": []}
        diagram_types = [DiagramType(name) for name in failed]

    # Queue diagram generation — runs after this 202 response is sent.
    # (Previously this call didn't forward diagram_types at all, so requesting
    # a specific subset silently regenerated ALL 6 diagrams every time.)
    background_tasks.add_task(
        generate_diagrams, project_id=project_id, diagram_types=diagram_types
    )
    return {
        "message": "Diagram generation started",
        "project_id": str(project_id),
        "diagram_types": [d.value for d in diagram_types] if diagram_types else "all",
    }


@router.get("/", response_model=list[DiagramOut])
async def list_diagrams(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all generated diagrams for a project.

    Returns the Mermaid.js source_code for each diagram along with its type
    and title. The frontend passes source_code to mermaid.render() to display
    it as an interactive SVG diagram in the browser.

    Ordered alphabetically by diagram_type for consistent sidebar display.
    """
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(Diagram)
        .where(Diagram.project_id == project_id)
        .order_by(Diagram.diagram_type)
    )
    return result.scalars().all()


@router.get("/{diagram_type}", response_model=DiagramOut)
async def get_diagram(
    project_id: uuid.UUID,
    diagram_type: DiagramType,  # Validated against DiagramType enum by FastAPI
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get one specific diagram by its type.

    Returns the Mermaid.js source_code string. The frontend renders this
    with: mermaid.render('diagram-id', source_code) → SVG output.

    Example: GET /diagrams/er_diagram returns the ER diagram source.
    Returns 404 if that diagram type hasn't been generated yet.
    """
    await _get_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(Diagram).where(
            Diagram.project_id == project_id,
            Diagram.diagram_type == diagram_type,
        )
    )
    diagram = result.scalar_one_or_none()
    if not diagram:
        raise HTTPException(
            status_code=404,
            detail=f"Diagram '{diagram_type}' not generated yet.",
        )
    return diagram