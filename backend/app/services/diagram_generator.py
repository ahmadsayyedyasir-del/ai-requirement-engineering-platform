"""
services/diagram_generator.py — Phase 6: AI Mermaid.js Diagram Generator.

WHAT THIS FILE DOES:
  Generates 6 types of software engineering diagrams as Mermaid.js source code.
  The code is stored in the database and rendered live in the browser using
  the Mermaid.js JavaScript library — no server-side rendering needed.

WHY MERMAID.JS?
  Traditional diagramming tools (Visio, Lucidchart) produce binary image files.
  Mermaid uses TEXT as the source format:
    erDiagram
      USER { uuid id PK; string email }
      ORDER { uuid id PK; uuid user_id FK }
      USER ||--o{ ORDER : places
  Benefits:
    - Stored as text in PostgreSQL → version-controllable, diff-friendly
    - Rendered client-side → no server-side image generation infrastructure
    - Copy-paste into GitHub/GitLab/Notion/Confluence → renders automatically
    - Editable → analysts can paste into any Mermaid editor to modify

WHY TEMPERATURE=0.1?
  Mermaid has STRICT syntax. A misplaced curly brace or wrong arrow type
  causes the entire diagram to fail to render. Temperature=0.1 makes the
  LLM output as predictable and syntax-correct as possible.

UPSERT BEHAVIOR:
  Unlike documents (versioned), diagrams are UPSERTED — regeneration
  overwrites the source_code in place. We don't need full history for diagrams
  because the requirements (which drive diagram content) are versioned separately.

6 DIAGRAM TYPES:
  use_case      → flowchart TB showing actors and use cases
  flowchart     → flowchart TD showing the main process steps
  er_diagram    → erDiagram showing database entities and relationships
  sequence      → sequenceDiagram showing component interactions
  class_diagram → classDiagram showing domain object model
  architecture  → graph TB showing system layers (client, API, data)

ENTRY POINT: generate_diagrams()
  Called from diagrams.py endpoint as a background task.
"""

import asyncio  # needed for the concurrency semaphore below
import json
import logging
import uuid
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.diagram import Diagram, DiagramType, DiagramFormat
from app.models.requirement import Requirement
from app.services.llm_client import get_llm, ainvoke_with_retry
from app.services.generation_tracker import (
    mark_batch_started, mark_batch_finished, record_item_result,
)

logger = logging.getLogger("reqeng.diagrams")

# See document_generator.py's _CONCURRENCY for the reasoning.
_CONCURRENCY = 3


async def generate_diagrams(
    project_id: uuid.UUID,
    diagram_types: Optional[list[DiagramType]] = None,
) -> None:
    """
    Generate diagrams for the project — all 6 types, or a specific subset.

    Loads requirements once, then runs up to _CONCURRENCY diagram generators
    at once. If one diagram fails (e.g., LLM produced invalid Mermaid syntax
    even after retries), it's recorded as a visible failure — continuing to
    generate the rest — rather than only logged server-side.

    Args:
        project_id:    Which project to generate diagrams for.
        diagram_types: Specific types to (re)generate, e.g. only the ones that
                        failed last time. None = generate all 6 types.
    """
    reqs = await _get_requirements(project_id)

    # temperature=0.1 — critical for valid Mermaid syntax (strict format required)
    llm = get_llm(temperature=0.1)

    types_to_generate = diagram_types or list(_DIAGRAM_GENERATORS.keys())

    await mark_batch_started(project_id, "diagrams")
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _run_one(diagram_type: DiagramType) -> None:
        generator_fn = _DIAGRAM_GENERATORS[diagram_type]
        async with semaphore:
            try:
                logger.info(f"Generating {diagram_type} diagram for project {project_id}")
                title, source_code = await generator_fn(reqs, llm)
                if not source_code.strip():
                    # An empty/blank diagram is a failure, not a valid result —
                    # don't save it silently as if generation succeeded.
                    raise ValueError("LLM returned an empty diagram")
                await _save_diagram(project_id, diagram_type, title, source_code)
                await record_item_result(project_id, "diagrams", diagram_type.value, ok=True)
            except Exception as e:
                await record_item_result(
                    project_id, "diagrams", diagram_type.value, ok=False, error=str(e)
                )

    await asyncio.gather(*(_run_one(dt) for dt in types_to_generate))
    await mark_batch_finished(project_id, "diagrams")


async def _get_requirements(project_id: uuid.UUID) -> dict:
    """
    Load requirements grouped by category for diagram generation.
    Descriptions are truncated to 200 chars — diagram prompts need the structure,
    not every detail of each requirement.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Requirement).where(
                Requirement.project_id == project_id,
                Requirement.is_active == True,
            )
        )
        reqs = result.scalars().all()

    grouped = {}
    for req in reqs:
        cat = req.category.value
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append({
            "req_id":      req.req_id,
            "title":       req.title,
            "description": req.description[:200],  # Truncate to save tokens
        })
    return grouped


async def _save_diagram(
    project_id: uuid.UUID,
    dtype: DiagramType,
    title: str,
    source_code: str,
) -> None:
    """
    Upsert a diagram row — update source_code if exists, insert if new.

    WHY UPSERT NOT VERSION?
      Diagrams are directly derived from requirements. When requirements change
      and diagrams are regenerated, the new diagram REPLACES the old one.
      We don't need to keep "what did the ER diagram look like 3 analyses ago?"
      The requirements table provides that history via version numbers.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Diagram).where(
                Diagram.project_id == project_id,
                Diagram.diagram_type == dtype,
            )
        )
        diagram = result.scalar_one_or_none()

        if diagram:
            # Update existing diagram's source code and title
            diagram.source_code = source_code
            diagram.title = title
        else:
            # Create new diagram record
            diagram = Diagram(
                project_id=project_id,
                diagram_type=dtype,
                diagram_format=DiagramFormat.mermaid,  # Always Mermaid
                title=title,
                source_code=source_code,
            )
            db.add(diagram)

        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# DIAGRAM GENERATORS — one async function per diagram type
# Each takes (reqs: dict, llm: ChatOpenAI) and returns (title: str, source: str)
# ═══════════════════════════════════════════════════════════════════════════════

async def _gen_use_case(reqs: dict, llm) -> tuple[str, str]:
    """
    Generate a Use Case Diagram using Mermaid flowchart syntax.

    Shows ACTORS (users/external systems) connecting to USE CASES (what they do).
    Uses actors from user_roles and use cases from functional_requirements.
    Max 15 nodes — more than that becomes unreadable.

    Why flowchart syntax (not a native UML use case syntax)?
    Mermaid doesn't have a dedicated use-case diagram type, so we use
    flowchart TB (top-to-bottom) with actors styled as circles [( )] and
    use cases as rectangles [ ] inside a subgraph representing the system boundary.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate a Mermaid.js Use Case Diagram.
Return ONLY raw Mermaid code (no fences, no explanation).

Use this format:
flowchart TB
    Actor1([Actor Name])
    subgraph System["System Name"]
        UC1[Use Case 1]
        UC2[Use Case 2]
    end
    Actor1 --> UC1
    Actor1 --> UC2

Use actors from user_roles and use cases from functional_requirements. Max 15 nodes."""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    return "Use Case Diagram", _clean_mermaid(r.content)


async def _gen_flowchart(reqs: dict, llm) -> tuple[str, str]:
    """
    Generate a flowchart of the core process using flowchart TD syntax.

    Shows the main user journey from start to finish, including decision points
    (diamond shapes) and alternative paths. TD = top-down direction.
    Max 20 nodes for readability.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate a Mermaid.js flowchart of the core system process.
Return ONLY raw Mermaid code (no fences).

Format:
flowchart TD
    A([Start]) --> B[Step]
    B --> C{{Decision?}}
    C -->|Yes| D[Continue]
    C -->|No| E[Alternative]
    D --> F([End])

Show the core user journey. Max 20 nodes. Double braces {{ }} for decision diamonds."""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    return "Core Process Flowchart", _clean_mermaid(r.content)


async def _gen_er_diagram(reqs: dict, llm) -> tuple[str, str]:
    """
    Generate an Entity Relationship (ER) Diagram.

    Shows database entities, their attributes (columns), and relationships
    (one-to-many, many-to-many). Extracted from user_roles and business entities
    implied by the functional requirements.

    The `||--o{` syntax means "one (||) to zero-or-many (o{)".
    PK = Primary Key, FK = Foreign Key.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate a Mermaid.js ER Diagram.
Return ONLY raw Mermaid code (no fences).

Format:
erDiagram
    USER {{
        uuid id PK
        string email
        string name
    }}
    ORDER {{
        uuid id PK
        uuid user_id FK
        decimal total
    }}
    USER ||--o{{ ORDER : places

Extract entities from requirements. Include PK, FK, and key fields. Show all relationships.
Note: use {{ and }} for entity attribute blocks in Mermaid erDiagram."""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    return "Entity Relationship Diagram", _clean_mermaid(r.content)


async def _gen_sequence(reqs: dict, llm) -> tuple[str, str]:
    """
    Generate a Sequence Diagram for the most important user flow.

    Shows interactions OVER TIME between components: User, Frontend, API, Database.
    ->>  = synchronous message (solid arrow)
    -->> = response (dashed arrow)
    Shows at least 8 steps including error handling paths.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate a Mermaid.js Sequence Diagram for the most important user flow.
Return ONLY raw Mermaid code (no fences).

Format:
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as Backend API
    participant DB as Database
    U->>FE: Action
    FE->>API: POST /endpoint
    API->>DB: Query
    DB-->>API: Result
    API-->>FE: Response
    FE-->>U: Display result

Pick the most important flow (login, main transaction, etc.). At least 8 steps."""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    return "Key User Flow Sequence Diagram", _clean_mermaid(r.content)


async def _gen_class_diagram(reqs: dict, llm) -> tuple[str, str]:
    """
    Generate a Class Diagram of the core domain model.

    Shows classes (domain objects), their attributes and methods,
    and relationships (inheritance, composition, association).
    Max 10 classes for readability.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate a Mermaid.js Class Diagram of the core domain model.
Return ONLY raw Mermaid code (no fences).

Format:
classDiagram
    class User {{
        +UUID id
        +String email
        +login() bool
    }}
    class Order {{
        +UUID id
        +Decimal total
        +place() void
    }}
    User "1" --> "*" Order : places

Note: use {{ and }} for class body blocks. Max 10 classes."""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    return "Domain Class Diagram", _clean_mermaid(r.content)


async def _gen_architecture(reqs: dict, llm) -> tuple[str, str]:
    """
    Generate a System Architecture Diagram showing all system layers.

    Uses Mermaid graph TB (top-bottom) with subgraphs for layers:
    Client Layer, API/Backend Layer, Data Layer, External Services.
    Reflects the actual tech stack implied by the requirements.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate a Mermaid.js System Architecture Diagram.
Return ONLY raw Mermaid code (no fences).

Format:
graph TB
    subgraph Client["Client Layer"]
        WEB[Web Browser]
    end
    subgraph API["API Layer"]
        GW[API Gateway]
        SVC[Backend Service]
    end
    subgraph Data["Data Layer"]
        DB[(PostgreSQL)]
        CACHE[(Redis)]
    end
    WEB -->|HTTPS| GW
    GW --> SVC
    SVC --> DB

Show all layers: Client, API/Backend, Data stores, External services."""),
        ("human", "Requirements:\n{reqs}"),
    ])
    r = await ainvoke_with_retry(prompt | llm, {"reqs": json.dumps(reqs, indent=2)})
    return "System Architecture Diagram", _clean_mermaid(r.content)


# ── DISPATCH TABLE ─────────────────────────────────────────────────────────────
# Maps DiagramType enum values to generator functions.
# generate_diagrams() iterates over this dict.
_DIAGRAM_GENERATORS = {
    DiagramType.use_case:      _gen_use_case,
    DiagramType.flowchart:     _gen_flowchart,
    DiagramType.er_diagram:    _gen_er_diagram,
    DiagramType.sequence:      _gen_sequence,
    DiagramType.class_diagram: _gen_class_diagram,
    DiagramType.architecture:  _gen_architecture,
}


def _clean_mermaid(text: str) -> str:
    """
    Remove markdown code fences from LLM output.

    WHY: Despite instructions saying "return only raw Mermaid code",
    GPT-4o often wraps output in ```mermaid...``` or just ```...```.
    This function strips those fences so the stored source_code is pure
    Mermaid syntax that the browser's mermaid.render() can accept directly.

    Algorithm:
      If text starts with ```, split on newlines.
      Remove the first line (the opening fence + optional "mermaid" label).
      Find the last closing ``` and remove it.
      Join the remaining lines.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Walk backwards to find the last closing ```
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        # lines[0] = "```mermaid" or "```" → skip it
        # lines[end] = closing "```" → stop before it
        text = "\n".join(lines[1:end])
    return text.strip()