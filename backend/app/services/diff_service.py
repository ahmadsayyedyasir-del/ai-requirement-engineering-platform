"""
services/diff_service.py — Bonus Feature 2: Document Version Diff & Requirement Comparator.

TWO FUNCTIONS IN THIS FILE:

1. get_document_diff() — Line-level diff between two document versions
   Answers: "What changed between SRS version 1 and SRS version 2?"
   Uses Python's built-in `difflib.unified_diff` — same format as `git diff`.
   Returns: added lines, removed lines, full unified diff string.

2. compare_requirement_sets() — Structural diff between two requirement snapshots
   Answers: "What requirements were added/removed/changed after re-analysis?"
   Returns: added_requirements, removed_requirements, modified_requirements.

WHEN TO USE EACH:
  get_document_diff:       After regenerating a document — see text-level changes
  compare_requirement_sets: After re-running analysis — see structural scope changes

HOW UNIFIED DIFF WORKS:
  A unified diff shows context lines (+/-) around changes:
    --- v1 (old version)
    +++ v2 (new version)
    @@ -5,7 +5,9 @@    ← "starting at line 5, showing 7/9 lines"
     unchanged line
    -removed line        ← starts with "-"
    +added line          ← starts with "+"
     unchanged line

  This is the same format git uses, and react-diff-viewer-continued in the
  frontend renders it as a side-by-side or inline colored diff view.
"""

import difflib    # Python standard library — unified diff generation
import json       # For JSON serialization when markdown isn't available
import logging
import uuid
from typing import Optional

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.document import Document, DocumentVersion, DocumentType

logger = logging.getLogger("reqeng.diff")


async def get_document_diff(
    project_id: uuid.UUID,
    doc_type: DocumentType,
    version_a: int,
    version_b: int,
) -> dict:
    """
    Compare two versions of a generated document and return a structured diff.

    EXAMPLE USAGE:
      # Compare SRS version 1 vs version 2
      diff = await get_document_diff(project_id, DocumentType.srs, 1, 2)
      # diff["added_lines"] = ["+## New Section\n+New requirement..."]
      # diff["unified_diff"] = "--- v1\n+++ v2\n@@ ... @@\n..."

    WHY USE content_markdown FOR DIFF (not content_json)?
      Markdown is line-oriented text — each line has meaning (a heading,
      a bullet point, a paragraph). Line-level diffs of Markdown are
      human-readable: "+## New Section" clearly means a new section was added.

      JSON diffs are harder to read: the same change produces many lines of
      "}" / "{" / "," changes that obscure what actually changed.

      If markdown isn't available, we fall back to JSON — at least it works.

    Args:
        project_id:  UUID of the project
        doc_type:    Which document type (srs, brd, user_stories, etc.)
        version_a:   Earlier version number (e.g., 1)
        version_b:   Later version number (e.g., 2)

    Returns:
        dict with: doc_type, version_a, version_b, added_lines, removed_lines,
                   unchanged_line_count, unified_diff, summary, has_changes

    Raises:
        ValueError: If the document or a version doesn't exist.
    """
    async with AsyncSessionLocal() as db:
        # Step 1: Find the document header row
        result = await db.execute(
            select(Document).where(
                Document.project_id == project_id,
                Document.doc_type == doc_type,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document '{doc_type}' not found for this project")

        # Step 2: Fetch both specific version rows simultaneously
        ver_a_result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.version_number == version_a,
            )
        )
        ver_b_result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.version_number == version_b,
            )
        )

        ver_a = ver_a_result.scalar_one_or_none()
        ver_b = ver_b_result.scalar_one_or_none()

        # Raise informative errors for missing versions
        if not ver_a:
            raise ValueError(f"Version {version_a} not found for {doc_type}")
        if not ver_b:
            raise ValueError(f"Version {version_b} not found for {doc_type}")

    # Step 3: Get text content for diffing.
    # Prefer markdown (human-readable), fall back to JSON (machine-readable but still valid)
    text_a = ver_a.content_markdown or json.dumps(ver_a.content_json, indent=2)
    text_b = ver_b.content_markdown or json.dumps(ver_b.content_json, indent=2)

    # Step 4: Split into lines (keepends=True preserves newline characters in each line)
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)

    # Step 5: Generate unified diff using Python's built-in difflib
    # fromfile/tofile = the labels shown in the diff header ("--- v1", "+++ v2")
    # lineterm="" prevents difflib from adding extra newlines
    unified = list(difflib.unified_diff(
        lines_a,
        lines_b,
        fromfile=f"v{version_a}",
        tofile=f"v{version_b}",
        lineterm="",
    ))

    # Step 6: Parse the unified diff into structured lists
    # Lines starting with "+" are additions (but "+++ v2" is the header, not a real addition)
    added   = [line.rstrip("\n") for line in unified if line.startswith("+") and not line.startswith("+++")]
    removed = [line.rstrip("\n") for line in unified if line.startswith("-") and not line.startswith("---")]
    # Lines starting with " " (space) are unchanged context lines
    unchanged_count = sum(1 for line in unified if line.startswith(" "))

    return {
        "doc_type":              doc_type.value,
        "version_a":             version_a,
        "version_b":             version_b,
        "unified_diff":          "".join(unified),      # Full diff string for the diff viewer
        "added_lines":           added,                  # Just the "+" lines
        "removed_lines":         removed,                # Just the "-" lines
        "unchanged_line_count":  unchanged_count,        # How many lines stayed the same
        "summary":               f"{len(added)} lines added, {len(removed)} lines removed",
        "has_changes":           bool(added or removed), # Quick boolean: did anything change?
    }


async def compare_requirement_sets(
    project_id: uuid.UUID,
    snapshot_a: list[dict],
    snapshot_b: list[dict],
) -> dict:
    """
    Compare two snapshots of a requirement set to identify scope changes.

    WHAT IS A "SNAPSHOT"?
      A snapshot is a list of requirement dicts (req_id, title, description, priority, category).
      The client takes a snapshot before and after a re-analysis run, then sends both here.

    EXAMPLE USE CASE:
      1. GET /requirements/ → save as snapshot_a (40 requirements)
      2. POST /requirements/analyze → re-run analysis (new input added)
      3. GET /requirements/ → save as snapshot_b (now 45 requirements)
      4. POST /requirements/compare with {snapshot_a, snapshot_b}
      5. Response: "5 added, 0 removed, 3 modified"

    HOW IT WORKS:
      - Uses req_id as the stable identifier (FR-001 = same logical requirement)
      - added:    req_ids in snapshot_b but NOT in snapshot_a
      - removed:  req_ids in snapshot_a but NOT in snapshot_b
      - modified: req_ids in BOTH where title, description, or priority changed

    WHY USE req_id NOT UUID?
      When requirements are re-extracted, they get new UUIDs (old rows deleted,
      new rows inserted). But req_id is re-assigned deterministically (FR-001,
      FR-002 always go to the first and second functional requirements).
      So req_id is stable across re-analyses for conceptually the same requirement.

    Args:
        project_id:  UUID of the project (used for logging/context)
        snapshot_a:  List of requirement dicts BEFORE some change
        snapshot_b:  List of requirement dicts AFTER some change

    Returns:
        dict with: added_requirements, removed_requirements, modified_requirements, summary
    """
    # Build sets of req_ids from each snapshot for fast set operations
    ids_a = {r["req_id"] for r in snapshot_a}
    ids_b = {r["req_id"] for r in snapshot_b}

    # Requirements in B but not A = newly added requirements
    added = [r for r in snapshot_b if r["req_id"] not in ids_a]

    # Requirements in A but not B = removed requirements (or merged into others)
    removed = [r for r in snapshot_a if r["req_id"] not in ids_b]

    # Requirements in BOTH — check for field-level changes
    common_ids = ids_a & ids_b  # Set intersection
    modified = []
    for req_id in common_ids:
        # Look up this req_id in both snapshots
        old = next(r for r in snapshot_a if r["req_id"] == req_id)
        new = next(r for r in snapshot_b if r["req_id"] == req_id)

        # Compare key fields — collect changes
        changes = {}
        for field in ["title", "description", "priority"]:
            if old.get(field) != new.get(field):
                changes[field] = {
                    "old": old.get(field),
                    "new": new.get(field),
                }

        # Only include in modified list if something actually changed
        if changes:
            modified.append({"req_id": req_id, "changes": changes})

    return {
        "added_requirements":    added,
        "removed_requirements":  removed,
        "modified_requirements": modified,
        "summary": (
            f"{len(added)} added, {len(removed)} removed, {len(modified)} modified "
            f"out of {len(common_ids)} common requirements"
        ),
    }
