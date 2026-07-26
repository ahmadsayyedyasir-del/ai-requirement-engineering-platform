"""
services/document_generator.py — Phase 4: AI Documentation Generator.

WHAT THIS FILE DOES:
  Reads structured requirements from PostgreSQL and generates professional
  software engineering documents using GPT-4o.

  Generates 8 document types (each is a separate AI call):
    SRS               — Software Requirements Specification (the master technical doc)
    BRD               — Business Requirements Document (business-focused)
    User Stories      — Agile "As a [role] I want [goal] so that [benefit]" format
    Use Cases         — Detailed actor/flow/precondition/postcondition specs
    Acceptance Criteria — Gherkin Given/When/Then test scenarios
    Glossary          — Definitions of domain-specific terms
    Functional Spec   — Detailed feature-by-feature technical specification
    Non-Functional Spec — Performance, security, reliability requirements

DESIGN PATTERN:
  Every generator function follows the same 4-step pattern:
    1. Load requirements from DB (_get_requirements_for_project)
    2. Build a GPT-4o prompt with JSON output schema instruction
    3. Parse the JSON response (_parse_json_response)
    4. Convert JSON to Markdown and save both (_save_document)

  This consistency makes it easy to add new document types later —
  just follow the same pattern and add to the _GENERATORS dict.

VERSIONING:
  _save_document() uses an upsert pattern:
    - First time: creates Document + DocumentVersion(v1)
    - Subsequent times: increments Document.current_version, creates new DocumentVersion
  This preserves full history for the diff viewer.

ENTRY POINT: generate_document()
  Called by documents.py as a background task.
"""

import json
import asyncio  # needed for the concurrency semaphore below
import logging
import uuid
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.document import Document, DocumentVersion, DocumentType
from app.models.requirement import Requirement, RequirementCategory
from app.services.llm_client import get_llm, ainvoke_with_retry
from app.services.generation_tracker import (
    mark_batch_started, mark_batch_finished, record_item_result,
)

logger = logging.getLogger("reqeng.docgen")

# Max document generations running at once. WHY 3 (not all 8 at once, not 1)?
# Groq's free tier allows ~30 requests/minute and ~12,000 tokens/minute. Running
# a handful concurrently — with ainvoke_with_retry() handling any 429s that do
# slip through — finishes noticeably faster than the old strictly-sequential
# loop with a blind 5s sleep after every call, without hammering the API.
_CONCURRENCY = 3


async def generate_document(
    project_id: uuid.UUID,
    doc_types: Optional[list[DocumentType]] = None,
) -> None:
    """
    Generate one or all document types for the given project.

    This is the public entry point called from the documents.py endpoint.
    Runs up to _CONCURRENCY generators at once (instead of one at a time with
    a fixed delay), and records the outcome of every item — success or
    failure — on the project so the UI can show exactly what happened.

    Args:
        project_id: Which project to generate documents for
        doc_types:  Which document types to generate. None = all 8 types.

    Errors in one document type don't stop generation of others — each
    type is tried independently and its failure is recorded rather than
    only logged, so it's visible to the user and retry-able individually.
    """
    # If no types specified, generate all 8 types
    types_to_generate = doc_types or list(DocumentType)

    await mark_batch_started(project_id, "documents")
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _run_one(doc_type: DocumentType) -> None:
        async with semaphore:
            try:
                logger.info(f"Generating {doc_type} for project {project_id}")
                generator = _GENERATORS.get(doc_type)
                if generator:
                    await generator(project_id)
                await record_item_result(project_id, "documents", doc_type.value, ok=True)
            except Exception as e:
                await record_item_result(
                    project_id, "documents", doc_type.value, ok=False, error=str(e)
                )

    await asyncio.gather(*(_run_one(dt) for dt in types_to_generate))
    await mark_batch_finished(project_id, "documents")


async def _get_requirements_for_project(project_id: uuid.UUID) -> dict:
    """
    Load all active requirements for a project, grouped by category.

    Returns a dict like:
    {
      "functional": [{"req_id": "FR-001", "title": "...", "description": "...", ...}],
      "non_functional": [...],
      "user_role": [...],
      ...
    }

    Why grouped by category?
      The LLM can understand "here are the functional requirements, here are the
      NFRs" much better than a flat unsorted list. Grouped format produces
      better-structured document output.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Requirement).where(
                Requirement.project_id == project_id,
                Requirement.is_active == True,  # Skip soft-deleted requirements
            )
        )
        reqs = result.scalars().all()

    # Group requirements by category into a dict
    grouped = {}
    for req in reqs:
        cat = req.category.value  # e.g., "functional"
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append({
            "req_id":      req.req_id,
            "title":       req.title,
            "description": req.description,
            "priority":    req.priority.value,
            # Column is named extra_metadata (renamed from metadata to avoid
            # SQLAlchemy's reserved MetaData attribute name conflict)
            "extra_metadata": req.extra_metadata or {},
        })
    return grouped


async def _save_document(
    project_id: uuid.UUID,
    doc_type: DocumentType,
    title: str,
    content_json: dict,
    content_markdown: str,
) -> None:
    """
    Upsert a document and create a new version row.

    UPSERT LOGIC:
      - If no Document row exists for (project_id, doc_type): create it at version 1
      - If a Document row already exists: increment current_version

    Either way, always create a new DocumentVersion row with the full content.
    This preserves complete version history — old versions are never overwritten.

    Args:
        content_json:     The structured AI output (dict) — canonical form
        content_markdown: The rendered markdown for display
    """
    async with AsyncSessionLocal() as db:
        # Look for an existing document header row
        result = await db.execute(
            select(Document).where(
                Document.project_id == project_id,
                Document.doc_type == doc_type,
            )
        )
        doc = result.scalar_one_or_none()

        if not doc:
            # First generation — create the document header at version 1
            doc = Document(
                project_id=project_id,
                doc_type=doc_type,
                title=title,
                current_version=1,
            )
            db.add(doc)
            await db.flush()          # Get the auto-generated UUID assigned
            new_version_number = 1
        else:
            # Regeneration — increment the version counter
            doc.current_version += 1
            new_version_number = doc.current_version

        # Create a new DocumentVersion row with the full content
        version = DocumentVersion(
            document_id=doc.id,
            version_number=new_version_number,
            content_json=content_json,
            content_markdown=content_markdown,
            change_summary=f"AI-generated version {new_version_number}",
        )
        db.add(version)
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT GENERATORS — one function per document type
# Each follows the pattern: load reqs → prompt GPT-4o → parse JSON → save
# ═══════════════════════════════════════════════════════════════════════════════

async def _generate_srs(project_id: uuid.UUID) -> None:
    """
    Generate the SRS (Software Requirements Specification).

    The SRS is the most comprehensive technical document — it covers:
    - Introduction (purpose, scope, overview)
    - Overall description (product perspective, user characteristics, constraints)
    - Functional requirements (each with ID, description, priority)
    - Non-functional requirements (performance, security, usability)
    - System constraints
    - Appendix (glossary)

    Temperature=0.2: Low enough for consistent structure, allows some phrasing variation.
    """
    reqs = await _get_requirements_for_project(project_id)
    llm = get_llm(temperature=0.2)

    # The prompt instructs GPT-4o to produce the exact JSON structure we need.
    # Double braces {{ }} are Python string escaping for literal { } in the template.
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a senior software architect writing a professional SRS document.
Generate a complete Software Requirements Specification based on the provided requirements.
Return ONLY a valid JSON object (no markdown fences):
{{
  "document_title": "...",
  "version": "1.0",
  "date": "...",
  "sections": {{
    "introduction": {{
      "purpose": "...", "scope": "...",
      "definitions": [{{"term": "...", "definition": "..."}}],
      "overview": "..."
    }},
    "overall_description": {{
      "product_perspective": "...",
      "product_functions": ["..."],
      "user_characteristics": ["..."],
      "constraints": ["..."],
      "assumptions_and_dependencies": ["..."]
    }},
    "functional_requirements": [
      {{"id": "FR-001", "title": "...", "description": "...", "priority": "..."}}
    ],
    "non_functional_requirements": [
      {{"id": "NFR-001", "category": "performance|security|usability|...", "description": "..."}}
    ],
    "system_constraints": ["..."],
    "appendix": {{"glossary": [{{"term": "...", "definition": "..."}}]}}
  }}
}}"""),
        ("human", "Requirements:\n{requirements_json}"),
    ])

    response = await ainvoke_with_retry(prompt | llm, 
        {"requirements_json": json.dumps(reqs, indent=2)}
    )
    content = _parse_json_response(response.content)
    markdown = _srs_to_markdown(content)
    await _save_document(
        project_id, DocumentType.srs, "Software Requirements Specification", content, markdown
    )


def _srs_to_markdown(data: dict) -> str:
    """Convert the SRS JSON dict to a formatted Markdown string for display."""
    sections = data.get("sections", {})
    md = [
        f"# {data.get('document_title', 'Software Requirements Specification')}",
        f"**Version:** {data.get('version', '1.0')} | **Date:** {data.get('date', 'N/A')}\n",
    ]
    intro = sections.get("introduction", {})
    md.append("## 1. Introduction")
    md.append(f"### 1.1 Purpose\n{intro.get('purpose', '')}")
    md.append(f"### 1.2 Scope\n{intro.get('scope', '')}")
    md.append(f"### 1.3 Overview\n{intro.get('overview', '')}")
    overall = sections.get("overall_description", {})
    md.append("## 2. Overall Description")
    md.append(f"### 2.1 Product Perspective\n{overall.get('product_perspective', '')}")
    funcs = overall.get("product_functions", [])
    if funcs:
        md.append("### 2.2 Product Functions\n" + "\n".join(f"- {f}" for f in funcs))
    frs = sections.get("functional_requirements", [])
    if frs:
        md.append("## 3. Functional Requirements")
        for fr in frs:
            md.append(f"### {fr.get('id', '')} — {fr.get('title', '')}")
            md.append(f"**Priority:** {fr.get('priority', '')}\n\n{fr.get('description', '')}")
    nfrs = sections.get("non_functional_requirements", [])
    if nfrs:
        md.append("## 4. Non-Functional Requirements")
        for nfr in nfrs:
            md.append(f"### {nfr.get('id', '')} — {nfr.get('category', '').title()}")
            md.append(nfr.get("description", ""))
    return "\n\n".join(md)


async def _generate_brd(project_id: uuid.UUID) -> None:
    """
    Generate the BRD (Business Requirements Document).
    Unlike SRS, BRD is business-focused — talks about business problem,
    stakeholders, and success metrics rather than technical requirements.
    """
    reqs = await _get_requirements_for_project(project_id)
    llm = get_llm(temperature=0.2)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate a Business Requirements Document (BRD) as JSON (no fences):
{{
  "document_title": "...", "executive_summary": "...", "business_problem": "...",
  "project_objectives": ["..."],
  "stakeholders": [{{"name": "...", "role": "...", "interest": "..."}}],
  "business_requirements": [{{"id": "BRQ-001", "description": "...", "success_metric": "..."}}],
  "out_of_scope": ["..."], "assumptions": ["..."],
  "risks": [{{"description": "...", "mitigation": "..."}}],
  "success_criteria": ["..."], "timeline_overview": "..."
}}"""),
        ("human", "Requirements:\n{requirements_json}"),
    ])
    response = await ainvoke_with_retry(prompt | llm, {"requirements_json": json.dumps(reqs, indent=2)})
    content = _parse_json_response(response.content)
    markdown = _brd_to_markdown(content)
    await _save_document(project_id, DocumentType.brd, "Business Requirements Document", content, markdown)


def _brd_to_markdown(data: dict) -> str:
    """Convert BRD JSON dict to formatted Markdown."""
    md = [f"# {data.get('document_title', 'Business Requirements Document')}\n"]
    md.append(f"## Executive Summary\n{data.get('executive_summary', '')}")
    md.append(f"## Business Problem\n{data.get('business_problem', '')}")
    if data.get("project_objectives"):
        md.append("## Project Objectives\n" + "\n".join(f"- {o}" for o in data["project_objectives"]))
    stakeholders = data.get("stakeholders", [])
    if stakeholders:
        md.append("## Stakeholders\n| Name | Role | Interest |\n|---|---|---|")
        for s in stakeholders:
            md.append(f"| {s.get('name','')} | {s.get('role','')} | {s.get('interest','')} |")
    brs = data.get("business_requirements", [])
    if brs:
        md.append("## Business Requirements")
        for br in brs:
            md.append(f"**{br.get('id','')}:** {br.get('description','')}\n*Success metric:* {br.get('success_metric','')}")
    return "\n\n".join(md)


async def _generate_user_stories(project_id: uuid.UUID) -> None:
    """
    Generate User Stories in standard Agile format.
    Each story: "As a [role], I want [goal], so that [benefit]"
    Includes story points, priority, acceptance criteria, and linked requirements.
    Temperature=0.3 allows slightly more creative language in story descriptions.
    """
    reqs = await _get_requirements_for_project(project_id)
    llm = get_llm(temperature=0.3)  # Slightly higher temp — user stories benefit from varied phrasing
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate user stories in Agile format as JSON (no fences):
{{
  "user_stories": [
    {{
      "id": "US-001", "as_a": "...", "i_want": "...", "so_that": "...",
      "story_points": 3,
      "priority": "must_have|should_have|could_have|wont_have",
      "acceptance_criteria": ["Given ... When ... Then ..."],
      "linked_requirements": ["FR-001"]
    }}
  ]
}}
Story points: 1=trivial, 2=small, 3=medium, 5=large, 8=complex, 13=epic (should be split)."""),
        ("human", "Requirements:\n{requirements_json}"),
    ])
    response = await ainvoke_with_retry(prompt | llm, {"requirements_json": json.dumps(reqs, indent=2)})
    content = _parse_json_response(response.content)
    markdown = _user_stories_to_markdown(content)
    await _save_document(project_id, DocumentType.user_stories, "User Stories", content, markdown)


def _user_stories_to_markdown(data: dict) -> str:
    """Convert user stories JSON to formatted Markdown."""
    stories = data.get("user_stories", [])
    md = ["# User Stories\n"]
    for s in stories:
        md.append(f"## {s.get('id', '')} — As a {s.get('as_a', '')}")
        md.append(
            f"**Story:** As a **{s.get('as_a','')}**, I want **{s.get('i_want','')}**, "
            f"so that **{s.get('so_that','')}**."
        )
        md.append(f"**Story Points:** {s.get('story_points', '?')} | **Priority:** {s.get('priority', '?')}")
        criteria = s.get("acceptance_criteria", [])
        if criteria:
            md.append("**Acceptance Criteria:**\n" + "\n".join(f"- {c}" for c in criteria))
        linked = s.get("linked_requirements", [])
        if linked:
            md.append(f"**Linked Requirements:** {', '.join(linked)}")
        md.append("---")
    return "\n\n".join(md)


async def _generate_use_cases(project_id: uuid.UUID) -> None:
    """
    Generate detailed Use Cases with actors, preconditions, main/alternative flows.
    Use Cases are more formal than user stories — they describe every step of
    an interaction including error paths and postconditions.
    """
    reqs = await _get_requirements_for_project(project_id)
    llm = get_llm(temperature=0.2)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate detailed use cases as JSON (no fences):
{{
  "use_cases": [
    {{
      "id": "UC-001", "name": "...", "actors": ["..."],
      "description": "...", "preconditions": ["..."],
      "main_flow": ["Step 1: ...", "Step 2: ..."],
      "alternative_flows": [{{"condition": "...", "steps": ["..."]}}],
      "postconditions": ["..."], "exceptions": ["..."],
      "linked_requirements": ["FR-001"]
    }}
  ]
}}"""),
        ("human", "Requirements:\n{requirements_json}"),
    ])
    response = await ainvoke_with_retry(prompt | llm, {"requirements_json": json.dumps(reqs, indent=2)})
    content = _parse_json_response(response.content)
    markdown = _use_cases_to_markdown(content)
    await _save_document(project_id, DocumentType.use_cases, "Use Cases", content, markdown)


def _use_cases_to_markdown(data: dict) -> str:
    """Convert use cases JSON to formatted Markdown."""
    use_cases = data.get("use_cases", [])
    md = ["# Use Cases\n"]
    for uc in use_cases:
        md.append(f"## {uc.get('id', '')} — {uc.get('name', '')}")
        md.append(f"**Actors:** {', '.join(uc.get('actors', []))}")
        md.append(f"**Description:** {uc.get('description', '')}")
        if uc.get("preconditions"):
            md.append("**Preconditions:**\n" + "\n".join(f"- {p}" for p in uc["preconditions"]))
        if uc.get("main_flow"):
            md.append("**Main Flow:**\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(uc["main_flow"])))
        if uc.get("postconditions"):
            md.append("**Postconditions:**\n" + "\n".join(f"- {p}" for p in uc["postconditions"]))
        md.append("---")
    return "\n\n".join(md)


async def _generate_acceptance_criteria(project_id: uuid.UUID) -> None:
    """
    Generate Gherkin-format acceptance criteria for each functional requirement.
    Format: Given [precondition] When [action] Then [expected outcome]
    Each requirement gets at least 2 scenarios (happy path + error path).
    """
    reqs = await _get_requirements_for_project(project_id)
    llm = get_llm(temperature=0.2)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate acceptance criteria for all functional requirements as JSON (no fences):
{{
  "acceptance_criteria": [
    {{
      "requirement_id": "FR-001", "requirement_title": "...",
      "criteria": [{{"scenario": "...", "given": "...", "when": "...", "then": "..."}}]
    }}
  ]
}}
Write at least 2 Gherkin scenarios per requirement (happy path and error path)."""),
        ("human", "Requirements:\n{requirements_json}"),
    ])
    response = await ainvoke_with_retry(prompt | llm, {"requirements_json": json.dumps(reqs, indent=2)})
    content = _parse_json_response(response.content)
    markdown = _ac_to_markdown(content)
    await _save_document(project_id, DocumentType.acceptance_criteria, "Acceptance Criteria", content, markdown)


def _ac_to_markdown(data: dict) -> str:
    """Convert acceptance criteria JSON to formatted Markdown."""
    items = data.get("acceptance_criteria", [])
    md = ["# Acceptance Criteria\n"]
    for item in items:
        md.append(f"## {item.get('requirement_id', '')} — {item.get('requirement_title', '')}")
        for c in item.get("criteria", []):
            md.append(f"### Scenario: {c.get('scenario', '')}")
            md.append(f"- **Given** {c.get('given', '')}")
            md.append(f"- **When** {c.get('when', '')}")
            md.append(f"- **Then** {c.get('then', '')}")
        md.append("---")
    return "\n\n".join(md)


async def _generate_glossary(project_id: uuid.UUID) -> None:
    """
    Extract domain-specific terms and generate a glossary.
    Temperature=0.1: very low — definitions should be precise and consistent.
    """
    reqs = await _get_requirements_for_project(project_id)
    llm = get_llm(temperature=0.1)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Extract domain-specific terms and generate a glossary as JSON (no fences):
{{ "glossary": [{{"term": "...", "definition": "...", "context": "..."}}] }}"""),
        ("human", "Requirements:\n{requirements_json}"),
    ])
    response = await ainvoke_with_retry(prompt | llm, {"requirements_json": json.dumps(reqs, indent=2)})
    content = _parse_json_response(response.content)
    markdown = _glossary_to_markdown(content)
    await _save_document(project_id, DocumentType.glossary, "Glossary of Terms", content, markdown)


def _glossary_to_markdown(data: dict) -> str:
    """Convert glossary JSON to formatted Markdown, sorted alphabetically."""
    terms = data.get("glossary", [])
    md = ["# Glossary of Terms\n"]
    # Sort alphabetically so the glossary is easy to scan
    for t in sorted(terms, key=lambda x: x.get("term", "").lower()):
        md.append(f"**{t.get('term', '')}**\n{t.get('definition', '')}")
        if t.get("context"):
            md.append(f"*Context: {t['context']}*")
        md.append("")
    return "\n\n".join(md)


async def _generate_functional_spec(project_id: uuid.UUID) -> None:
    """
    Generate a detailed Functional Specification broken down by module.
    More technical than the SRS — includes inputs, outputs, business logic,
    and edge cases for each feature within each module.
    """
    reqs = await _get_requirements_for_project(project_id)
    llm = get_llm(temperature=0.2)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Write a detailed Functional Specification as JSON (no fences):
{{
  "title": "Functional Specification",
  "modules": [{{
    "module_name": "...", "description": "...",
    "features": [{{
      "feature_id": "...", "name": "...", "description": "...",
      "inputs": ["..."], "outputs": ["..."],
      "business_logic": "...", "edge_cases": ["..."]
    }}]
  }}]
}}"""),
        ("human", "Requirements:\n{requirements_json}"),
    ])
    response = await ainvoke_with_retry(prompt | llm, {"requirements_json": json.dumps(reqs, indent=2)})
    content = _parse_json_response(response.content)
    md_lines = [f"# {content.get('title', 'Functional Specification')}\n"]
    for mod in content.get("modules", []):
        md_lines.append(f"## {mod.get('module_name', '')}\n{mod.get('description', '')}")
        for feat in mod.get("features", []):
            md_lines.append(f"### {feat.get('feature_id','')} — {feat.get('name','')}")
            md_lines.append(feat.get("description", ""))
    markdown = "\n\n".join(md_lines)
    await _save_document(project_id, DocumentType.functional_spec, "Functional Specification", content, markdown)


async def _generate_non_functional_spec(project_id: uuid.UUID) -> None:
    """
    Generate a Non-Functional Specification covering quality attributes:
    performance, security, reliability, usability, maintainability, deployment.
    """
    reqs = await _get_requirements_for_project(project_id)
    llm = get_llm(temperature=0.2)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Write a Non-Functional Specification as JSON (no fences):
{{
  "title": "Non-Functional Specification",
  "performance": {{"response_time": "...", "throughput": "...", "scalability": "..."}},
  "security": {{"authentication": "...", "authorization": "...", "data_protection": "...", "compliance": "..."}},
  "reliability": {{"availability": "...", "mttr": "...", "backup_strategy": "..."}},
  "usability": {{"accessibility": "...", "browser_support": "...", "mobile_support": "..."}},
  "maintainability": {{"code_standards": "...", "documentation": "...", "testing_coverage": "..."}},
  "deployment": {{"environment": "...", "ci_cd": "...", "monitoring": "..."}}
}}"""),
        ("human", "Requirements:\n{requirements_json}"),
    ])
    response = await ainvoke_with_retry(prompt | llm, {"requirements_json": json.dumps(reqs, indent=2)})
    content = _parse_json_response(response.content)
    md_lines = [f"# {content.get('title', 'Non-Functional Specification')}\n"]
    for section, details in content.items():
        if section == "title":
            continue
        if isinstance(details, dict):
            md_lines.append(f"## {section.title()}")
            for k, v in details.items():
                md_lines.append(f"**{k.replace('_', ' ').title()}:** {v}")
    markdown = "\n\n".join(md_lines)
    await _save_document(project_id, DocumentType.non_functional_spec, "Non-Functional Specification", content, markdown)


# ── DISPATCH TABLE ─────────────────────────────────────────────────────────────
# Maps each DocumentType enum value to its generator function.
# generate_document() looks up the right function here.
# To add a new document type: add an enum value to DocumentType AND add it here.
_GENERATORS = {
    DocumentType.srs:                  _generate_srs,
    DocumentType.brd:                  _generate_brd,
    DocumentType.user_stories:         _generate_user_stories,
    DocumentType.use_cases:            _generate_use_cases,
    DocumentType.acceptance_criteria:  _generate_acceptance_criteria,
    DocumentType.glossary:             _generate_glossary,
    DocumentType.functional_spec:      _generate_functional_spec,
    DocumentType.non_functional_spec:  _generate_non_functional_spec,
}


# ── HELPER ─────────────────────────────────────────────────────────────────────

def _parse_json_response(text: str) -> dict:
    """
    Clean and parse a JSON string from an LLM response.

    PROBLEM: GPT-4o sometimes wraps JSON output in markdown code fences:
        ```json
        {"key": "value"}
        ```
    even when instructed not to. This function strips those fences before parsing.

    WHY RAISE INSTEAD OF SILENTLY FALLING BACK:
      This used to fall back to {"raw_content": text} on a parse failure,
      which saved a "document" that was really just unstructured leftover
      text — it looked like a generated document but had none of the
      expected structure. That's exactly the "pattern isn't right"
      inconsistency users hit. Raising here lets the caller record this
      document type as a clear, visible FAILURE (retry-able) instead of a
      silently malformed success.
    """
    text = text.strip()

    # Remove markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Find the closing ``` and remove everything outside the fences
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM did not return valid JSON: {e}") from e