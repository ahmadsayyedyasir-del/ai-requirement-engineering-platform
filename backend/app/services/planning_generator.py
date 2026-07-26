"""
services/planning_generator.py — Phase 5: AI Software Planning Module.

WHAT THIS FILE DOES:
  After requirements are extracted, this service generates 8 planning artifacts
  that answer the practical questions every client asks:
    "How long will it take?" (timeline)
    "How much will it cost?" (cost_estimation)
    "Who do we need to hire?" (team_composition)
    "What do we build first?" (module_breakdown, roadmap)
    "How do we divide the work?" (sprints)
    "What tech should we use?" (tech_stack)
    "What could go wrong?" (risk_assessment)

DESIGN PATTERN:
  All 8 generators follow the same structure:
    1. Build a GPT-4o prompt asking for specific JSON output
    2. Parse the JSON response with _parse()
    3. Build a Markdown summary from the JSON
    4. Return (content_dict, markdown_string)

  The main generate_planning() function loops over all generators and saves
  each result via _save_artifact(). Each artifact is UPSERTED — updated if
  it exists, created if it doesn't. (Unlike documents, planning doesn't need
  per-version history — regeneration overwrites.)

TEMPERATURE=0.3:
  Slightly higher than requirement analysis (0.1) because planning output
  benefits from some judgment and creativity (e.g., tech stack recommendations
  shouldn't always be identical). Still low enough for consistent JSON structure.

ENTRY POINT: generate_planning()
  Called from planning.py endpoint as a background task.
"""

import asyncio  # needed for the concurrency semaphore below
import json
import logging
import uuid
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.planning import PlanningArtifact, PlanningType
from app.models.requirement import Requirement
from app.services.llm_client import get_llm, ainvoke_with_retry
from app.services.generation_tracker import (
    mark_batch_started, mark_batch_finished, record_item_result,
)

logger = logging.getLogger("reqeng.planning")

# See document_generator.py's _CONCURRENCY for the reasoning — a handful of
# concurrent calls (with retry/backoff handling real rate limits) beats a
# strictly sequential loop with a blind fixed delay.
_CONCURRENCY = 3


async def generate_planning(
    project_id: uuid.UUID,
    planning_types: Optional[list[PlanningType]] = None,
) -> None:
    """
    Generate planning artifacts for the given project — all 8 types, or a
    specific subset (e.g. just the ones that failed last run).

    Runs up to _CONCURRENCY generators at once and records the outcome of
    every artifact — success or failure — so the UI can show exactly what
    happened and offer to retry only the failed ones.

    Prerequisites: Requirements must exist in the DB (Phase 3 must have run first).
    """
    # Load requirements once — all generators use the same data
    reqs = await _get_requirements(project_id)

    # All planning generators use the same LLM instance with temperature=0.3
    # (slightly more creative than the extraction pipeline)
    llm = get_llm(temperature=0.3)

    types_to_generate = planning_types or list(_PLANNING_GENERATORS.keys())

    await mark_batch_started(project_id, "planning")
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _run_one(planning_type: PlanningType) -> None:
        generator_fn = _PLANNING_GENERATORS[planning_type]
        async with semaphore:
            try:
                logger.info(f"Generating {planning_type} for project {project_id}")
                content, markdown = await generator_fn(reqs, llm)
                await _save_artifact(project_id, planning_type, content, markdown)
                await record_item_result(project_id, "planning", planning_type.value, ok=True)
            except Exception as e:
                await record_item_result(
                    project_id, "planning", planning_type.value, ok=False, error=str(e)
                )

    await asyncio.gather(*(_run_one(pt) for pt in types_to_generate))
    await mark_batch_finished(project_id, "planning")


async def _get_requirements(project_id: uuid.UUID) -> dict:
    """
    Load all active requirements grouped by category.
    Includes the priority field so planners know what's must-have vs. could-have.
    Description is included in full (not truncated) for planning quality.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Requirement).where(
                Requirement.project_id == project_id,
                Requirement.is_active == True,
            )
        )
        reqs = result.scalars().all()

    # Group by category to give the planning LLM better structure
    grouped = {}
    for req in reqs:
        cat = req.category.value
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append({
            "req_id":      req.req_id,
            "title":       req.title,
            "description": req.description,
            "priority":    req.priority.value,  # Planning needs to know what's must-have
        })
    return grouped


async def _save_artifact(
    project_id: uuid.UUID,
    ptype: PlanningType,
    content: dict,
    markdown: str,
) -> None:
    """
    Upsert a planning artifact row.

    If a row for this (project_id, planning_type) pair already exists,
    UPDATE it in-place. If not, INSERT a new one.

    WHY UPSERT (not versioned like documents)?
      Planning artifacts are meant to reflect the CURRENT state of requirements.
      Unlike SRS documents where history matters, a cost estimate from before
      you added 20 requirements isn't useful to keep. Regeneration replaces the old one.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PlanningArtifact).where(
                PlanningArtifact.project_id == project_id,
                PlanningArtifact.planning_type == ptype,
            )
        )
        artifact = result.scalar_one_or_none()

        if artifact:
            # Update existing artifact with fresh content
            artifact.content = content
            artifact.summary_markdown = markdown
        else:
            # Create new artifact — convert enum to human-readable title
            # e.g., PlanningType.cost_estimation → "Cost Estimation"
            artifact = PlanningArtifact(
                project_id=project_id,
                planning_type=ptype,
                title=ptype.value.replace("_", " ").title(),
                content=content,
                summary_markdown=markdown,
            )
            db.add(artifact)

        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# PLANNING GENERATORS — one async function per planning type
# Each takes (reqs: dict, llm: ChatOpenAI) and returns (content: dict, markdown: str)
# ═══════════════════════════════════════════════════════════════════════════════

async def _gen_module_breakdown(reqs: dict, llm) -> tuple[dict, str]:
    """
    Identify the software modules/components needed to build this system.

    Output: A list of modules, each with name, description, sub-components,
    recommended technologies, dependencies on other modules, complexity rating,
    and which requirements it covers.

    WHY THIS MATTERS: Gives developers a clear picture of what to build BEFORE
    diving into detailed design. Prevents "big ball of mud" architecture.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Identify software modules/components needed for this system.
Return JSON (no fences):
{{
  "modules": [
    {{
      "name": "...", "description": "...",
      "sub_components": ["..."], "technologies": ["..."],
      "dependencies": ["other_module_name"],
      "complexity": "low|medium|high",
      "linked_requirements": ["FR-001"]
    }}
  ]
}}"""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    content = _parse(r.content)
    # Build markdown summary — one section per module
    md = ["# Module Breakdown\n"]
    for m in content.get("modules", []):
        md.append(f"## {m.get('name', '')}\n{m.get('description', '')}")
        sub = m.get("sub_components", [])
        if sub:
            md.append("**Sub-components:** " + ", ".join(sub))
        md.append(f"**Complexity:** {m.get('complexity', 'medium')}")
    return content, "\n\n".join(md)


async def _gen_roadmap(reqs: dict, llm) -> tuple[dict, str]:
    """
    Create a phased development roadmap.

    Phases follow a standard progression: Foundation → Core Features →
    Advanced Features → Testing & Launch. Each phase has objectives,
    deliverables, milestones, and which requirements it covers.

    WHY PHASES? Phasing helps stakeholders understand progress and lets
    teams deliver working software incrementally rather than one big release.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Create a phased development roadmap. Return JSON (no fences):
{{
  "phases": [
    {{
      "phase_number": 1, "name": "...", "duration_weeks": 4,
      "objectives": ["..."], "deliverables": ["..."],
      "milestones": ["..."], "requirements_covered": ["FR-001"]
    }}
  ]
}}
Typical phases: Foundation → Core Features → Advanced Features → Testing & Launch"""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    content = _parse(r.content)
    md = ["# Development Roadmap\n"]
    for p in content.get("phases", []):
        md.append(
            f"## Phase {p.get('phase_number','')} — "
            f"{p.get('name','')} ({p.get('duration_weeks',0)} weeks)"
        )
        if p.get("deliverables"):
            md.append("**Deliverables:**\n" + "\n".join(f"- {d}" for d in p["deliverables"]))
    return content, "\n\n".join(md)


async def _gen_sprints(reqs: dict, llm) -> tuple[dict, str]:
    """
    Create a 2-week Agile sprint plan.

    Each sprint has: a clear goal, which user stories to implement,
    story point total, team capacity calculation, and definition of done.

    Story point velocity used: 20 story points per developer per 2-week sprint
    (industry standard estimate). The LLM adapts this based on complexity.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Create a 2-week Agile sprint plan. Return JSON (no fences):
{{
  "total_sprints": 12, "sprint_duration_days": 14,
  "sprints": [
    {{
      "sprint_number": 1, "sprint_goal": "...",
      "user_stories": ["US-001", "US-002"],
      "story_points": 20,
      "team_capacity": "2 devs × 5 days × 2 pts/day",
      "definition_of_done": ["..."]
    }}
  ]
}}"""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    content = _parse(r.content)
    md = [
        "# Sprint Plan\n",
        f"**Total Sprints:** {content.get('total_sprints', '?')} | "
        f"**Duration:** {content.get('sprint_duration_days', 14)} days\n",
    ]
    for s in content.get("sprints", []):
        md.append(f"## Sprint {s.get('sprint_number','')} — {s.get('sprint_goal','')}")
        md.append(f"**Story Points:** {s.get('story_points', '?')} | **Capacity:** {s.get('team_capacity','?')}")
    return content, "\n\n".join(md)


async def _gen_team(reqs: dict, llm) -> tuple[dict, str]:
    """
    Recommend team composition for this project.

    Output: Each recommended role with headcount, required skills,
    responsibilities, and seniority level. Plus overall team structure.

    WHY THIS IS USEFUL: Clients need to know how many people to hire (or contract)
    before they can approve a project budget. This gives them a concrete starting point.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Recommend team composition for this project. Return JSON (no fences):
{{
  "recommended_team": [
    {{
      "role": "...", "count": 1,
      "skills": ["..."], "responsibilities": ["..."],
      "seniority": "junior|mid|senior"
    }}
  ],
  "total_headcount": 5, "team_structure": "..."
}}"""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    content = _parse(r.content)
    md = [
        "# Recommended Team Composition\n",
        f"**Total Headcount:** {content.get('total_headcount','?')}\n{content.get('team_structure','')}\n",
        "| Role | Count | Seniority | Key Skills |\n|---|---|---|---|",
    ]
    for m in content.get("recommended_team", []):
        skills = ", ".join(m.get("skills", [])[:3])  # Show first 3 skills only
        md.append(f"| {m.get('role','')} | {m.get('count',1)} | {m.get('seniority','')} | {skills} |")
    return content, "\n\n".join(md)


async def _gen_tech_stack(reqs: dict, llm) -> tuple[dict, str]:
    """
    Recommend the technology stack with justification.

    Covers: frontend, backend, database, infrastructure, AI/ML (if applicable),
    third-party services, and an overall justification paragraph.

    WHY JUSTIFICATION MATTERS: Clients often don't trust tech choices without
    reasoning. Including "why React" or "why PostgreSQL" builds confidence.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Recommend a technology stack with justification. Return JSON (no fences):
{{
  "frontend": {{"technology": "...", "framework": "...", "justification": "..."}},
  "backend": {{"language": "...", "framework": "...", "justification": "..."}},
  "database": {{"primary": "...", "secondary": "...", "justification": "..."}},
  "infrastructure": {{"cloud": "...", "containerization": "...", "ci_cd": "..."}},
  "ai_ml": {{"frameworks": ["..."], "models": ["..."]}},
  "third_party_services": [{{"name": "...", "purpose": "..."}}],
  "overall_justification": "..."
}}"""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    content = _parse(r.content)
    md = ["# Recommended Technology Stack\n"]
    for section in ["frontend", "backend", "database", "infrastructure"]:
        details = content.get(section, {})
        if details:
            md.append(f"## {section.title()}")
            for k, v in details.items():
                md.append(f"**{k.replace('_', ' ').title()}:** {v}")
    return content, "\n\n".join(md)


async def _gen_timeline(reqs: dict, llm) -> tuple[dict, str]:
    """
    Estimate total project duration broken down by phase.

    Includes a 20% buffer (buffer_weeks) for unexpected complexity,
    integration issues, and stakeholder review cycles.
    The critical path identifies which items must complete before others can start.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Estimate project timeline. Return JSON (no fences):
{{
  "total_duration_weeks": 24,
  "start_date_assumption": "T+0 (project kick-off)",
  "timeline_breakdown": [
    {{"phase": "Requirements & Design", "weeks": 2, "week_range": "1-2"}},
    {{"phase": "Development", "weeks": 16, "week_range": "3-18"}},
    {{"phase": "Testing & QA", "weeks": 4, "week_range": "19-22"}},
    {{"phase": "Deployment & Handover", "weeks": 2, "week_range": "23-24"}}
  ],
  "critical_path": ["..."], "buffer_weeks": 2, "assumptions": ["..."]
}}"""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    content = _parse(r.content)
    md = [
        "# Project Timeline\n",
        f"**Total Duration:** {content.get('total_duration_weeks','?')} weeks "
        f"(including {content.get('buffer_weeks',0)} weeks buffer)\n",
        "| Phase | Duration | Weeks |\n|---|---|---|",
    ]
    for t in content.get("timeline_breakdown", []):
        md.append(f"| {t.get('phase','')} | {t.get('weeks','')} weeks | {t.get('week_range','')} |")
    return content, "\n\n".join(md)


async def _gen_cost(reqs: dict, llm) -> tuple[dict, str]:
    """
    Generate a cost estimation breakdown.

    Covers: labor costs (per role), infrastructure costs (cloud, DB),
    third-party licenses, plus a 20% contingency buffer.

    WHY 20% CONTINGENCY?
      Software projects almost always encounter scope changes, integration issues,
      or unexpected complexity. 20% is the industry-standard buffer. Without it,
      the first unexpected problem puts the project over budget.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate a cost estimation breakdown. Return JSON (no fences):
{{
  "estimation_methodology": "...", "currency": "USD",
  "labor_costs": [{{"role": "...", "count": 1, "months": 6, "monthly_rate": 5000, "total": 30000}}],
  "infrastructure_costs": [{{"item": "...", "monthly_cost": 200, "duration_months": 12, "total": 2400}}],
  "third_party_licenses": [{{"service": "...", "monthly_cost": 100, "total": 1200}}],
  "subtotal_labor": 0, "subtotal_infrastructure": 0,
  "contingency_percentage": 20, "contingency_amount": 0,
  "total_estimate": 0, "notes": "..."
}}
Calculate all totals accurately. Include 20% contingency buffer."""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    content = _parse(r.content)
    md = ["# Cost Estimation\n", f"**Methodology:** {content.get('estimation_methodology','')}\n"]
    md.append("## Labor Costs\n| Role | Count | Duration | Rate/Month | Total |\n|---|---|---|---|---|")
    for l in content.get("labor_costs", []):
        md.append(
            f"| {l.get('role','')} | {l.get('count',1)} | "
            f"{l.get('months',0)} months | ${l.get('monthly_rate',0):,} | ${l.get('total',0):,} |"
        )
    contingency = content.get('contingency_percentage', 20)
    total = content.get('total_estimate', 0)
    md.append(f"\n**Total Estimate (with {contingency}% contingency): ${total:,}**")
    return content, "\n\n".join(md)


async def _gen_risk(reqs: dict, llm) -> tuple[dict, str]:
    """
    Generate a comprehensive risk assessment table.

    At least 8 risks across categories: technical, schedule, resource, business, security.
    Each risk has: likelihood, impact, risk score, mitigation strategy, and contingency plan.

    RISK SCORE = f(likelihood, impact):
      Both high    → high risk
      One high     → medium risk
      Both low     → low risk
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate a comprehensive risk assessment table. Return JSON (no fences):
{{
  "risks": [
    {{
      "id": "RSK-001",
      "category": "technical|schedule|resource|business|security",
      "description": "...", "likelihood": "high|medium|low", "impact": "high|medium|low",
      "risk_score": "high|medium|low", "mitigation_strategy": "...",
      "contingency_plan": "...", "owner": "...", "status": "open"
    }}
  ]
}}
Include at least 8 risks across different categories."""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    content = _parse(r.content)
    md = [
        "# Risk Assessment\n",
        "| ID | Category | Description | Likelihood | Impact | Score | Mitigation |\n|---|---|---|---|---|---|---|",
    ]
    for risk in content.get("risks", []):
        # Truncate long text to keep the table readable
        desc = risk.get("description", "")[:50] + "..."
        mitigation = risk.get("mitigation_strategy", "")[:50] + "..."
        md.append(
            f"| {risk.get('id','')} | {risk.get('category','')} | {desc} | "
            f"{risk.get('likelihood','')} | {risk.get('impact','')} | "
            f"{risk.get('risk_score','')} | {mitigation} |"
        )
    return content, "\n\n".join(md)


# ── DISPATCH TABLE ─────────────────────────────────────────────────────────────
# Maps each PlanningType to its generator function.
# generate_planning() iterates over this dict to generate all artifacts.
# To add a new planning type: add to PlanningType enum AND add here.
_PLANNING_GENERATORS = {
    PlanningType.module_breakdown:  _gen_module_breakdown,
    PlanningType.roadmap:           _gen_roadmap,
    PlanningType.sprints:           _gen_sprints,
    PlanningType.team_composition:  _gen_team,
    PlanningType.tech_stack:        _gen_tech_stack,
    PlanningType.timeline:          _gen_timeline,
    PlanningType.cost_estimation:   _gen_cost,
    PlanningType.risk_assessment:   _gen_risk,
}


def _parse(text: str) -> dict:
    """
    Strip markdown code fences and parse JSON from LLM response.

    GPT-4o sometimes wraps JSON in ```json...``` even when instructed not to.
    This helper strips those fences and falls back gracefully if JSON parsing fails.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Find the closing ``` and strip from first content line to before it
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    try:
        return json.loads(text)
    except Exception as e:
        # Raising (instead of silently wrapping raw text) lets the caller record
        # this planning artifact as a visible, retry-able failure rather than
        # saving unstructured leftover text that looks like a broken artifact.
        raise ValueError(f"LLM did not return valid JSON: {e}") from e