"""
review.py â€” Stores AI quality review reports for generated requirements and documents.

WHY THIS FILE EXISTS:
  Just because the AI generated requirements doesn't mean they're perfect.
  Phase 7 runs a SECOND AI pass that acts as a quality reviewer â€” looking at
  all the requirements and documents and asking:
    - Are there missing requirements that should obviously be here?
    - Do any requirements contradict each other?
    - Are there duplicate requirements phrased differently?
    - Are there business areas mentioned in the input but not covered by any req?
    - Are there technical risks the analyst should know about?

  The result is a "Review Report" â€” a structured quality assessment with a
  score, a list of specific issues (each with severity and suggestion), and
  an overall summary.

  Keeping reports in the database (rather than just showing them once) means:
    - Users can view the report any time without re-running the review
    - Each re-run creates a NEW version (history is preserved)
    - You can compare quality scores over time ("did our requirements improve?")

TABLE STRUCTURE:
  id               UUID        Primary key
  project_id       UUID        FK â†’ projects.id
  version          INTEGER     Review version number (1, 2, 3, ...)
  issues           JSON        List of issue objects (see structure below)
  quality_score    INTEGER     0â€“100 overall quality score
  summary          TEXT        2â€“3 sentence plain-English assessment
  report_markdown  TEXT        Full formatted report for display in the UI
  created_at       TIMESTAMP
  updated_at       TIMESTAMP

ISSUE STRUCTURE (each item in the `issues` JSON array):
  {
    "issue_type":               "missing|conflict|duplicate|scope_gap|risk|ambiguity",
    "severity":                 "high|medium|low",
    "title":                    "Short issue title",
    "description":              "What the problem is",
    "suggestion":               "How to fix it",
    "affected_requirement_ids": ["FR-001", "FR-003"]  // which reqs are involved
  }
"""

import uuid
from sqlalchemy import String, Text, ForeignKey, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.models import TimestampMixin


class ReviewReport(Base, TimestampMixin):
    """
    ORM model for the `review_reports` table.

    Each row represents one complete AI review run.
    Multiple runs are kept (version 1, 2, 3...) so you can track improvement.
    """

    __tablename__ = "review_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Which project this review belongs to
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Review version number â€” starts at 1, increments on each re-run.
    # Lets users see "I ran the review 3 times and the quality score went from 58 â†’ 72 â†’ 85"
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # A JSON array of issue objects. Each issue has:
    #   issue_type     â€” category of problem (missing, conflict, duplicate, etc.)
    #   severity       â€” how serious the problem is (high, medium, low)
    #   title          â€” short description (10 words max)
    #   description    â€” full explanation of the problem
    #   suggestion     â€” specific, actionable recommendation to fix it
    #   affected_requirement_ids â€” list of req_ids involved (e.g., ["FR-001", "FR-004"])
    #
    # WHY JSON AND NOT A SEPARATE TABLE?
    #   Issues don't have their own lifecycle â€” they exist only as part of a report.
    #   Storing them as JSON in one column is simpler and faster to read/write.
    issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Overall quality score from 0 to 100.
    # Rubric:
    #   90-100: Excellent â€” complete, consistent, unambiguous
    #   75-89:  Good â€” minor issues
    #   60-74:  Fair â€” several gaps or conflicts
    #   0-59:   Poor â€” significant problems, needs rework
    quality_score: Mapped[int] = mapped_column(Integer, nullable=True)

    # A 2â€“3 sentence plain-English summary of the review findings.
    # Shown at the top of the Review page before the detailed issue list.
    summary: Mapped[str] = mapped_column(Text, nullable=True)

    # The full formatted report as Markdown, rendered in the UI.
    # Contains: quality score, summary, issues grouped by severity, recommendations.
    report_markdown: Mapped[str] = mapped_column(Text, nullable=True)

    # Relationship back to the parent project
    project: Mapped["Project"] = relationship("Project", back_populates="review_reports")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<ReviewReport project={self.project_id} "
            f"v{self.version} score={self.quality_score}>"
        )
