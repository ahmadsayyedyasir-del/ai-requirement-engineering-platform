"""
services/generation_tracker.py — Shared status + failure tracking for
"Generate Everything" (documents + planning + diagrams).

WHY THIS FILE EXISTS:
  Before this file existed, three problems made the generation step feel
  broken even when the code was "working":

    1. project.status was NEVER set to "generating" during document/planning/
       diagram generation. The frontend only polls for live updates while
       status is "analyzing" or "generating" — so the status pill and any
       progress feedback silently did nothing for the 1-5 minutes that
       generation actually took. It looked frozen/finished when it wasn't.

    2. If one document/diagram/planning item failed (rate limit, bad JSON,
       transient network error), it was only written to the server log.
       Nothing in the database recorded it, so the user had no way to know
       which items failed or that anything failed at all — they'd just
       notice, later, that some tab was missing content.

    3. There was no way to retry ONLY the failed items — the only option
       was to regenerate everything from scratch.

  This module fixes all three: it flips project.status to "generating" when
  a batch starts and to "completed"/"analyzed" when the last of the three
  batches (documents/planning/diagrams) finishes, and it records a per-item
  success/failure map on Project.generation_errors that the API can expose
  and the frontend can render.

USAGE (from document_generator.py / planning_generator.py / diagram_generator.py):

    from app.services.generation_tracker import (
        mark_batch_started, mark_batch_finished, record_item_result,
    )

    async def generate_document(project_id, doc_types=None):
        await mark_batch_started(project_id, "documents")
        ...
        for doc_type in types_to_generate:
            try:
                await generator(project_id)
                await record_item_result(project_id, "documents", doc_type.value, ok=True)
            except Exception as e:
                await record_item_result(project_id, "documents", doc_type.value, ok=False, error=str(e))
        await mark_batch_finished(project_id, "documents")
"""

import logging
import uuid

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.project import Project, ProjectStatus

logger = logging.getLogger("reqeng.generation_tracker")

# The three generation batches that make up "Generate Everything".
# Used to decide when ALL of them are done so status can move to "completed".
_ALL_SECTIONS = ("documents", "planning", "diagrams")


async def mark_batch_started(project_id: uuid.UUID, section: str) -> None:
    """
    Flip project.status to "generating" and clear any stale error entries
    for this section (a fresh run deserves a fresh slate for THIS section
    only — we don't touch the other two sections' results).
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return

        if project.status != ProjectStatus.generating:
            project.status = ProjectStatus.generating

        errors = dict(project.generation_errors or {})
        errors[section] = {}  # reset this section's results for the new run
        project.generation_errors = errors

        await db.commit()


async def record_item_result(
    project_id: uuid.UUID,
    section: str,
    item_name: str,
    ok: bool,
    error: str | None = None,
) -> None:
    """
    Record the outcome of ONE generated item (one document type, one planning
    type, or one diagram type) into Project.generation_errors.

    Successful items are recorded as "ok" (not just omitted) so the UI can
    show a complete picklist of what ran, not just what failed.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return

        errors = dict(project.generation_errors or {})
        section_map = dict(errors.get(section, {}))
        section_map[item_name] = "ok" if ok else f"failed: {error}"
        errors[section] = section_map
        project.generation_errors = errors

        await db.commit()

    if not ok:
        logger.error(f"[{section}] {item_name} failed for project {project_id}: {error}")


async def mark_batch_finished(project_id: uuid.UUID, section: str) -> None:
    """
    Called when one of the three batches (documents/planning/diagrams) finishes
    — whether or not every item in it succeeded.

    Moves project.status to "completed" only once ALL THREE sections have run
    at least once (so triggering just "Generate Documents" alone doesn't
    prematurely mark the whole project as completed). Otherwise reverts to
    "analyzed" so the UI's polling stops and the status pill reflects reality.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return

        errors = project.generation_errors or {}
        all_sections_ran = all(sec in errors for sec in _ALL_SECTIONS)

        project.status = ProjectStatus.completed if all_sections_ran else ProjectStatus.analyzed
        await db.commit()

    logger.info(f"Finished '{section}' batch for project {project_id}")


def has_failures(generation_errors: dict, section: str | None = None) -> bool:
    """
    Convenience check: did anything fail? If `section` is given, checks only
    that section (e.g. just "documents"); otherwise checks all sections.
    Used by the API layer to decide whether to surface a "Retry Failed" action.
    """
    sections = [section] if section else _ALL_SECTIONS
    for sec in sections:
        for status in (generation_errors or {}).get(sec, {}).values():
            if status != "ok":
                return True
    return False


def failed_items(generation_errors: dict, section: str) -> list[str]:
    """Return the list of item names that failed within one section."""
    return [
        name for name, status in (generation_errors or {}).get(section, {}).items()
        if status != "ok"
    ]