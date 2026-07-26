"""
bonus.py — Bonus feature endpoints (MoSCoW AI, version diff, scope comparator).

WHY THIS FILE EXISTS:
  This file contains three bonus features that go beyond the core 8 phases:

  1. MoSCoW AI Prioritizer  (POST /projects/{id}/prioritize/moscow)
     Re-evaluates all requirements using AI and assigns MoSCoW priorities
     with a reasoning explanation for each assignment.
     WHEN TO USE: After the initial analysis, or when requirements change,
     to get an AI-driven recommendation on what to build first (MVP scope).

  2. Document Version Diff Viewer  (GET /projects/{id}/documents/{type}/diff)
     Compares two versions of a generated document line-by-line.
     Returns: added lines, removed lines, unified diff string.
     WHEN TO USE: After regenerating a document to see exactly what changed.

  3. Requirement Set Comparator  (POST /projects/{id}/requirements/compare)
     Compares two snapshots of a requirement list to identify scope changes.
     Returns: added requirements, removed requirements, modified requirements.
     WHEN TO USE: To compare "before re-analysis" vs "after re-analysis" sets.

NOTE ON ROUTING:
  These endpoints have their full paths defined here (not just a suffix)
  because they span two different resource types (documents AND requirements).
  In router.py they're mounted with prefix="" so the full path is included here.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Pydantic BaseModel for defining the request body schema inline
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.document import DocumentType
from app.api.v1.endpoints.auth import get_current_user

# The MoSCoW AI prioritizer service — re-evaluates all requirements with GPT-4o
from app.services.moscow_prioritizer import run_moscow_prioritization

# The diff service — computes line-level diffs between document versions
from app.services.diff_service import get_document_diff, compare_requirement_sets

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


# ── BONUS FEATURE 1: MoSCoW AI Prioritizer ────────────────────────────────────

@router.post("/projects/{project_id}/prioritize/moscow")
async def moscow_prioritize(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run AI-driven MoSCoW re-prioritization on all project requirements.

    WHAT THIS DOES:
      1. Fetches all active requirements from the DB
      2. Sends them ALL to GPT-4o with a product manager prompt
      3. GPT-4o evaluates each requirement against MoSCoW criteria:
           must_have   → MVP critical, system fails without this
           should_have → High value but not blocking launch
           could_have  → Nice to have if time/budget allows
           wont_have   → Explicitly deferred to future release
      4. Updates each requirement's priority in the DB
      5. Returns a summary of what changed and the reasoning

    WHY RUN THIS?
      The initial analysis assigns priorities too, but the AI doesn't always
      have full context on what's truly critical for the business vs. nice-to-have.
      This dedicated pass focuses solely on prioritization with more deliberate
      reasoning per requirement.

    This is a SYNCHRONOUS endpoint (not 202) — it runs in-request and returns
    the complete change summary. Typical time: 10–20 seconds for 30 requirements.
    """
    await _get_project_or_404(project_id, current_user, db)

    # Run prioritization and get back the changes summary
    result = await run_moscow_prioritization(project_id)
    return result  # {"message": "...", "changes": [...], "summary": {...}}


# ── BONUS FEATURE 2: Document Version Diff Viewer ────────────────────────────

@router.get("/projects/{project_id}/documents/{doc_type}/diff")
async def document_diff(
    project_id: uuid.UUID,
    doc_type: DocumentType,   # Which document type to compare (e.g., "srs", "brd")
    version_a: int,           # Earlier version number — from query string ?version_a=1
    version_b: int,           # Later version number  — from query string ?version_b=2
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compare two versions of a generated document and return a line-level diff.

    EXAMPLE URL:
      GET /projects/{id}/documents/srs/diff?version_a=1&version_b=2

    WHAT IT RETURNS:
      {
        "doc_type": "srs",
        "version_a": 1,
        "version_b": 2,
        "added_lines": ["+## 3. New Section\n+New requirement FR-012..."],
        "removed_lines": ["-Old requirement description..."],
        "unified_diff": "--- v1\n+++ v2\n@@ ... @@\n...",
        "summary": "12 lines added, 4 lines removed",
        "has_changes": true
      }

    HOW IT WORKS:
      Uses Python's built-in difflib.unified_diff on the markdown content
      of each version. The result is a standard unified diff format (same
      as `git diff` output) that the frontend renders with react-diff-viewer.

    Get version numbers first from GET /documents/{doc_type}/versions.
    """
    await _get_project_or_404(project_id, current_user, db)

    try:
        diff = await get_document_diff(project_id, doc_type, version_a, version_b)
        return diff
    except ValueError as e:
        # get_document_diff raises ValueError if a version doesn't exist
        raise HTTPException(status_code=404, detail=str(e))


# ── BONUS FEATURE 3: Requirement Set Comparator ──────────────────────────────

class RequirementSnapshot(BaseModel):
    """
    A snapshot of one requirement — used for comparing before/after sets.
    Not a DB model — just a Pydantic schema for the request body.
    """
    req_id: str       # e.g., "FR-001"
    title: str
    description: str
    priority: str     # e.g., "must_have"
    category: str     # e.g., "functional"


class CompareRequest(BaseModel):
    """
    The request body for comparing two requirement snapshots.
    snapshot_a = "before" set, snapshot_b = "after" set.
    """
    snapshot_a: list[RequirementSnapshot]  # The "before" requirement list
    snapshot_b: list[RequirementSnapshot]  # The "after" requirement list


@router.post("/projects/{project_id}/requirements/compare")
async def compare_requirements(
    project_id: uuid.UUID,
    payload: CompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compare two requirement set snapshots and identify scope changes.

    TYPICAL USE CASE:
      1. Call GET /requirements/ and save the list as "snapshot_a"
      2. Re-run analysis (POST /requirements/analyze)
      3. Call GET /requirements/ again as "snapshot_b"
      4. POST both to this endpoint to see what changed

    WHAT IT RETURNS:
      {
        "added_requirements":   [...],  // In snapshot_b but not snapshot_a
        "removed_requirements": [...],  // In snapshot_a but not snapshot_b
        "modified_requirements": [      // In both but fields changed
          {"req_id": "FR-003", "changes": {"priority": {"old": "could_have", "new": "must_have"}}}
        ],
        "summary": "3 added, 1 removed, 5 modified out of 20 common requirements"
      }

    WHY IS THIS USEFUL?
      When requirements change between analysis runs, scope creep or scope
      reduction can be hard to spot manually across 30+ requirements.
      This endpoint makes changes explicit and traceable.
    """
    await _get_project_or_404(project_id, current_user, db)

    # Convert Pydantic models to plain dicts for the service function
    result = await compare_requirement_sets(
        project_id,
        [s.model_dump() for s in payload.snapshot_a],
        [s.model_dump() for s in payload.snapshot_b],
    )
    return result
