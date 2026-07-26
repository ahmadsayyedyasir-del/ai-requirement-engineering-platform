"""
services/review_engine.py — Phase 7: AI Second-Pass Quality Reviewer.

WHAT THIS FILE DOES:
  After requirements are extracted and documents generated, this service
  runs a SECOND AI pass that acts as a quality assurance reviewer.

  It reads all requirements, sends them to GPT-4o with a specialized QA
  reviewer prompt, and gets back a structured quality report:
    - quality_score (0–100)
    - A list of specific issues with severity and actionable suggestions
    - Strengths (what was done well)
    - Recommended actions (prioritized fixes)

WHY A SECOND PASS?
  The first AI pass (Phase 3) is optimized for EXTRACTION — getting requirements
  out of business text. It's not designed to critique its own output.

  The second pass is designed for EVALUATION — given the complete set of
  requirements, are they:
    - Complete? (no obvious missing requirements)
    - Consistent? (no contradictions)
    - Unambiguous? (no vague statements)
    - Traceable? (no scope gaps)

  Using a different prompt role ("you are a QA engineer reviewing requirements")
  produces much better quality critiques than asking the same model that wrote
  the requirements to review them.

TEMPERATURE=0.1:
  Very low because we want consistent severity categorization. A "high" severity
  issue should always be classified as high, not sometimes "medium" due to
  randomness in the model output.

VERSIONING:
  Every run creates a NEW ReviewReport row (version increments).
  History is preserved: you can see how quality improved after fixing issues.

ENTRY POINT: run_review()
  Called from review.py endpoint as a background task.
"""

import json
import logging
import uuid

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.review import ReviewReport
from app.models.requirement import Requirement
from app.models.document import Document
from app.services.llm_client import get_llm

logger = logging.getLogger("reqeng.review")


async def run_review(project_id: uuid.UUID) -> None:
    """
    Execute the full AI review pipeline and save a ReviewReport to the DB.

    FLOW:
      1. Load all active requirements from PostgreSQL
      2. Get a quick summary of which documents have been generated
      3. Build a QA reviewer prompt with both pieces of context
      4. Send to GPT-4o (temperature=0.1 for consistent severity ratings)
      5. Parse the JSON response
      6. Build the full Markdown report
      7. Save as a new ReviewReport version to the DB
    """
    logger.info(f"Starting AI review for project {project_id}")

    # Load requirements and doc summary
    reqs = await _get_requirements(project_id)
    docs_summary = await _get_docs_summary(project_id)

    llm = get_llm(temperature=0.1)  # Very consistent — QA needs stable severity ratings

    # The QA reviewer prompt. This is separate from the extraction prompt
    # because the role, goal, and output structure are completely different.
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a senior software QA engineer and requirements auditor.
Your job is to review the provided requirements set for quality issues.

Return ONLY a valid JSON object (no fences):
{{
  "quality_score": 75,
  "summary": "2-3 sentences assessing overall quality",
  "issues": [
    {{
      "issue_type": "missing|conflict|duplicate|scope_gap|risk|ambiguity",
      "severity": "high|medium|low",
      "title": "Short issue title (max 10 words)",
      "description": "What the problem is and why it matters",
      "suggestion": "Specific, actionable fix recommendation",
      "affected_requirement_ids": ["FR-001", "FR-003"]
    }}
  ],
  "strengths": ["What is done well"],
  "recommended_actions": [
    {{"priority": "high|medium|low", "action": "..."}}
  ]
}}

QUALITY SCORE RUBRIC:
  90–100: Excellent — complete, consistent, unambiguous, traceable
  75–89:  Good — minor issues, safe to proceed with development
  60–74:  Fair — several gaps or conflicts, needs analyst review
  0–59:   Poor — significant problems, rework required before development

ISSUE TYPES:
  missing    — A requirement that obviously should exist but doesn't
               (e.g., "no authentication requirement", "no error handling requirement")
  conflict   — Two requirements that contradict each other
               (e.g., "FR-001 says users must register, FR-008 says no registration needed")
  duplicate  — Two requirements expressing the same thing with different wording
  scope_gap  — A business area mentioned in context but not covered by any requirement
  risk       — A technical or business risk that should be captured as a requirement
  ambiguity  — A requirement too vague to implement reliably
               (e.g., "the system should be fast" — no measurable target)

Be THOROUGH — identify at least 5 issues.
Be SPECIFIC — point to exact requirement IDs when possible.
Do NOT give generic feedback like "improve documentation" without specifics.
""",
        ),
        (
            "human",
            "Requirements:\n{requirements}\n\nDocuments generated: {docs_summary}",
        ),
    ])

    # Truncate requirements to avoid exceeding token limits
    # 8000 chars ≈ 2000 tokens — leaves room for prompt + response
    response = await (prompt | llm).ainvoke({
        "requirements": json.dumps(reqs, indent=2)[:8000],
        "docs_summary": docs_summary[:2000],
    })

    # Parse the JSON response
    content = _parse(response.content)

    # Extract fields from the parsed response (with safe defaults)
    issues = content.get("issues", [])
    quality_score = content.get("quality_score", 0)
    summary = content.get("summary", "")

    # Build the full formatted Markdown report for display in the UI
    report_markdown = _build_report_markdown(content)

    # Save to the database as a new version
    await _save_report(project_id, issues, quality_score, summary, report_markdown)

    logger.info(
        f"Review complete for project {project_id}: "
        f"score={quality_score}, issues={len(issues)}"
    )


async def _get_requirements(project_id: uuid.UUID) -> list[dict]:
    """
    Load all active requirements as a flat list of dicts.

    WHY FLAT LIST (not grouped by category)?
      The reviewer needs to see ALL requirements together to spot conflicts and
      duplicates across categories. A flat list with category labels is clearer
      for cross-category analysis than a nested grouped dict.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Requirement)
            .where(
                Requirement.project_id == project_id,
                Requirement.is_active == True,
            )
            .order_by(Requirement.category, Requirement.req_id)  # Consistent ordering
        )
        reqs = result.scalars().all()

    return [
        {
            "req_id":     r.req_id,
            "category":   r.category.value,
            "priority":   r.priority.value,
            "title":      r.title,
            "description": r.description,
        }
        for r in reqs
    ]


async def _get_docs_summary(project_id: uuid.UUID) -> str:
    """
    Return a brief summary of which documents have been generated.

    We pass this to the reviewer so it can note if documents are missing
    (e.g., "SRS not generated yet" could be flagged as a scope gap issue).
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document).where(Document.project_id == project_id)
        )
        docs = result.scalars().all()

    if not docs:
        return "No documents generated yet."

    # Simple comma-separated list is enough context for the reviewer
    return "Generated documents: " + ", ".join(d.doc_type.value for d in docs)


async def _save_report(
    project_id: uuid.UUID,
    issues: list,
    quality_score: int,
    summary: str,
    report_markdown: str,
) -> None:
    """
    Save a new ReviewReport to the database.

    Gets the current max version number and increments it.
    This preserves all previous review reports for history comparison.
    """
    async with AsyncSessionLocal() as db:
        # Find the highest existing version number for this project's reviews
        result = await db.execute(
            select(ReviewReport)
            .where(ReviewReport.project_id == project_id)
            .order_by(ReviewReport.version.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        # If no reviews yet: start at 1. Otherwise: increment.
        new_version = (latest.version + 1) if latest else 1

        report = ReviewReport(
            project_id=project_id,
            version=new_version,
            issues=issues,                  # JSON array of issue dicts
            quality_score=quality_score,    # 0–100
            summary=summary,               # 2–3 sentence overview
            report_markdown=report_markdown,  # Full formatted report
        )
        db.add(report)
        await db.commit()


def _build_report_markdown(content: dict) -> str:
    """
    Build a formatted Markdown report from the parsed review JSON.

    Structure:
      # AI Requirements Review Report
      ## Quality Score: 75/100
      ## Summary
      ## Strengths
      ## Issues Found (N)
        ### HIGH Severity (X)
        ### MEDIUM Severity (Y)
        ### LOW Severity (Z)
      ## Recommended Actions

    Issues are grouped by severity (high → medium → low) so the most
    important problems are always at the top.
    """
    lines = [
        "# AI Requirements Review Report\n",
        f"## Quality Score: {content.get('quality_score', 'N/A')}/100\n",
        f"## Summary\n{content.get('summary', '')}\n",
    ]

    # Show strengths (positives) before issues to balance the report
    strengths = content.get("strengths", [])
    if strengths:
        lines.append("## Strengths\n" + "\n".join(f"- {s}" for s in strengths))

    issues = content.get("issues", [])
    if issues:
        lines.append(f"\n## Issues Found ({len(issues)})\n")
        # Group issues by severity: high first (most urgent), then medium, then low
        for severity in ["high", "medium", "low"]:
            sev_issues = [i for i in issues if i.get("severity") == severity]
            if sev_issues:
                lines.append(f"### {severity.upper()} Severity ({len(sev_issues)})")
                for issue in sev_issues:
                    # Each issue gets its type in ALL CAPS as a category label
                    lines.append(
                        f"#### [{issue.get('issue_type','').upper()}] {issue.get('title','')}"
                    )
                    lines.append(f"**Description:** {issue.get('description','')}")
                    lines.append(f"**Suggestion:** {issue.get('suggestion','')}")
                    affected = issue.get("affected_requirement_ids", [])
                    if affected:
                        lines.append(f"**Affected Requirements:** {', '.join(affected)}")
                    lines.append("")  # Blank line between issues

    # Recommended actions at the end — prioritized list of next steps
    actions = content.get("recommended_actions", [])
    if actions:
        lines.append("## Recommended Actions")
        for action in actions:
            priority = action.get("priority", "medium").upper()
            lines.append(f"- **[{priority}]** {action.get('action','')}")

    return "\n\n".join(lines)


def _parse(text: str) -> dict:
    """
    Strip markdown fences and parse JSON from LLM output.
    Falls back to a safe default dict if parsing fails completely.
    """
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("\n")
        end = len(parts)
        for i in range(len(parts) - 1, 0, -1):
            if parts[i].strip() == "```":
                end = i
                break
        text = "\n".join(parts[1:end])
    try:
        return json.loads(text)
    except Exception:
        # If JSON parsing fails, return a minimal valid report
        return {
            "quality_score": 0,
            "summary": f"Review parsing failed. Raw response: {text[:200]}",
            "issues": [],
            "strengths": [],
        }
