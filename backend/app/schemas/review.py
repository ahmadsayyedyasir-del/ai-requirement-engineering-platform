"""
schemas/review.py — Pydantic schemas for the AI Review Engine results.

TWO SCHEMAS HERE:
  ReviewIssue    → shape of one issue in the review (used internally, not returned directly)
  ReviewReportOut → the complete review report returned by the API

NOTE ON ReviewIssue vs raw dict:
  The `issues` field in ReviewReportOut is `list[dict]` rather than
  `list[ReviewIssue]` because the issues come back from the DB as raw JSON.
  Pydantic would need to re-validate each dict into a ReviewIssue — adding
  complexity without benefit for the frontend. The ReviewIssue class documents
  the expected structure and can be used for internal validation if needed.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel


class ReviewIssue(BaseModel):
    """
    Describes the structure of ONE issue found by the AI reviewer.

    This is not a DB model — it documents what each item in
    ReviewReportOut.issues should look like.

    issue_type  — CATEGORY of the problem:
      missing      → a requirement that obviously should exist but doesn't
      conflict     → two requirements that contradict each other
      duplicate    → two requirements saying the same thing with different wording
      scope_gap    → a business area mentioned in input but not covered by any requirement
      risk         → a technical or business risk not captured as a requirement
      ambiguity    → a requirement too vague to implement reliably

    severity    — HOW SERIOUS:
      high   → fix this before starting development
      medium → fix before sprint planning
      low    → nice to fix but not blocking

    affected_requirement_ids — WHICH requirements are involved.
      Empty list if the issue is about something MISSING (no requirement to point to).
    """
    issue_type: str                              # missing | conflict | duplicate | scope_gap | risk | ambiguity
    severity: str                                # high | medium | low
    description: str                             # Plain English explanation of the problem
    suggestion: str                              # Specific action to fix it
    affected_requirement_ids: list[str] = []     # e.g., ["FR-001", "FR-003"]


class ReviewReportOut(BaseModel):
    """
    Full review report returned by GET /review/latest and GET /review/{id}.

    Contains everything needed for the Review page:
      - quality_score: the 0–100 dial chart
      - summary: the 2–3 sentence overview
      - issues: the full list of problems with severity colors
      - report_markdown: the full formatted report in a collapsible section

    `issues` is list[dict] because the data comes from a JSON column in PostgreSQL.
    Each dict in the list follows the structure described in ReviewIssue above.
    """
    id: uuid.UUID
    project_id: uuid.UUID
    version: int                    # 1, 2, 3... — every review run increments this
    issues: list[dict]              # List of issue objects (see ReviewIssue for structure)
    quality_score: int | None       # 0–100 (None if report is still generating)
    summary: str | None             # 2–3 sentence plain-English assessment
    report_markdown: str | None     # Full formatted markdown report for display
    created_at: datetime            # When this review was run

    model_config = {"from_attributes": True}
