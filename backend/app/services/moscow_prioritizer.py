"""
services/moscow_prioritizer.py — Bonus Feature 1: AI-Driven MoSCoW Prioritization.

WHAT IS MoSCoW?
  MoSCoW is the industry-standard framework for requirement prioritization:
    Must Have    — Critical for launch. Without it, the product FAILS.
    Should Have  — High value but not blocking the release.
    Could Have   — Nice to have if time/budget allows.
    Won't Have   — Explicitly DEFERRED to a future release (not forgotten).

WHY A DEDICATED SERVICE FOR THIS?
  The initial analysis (Phase 3) assigns priorities too, but it's doing
  MANY things at once — extracting text, categorizing requirements, assigning
  priorities. The priority assignment is opportunistic.

  This service is DEDICATED to prioritization. It sends ALL requirements to
  GPT-4o with a product manager prompt that focuses specifically on:
    1. Business value — how critical to core business goals?
    2. Technical dependency — do other requirements depend on this?
    3. User impact — how many users need this on day 1?
    4. Deferral risk — what happens if we wait?

  This produces much more thoughtful, consistent prioritization than the
  initial extraction pass.

WHAT GETS CHANGED:
  Each requirement with a different priority gets updated in the DB.
  The version counter increments for each changed requirement (audit trail).
  Requirements that STAY the same priority are NOT updated (efficiency).

RETURN VALUE:
  A summary dict with the list of changes (req_id, old priority, new priority,
  reasoning) and counts per MoSCoW category. The frontend shows this as a
  "what changed" summary.

ENTRY POINT: run_moscow_prioritization()
  Called synchronously from bonus.py (not a background task — it returns results directly).
"""

import json
import logging
import uuid

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.requirement import Requirement, RequirementPriority
from app.services.llm_client import get_llm

logger = logging.getLogger("reqeng.moscow")


async def run_moscow_prioritization(project_id: uuid.UUID) -> dict:
    """
    Re-evaluate and assign MoSCoW priorities to all project requirements.

    FLOW:
      1. Load all active requirements from the DB
      2. Build a product manager prompt with all requirements
      3. Ask GPT-4o to assign must/should/could/wont priorities with reasoning
      4. Apply the new priorities to the DB (only where they changed)
      5. Return a summary of changes

    WHY SYNCHRONOUS (not background task)?
      The return value (the change summary) is what the user sees immediately.
      Unlike document generation where the output is stored and fetched later,
      here the user wants to see "12 requirements re-prioritized" right away.
      Typical time: 10–20 seconds for 30 requirements.

    Args:
        project_id: UUID of the project to re-prioritize

    Returns:
        dict with keys:
          message  — summary string
          changes  — list of {req_id, title, old_priority, new_priority, reasoning}
          summary  — MoSCoW distribution counts + MVP story points estimate
    """
    logger.info(f"Running MoSCoW prioritization for project {project_id}")

    # Load all active requirements
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Requirement).where(
                Requirement.project_id == project_id,
                Requirement.is_active == True,
            )
        )
        requirements = result.scalars().all()

    # Handle the empty case gracefully
    if not requirements:
        return {"message": "No requirements found", "changes": []}

    # Build the list of requirements to send to the LLM.
    # Include current_priority so the LLM can see what was assigned before
    # and only suggest changes where it genuinely disagrees.
    reqs_list = [
        {
            "id":               str(r.id),      # UUID — needed to update the right DB row
            "req_id":           r.req_id,        # Human-readable ID (FR-001)
            "title":            r.title,
            "description":      r.description,
            "category":         r.category.value,
            "current_priority": r.priority.value,
        }
        for r in requirements
    ]

    llm = get_llm(temperature=0.1)  # Low temp for stable, consistent priority assignments

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are an experienced product manager applying MoSCoW prioritization.

For each requirement, assign a MoSCoW priority based on:
1. Business criticality — failure to include this = product doesn't achieve its goal
2. Technical dependency — other requirements can't work without this
3. User day-1 need — real users need this from the very first release
4. Deferral risk — what bad thing happens if we push this to the next release?

MoSCoW rules:
- must_have:   Without this the product launch FAILS. Be strict — max 60% should be must_have.
- should_have: High value, include in launch if at all possible. ~20% of requirements.
- could_have:  Desirable but deferrable. Fine to cut if behind schedule. ~15%.
- wont_have:   Explicitly OUT of scope for this release. Will be revisited later. ~5%.

Return ONLY JSON (no fences):
{{
  "prioritized_requirements": [
    {{
      "id": "...",
      "req_id": "FR-001",
      "title": "...",
      "moscow_priority": "must_have|should_have|could_have|wont_have",
      "reasoning": "1-2 sentence justification for this priority assignment"
    }}
  ],
  "summary": {{
    "must_have_count": 0,
    "should_have_count": 0,
    "could_have_count": 0,
    "wont_have_count": 0,
    "mvp_story_points_estimate": 0
  }}
}}

Include ALL requirements in the response, even those you keep at the same priority.""",
        ),
        ("human", "Requirements to prioritize:\n{requirements}"),
    ])

    response = await (prompt | llm).ainvoke({"requirements": json.dumps(reqs_list, indent=2)})
    content = _parse(response.content)

    # Apply the new priorities to the DB, tracking only the ones that changed
    changes = []
    prioritized = content.get("prioritized_requirements", [])

    async with AsyncSessionLocal() as db:
        for item in prioritized:
            # Fetch the requirement row by its UUID
            result = await db.execute(
                select(Requirement).where(Requirement.id == uuid.UUID(item["id"]))
            )
            req = result.scalar_one_or_none()
            if req:
                old_priority = req.priority.value
                new_priority = item.get("moscow_priority", old_priority)

                # Validate the new priority is a valid enum value (defensive check)
                if new_priority not in [p.value for p in RequirementPriority]:
                    new_priority = old_priority  # Ignore invalid values

                # Only update if the priority actually changed
                if old_priority != new_priority:
                    changes.append({
                        "req_id":       req.req_id,
                        "title":        req.title,
                        "old_priority": old_priority,
                        "new_priority": new_priority,
                        "reasoning":    item.get("reasoning", ""),  # The LLM's explanation
                    })
                    req.priority = RequirementPriority(new_priority)
                    req.version += 1  # Increment version to track that this was AI-modified

        # Commit all priority changes in one transaction
        await db.commit()

    return {
        "message": f"MoSCoW prioritization complete. {len(changes)} requirements re-prioritized.",
        "changes": changes,
        "summary": content.get("summary", {}),  # {must_have_count: N, ...}
    }


def _parse(text: str) -> dict:
    """
    Strip markdown fences and parse JSON from LLM output.
    Returns a safe empty structure if parsing fails.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[1:end])
    try:
        return json.loads(text)
    except Exception:
        return {"prioritized_requirements": [], "summary": {}}
