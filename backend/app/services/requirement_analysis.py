"""
services/requirement_analysis.py — Phase 3: The LangGraph AI Analysis Pipeline.

THIS IS THE CORE AI ENGINE OF THE ENTIRE PLATFORM.

WHAT IT DOES:
  Takes raw business text (typed descriptions, parsed PDFs, meeting transcripts)
  and extracts structured, categorized, prioritized software requirements.

HOW IT WORKS (LangGraph pipeline — 5 nodes):
  ┌───────────────────────────────────────────────────────────────────────────┐
  │  node_load_inputs  →  node_rag_context  →  node_extract_requirements     │
  │       ↓                                          ↓                       │
  │  Load all raw          Query ChromaDB       GPT-4o generates             │
  │  text from DB          for SE knowledge     structured JSON              │
  │                        base context         with all 8 requirement       │
  │                                             categories                   │
  │                              ↓                                           │
  │  node_validate_output  →  node_persist                                   │
  │       ↓                       ↓                                          │
  │  Parse JSON,             Save to PostgreSQL                              │
  │  assign FR-001 IDs,      Index in ChromaDB                              │
  │  validate priorities     Update project status                           │
  └───────────────────────────────────────────────────────────────────────────┘

WHAT IS LANGGRAPH?
  LangGraph is a library for building stateful, multi-step AI pipelines as
  directed graphs. Each "node" is a Python function that receives state,
  does work, and returns updated state. Edges define execution order.

  vs. a simple LangChain chain (prompt | llm | parser):
    A chain is linear and can't handle branching or complex state.
    A LangGraph graph can: branch, loop, maintain state across steps,
    and handle errors at specific nodes.

STATE DESIGN (AnalysisState):
  The TypedDict defines what information flows through all 5 nodes.
  Each node receives the full state dict, modifies its relevant fields, and returns it.
  This makes the pipeline easy to debug — you can inspect state at any step.

ENTRY POINT: run_requirement_analysis()
  Called by the requirements endpoint as a background task.
"""

import json
import logging
import uuid
from typing import TypedDict, Optional

# ChatPromptTemplate — builds structured prompt templates with system/human messages
from langchain_core.prompts import ChatPromptTemplate

# StateGraph — the LangGraph graph builder
# END — a special node that marks the final state
from langgraph.graph import StateGraph, END

from sqlalchemy import select

# We open our OWN sessions here (not via get_db) because this runs in background tasks
from app.core.database import AsyncSessionLocal

from app.models.project import Project, ProjectStatus
from app.models.requirement import Requirement, RequirementCategory, RequirementPriority
from app.models.requirement_input import RequirementInput
from app.services.llm_client import get_llm, ainvoke_with_retry
from app.services.rag_service import search_knowledge_base, index_project_requirements

logger = logging.getLogger("reqeng.analysis")


# ── PIPELINE STATE ─────────────────────────────────────────────────────────────

class AnalysisState(TypedDict):
    """
    The shared state dict that flows through all 5 pipeline nodes.

    TypedDict makes Python understand the shape of this dict for type checking.
    Each field starts empty/None and gets populated as the pipeline progresses:

      project_id          → set by the caller, never changes
      input_ids           → set by the caller (or None = use all)
      raw_texts           → populated by node_load_inputs
      rag_context         → populated by node_rag_context
      raw_llm_output      → populated by node_extract_requirements
      parsed_requirements → populated by node_validate_output
      error               → set by any node if something goes wrong
    """
    project_id: str                    # UUID string of the project being analyzed
    input_ids: Optional[list[str]]     # Specific input IDs, or None = use all
    raw_texts: list[str]               # All extracted text content from inputs
    rag_context: str                   # Retrieved SE knowledge base context
    raw_llm_output: str                # Raw JSON string from GPT-4o
    parsed_requirements: list[dict]    # Validated, structured requirements
    error: Optional[str]               # Error message if pipeline fails


# ── NODE 1: LOAD INPUTS ────────────────────────────────────────────────────────

async def node_load_inputs(state: AnalysisState) -> AnalysisState:
    """
    PIPELINE NODE 1: Fetch all raw text content from the project's inputs.

    WHAT IT DOES:
      - Queries RequirementInput rows for this project
      - If input_ids were specified, only fetches those specific inputs
      - Calls get_content() on each input to get the text
        (prefers extracted_text for file uploads, falls back to raw_text)
      - Filters out empty inputs (inputs that haven't been processed yet)

    WHY FILTER EMPTY TEXTS?
      An uploaded PDF might still be processing (is_processed=False). We skip
      those rather than sending empty strings to GPT-4o.

    RESULT: state["raw_texts"] = list of text strings, one per input
    """
    async with AsyncSessionLocal() as db:
        # Base query: all inputs for this project
        query = select(RequirementInput).where(
            RequirementInput.project_id == uuid.UUID(state["project_id"])
        )

        # If specific input IDs were provided, filter to just those
        if state.get("input_ids"):
            ids = [uuid.UUID(i) for i in state["input_ids"]]
            query = query.where(RequirementInput.id.in_(ids))

        result = await db.execute(query)
        inputs = result.scalars().all()

    # Get the text from each input, skip those with no content
    texts = [inp.get_content() for inp in inputs if inp.get_content().strip()]

    state["raw_texts"] = texts
    logger.info(f"Loaded {len(texts)} input texts for project {state['project_id']}")
    return state


# ── NODE 2: RAG CONTEXT RETRIEVAL ─────────────────────────────────────────────

async def node_rag_context(state: AnalysisState) -> AnalysisState:
    """
    PIPELINE NODE 2: Retrieve relevant SE knowledge from ChromaDB for RAG.

    WHAT IT DOES:
      - Combines the first ~1000 chars of all input text as the search query
      - Queries ChromaDB's knowledge base for the 6 most semantically similar documents
      - Formats the results as "[KB] <document content>" strings
      - Stores the combined context in state["rag_context"]

    WHY ONLY 1000 CHARS FOR THE QUERY?
      The embedding model converts text to vectors. More text = more tokens = more cost.
      The first 1000 characters are usually enough to determine the project domain
      (fintech, healthcare, ecommerce) and find the relevant KB documents.

    RESULT: state["rag_context"] = multiline string with 6 knowledge base entries
    This gets injected into the GPT-4o prompt in the next node.
    """
    # Use the beginning of all combined input text as the search query
    combined = " ".join(state["raw_texts"])[:1000]

    # k=6 means we retrieve 6 knowledge documents
    # More = better context but more prompt tokens and cost
    docs = await search_knowledge_base(combined, k=6)

    # Format each document with a "[KB]" prefix so GPT-4o recognizes them as reference material
    context = "\n\n".join([f"[KB] {d.page_content}" for d in docs])
    state["rag_context"] = context
    return state


# ── NODE 3: LLM REQUIREMENT EXTRACTION ────────────────────────────────────────

async def node_extract_requirements(state: AnalysisState) -> AnalysisState:
    """
    PIPELINE NODE 3: The main AI step — GPT-4o extracts structured requirements.

    WHAT IT DOES:
      - Builds a prompt with:
          SYSTEM: Instructions for the AI (role, output format, rules)
          SYSTEM: The RAG context from ChromaDB (SE knowledge base)
          HUMAN:  The actual business input text to analyze
      - Sends the prompt to GPT-4o
      - Stores the raw JSON response string in state["raw_llm_output"]

    WHY TEMPERATURE=0.1?
      We need consistent, structured JSON output every time.
      A higher temperature might generate creative field names or inconsistent
      priority values that would break JSON parsing in the next node.

    WHY 12000 CHAR LIMIT ON INPUT?
      GPT-4o has a token limit (~128k tokens for gpt-4o). We truncate at
      12000 characters (~3000 tokens) for the input text portion, leaving
      plenty of room for the system prompt, RAG context, and the response.
      Most requirement documents are much shorter than 12000 chars.

    RESULT: state["raw_llm_output"] = raw JSON string from GPT-4o
    """
    llm = get_llm(temperature=0.1)  # Very low temp for consistent structured JSON

    # Combine all input texts into one block, separated by "---"
    combined_input = "\n\n---\n\n".join(state["raw_texts"])

    # Build the prompt using LangChain's ChatPromptTemplate.
    # from_messages() takes a list of (role, content) tuples.
    # {rag_context} and {input_text} are template variables filled in .ainvoke()
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a senior software requirements analyst at a software house.
Analyze the business input and extract ALL software requirements.

Reference knowledge from our knowledge base:
{rag_context}

Return ONLY a valid JSON object with this EXACT structure (no markdown, no explanation):
{{
  "functional_requirements": [
    {{"title": "Short title max 10 words", "description": "Detailed description", "priority": "must_have|should_have|could_have|wont_have"}}
  ],
  "non_functional_requirements": [
    {{"title": "...", "description": "...", "priority": "must_have|should_have|could_have|wont_have"}}
  ],
  "user_roles": [
    {{"title": "...", "description": "What this role does in the system"}}
  ],
  "business_rules": [
    {{"title": "...", "description": "A business rule or policy the system must follow"}}
  ],
  "constraints": [
    {{"title": "...", "description": "A hard technical or regulatory constraint"}}
  ],
  "assumptions": [
    {{"title": "...", "description": "Something assumed to be true but should be validated"}}
  ],
  "risks": [
    {{"title": "...", "description": "...", "impact": "high|medium|low", "likelihood": "high|medium|low"}}
  ],
  "dependencies": [
    {{"title": "...", "description": "An external system or service this project depends on"}}
  ]
}}

RULES:
- Extract ALL implied requirements, not just explicitly stated ones
- Be specific and actionable — avoid vague statements like "the system shall be fast"
- Each requirement needs a clear title (≤10 words) and a detailed description
- Use MoSCoW priorities; default to must_have if unclear
- Identify at least 3 distinct user roles
- Identify at least 5 functional requirements
"""
        ),
        (
            "human",
            "Business Input to analyze:\n\n{input_text}"
        ),
    ])

    # Build the chain: prompt → llm → raw response
    chain = prompt | llm

    # Call the chain asynchronously with our variables.
    # ainvoke_with_retry() retries on rate-limit/transient errors with backoff
    # instead of letting a single hiccup fail the entire analysis run.
    response = await ainvoke_with_retry(chain, {
        "rag_context": state["rag_context"],
        "input_text": combined_input[:12000],  # Token safety — truncate if very long
    })

    # Store the raw text response for the validation node to parse
    state["raw_llm_output"] = response.content
    return state


# ── NODE 4: VALIDATE AND STRUCTURE OUTPUT ─────────────────────────────────────

def node_validate_output(state: AnalysisState) -> AnalysisState:
    """
    PIPELINE NODE 4: Parse the LLM's JSON response and assign requirement IDs.

    NOTE: This is a SYNCHRONOUS node (not async). LangGraph allows mixing
    sync and async nodes. JSON parsing doesn't need async.

    WHAT IT DOES:
      1. Strips markdown code fences if GPT-4o wrapped the JSON in ```json...```
      2. Parses the JSON string into a Python dict
      3. Maps each JSON key to its RequirementCategory enum value
      4. Assigns human-readable IDs: FR-001, NFR-003, BR-007, RSK-002, etc.
      5. Validates priority values (resets to "must_have" if invalid)
      6. Builds a list of requirement dicts ready for DB insertion

    WHY STRIP MARKDOWN FENCES?
      Despite instructions saying "ONLY JSON", GPT-4o sometimes wraps output in:
          ```json
          { ... }
          ```
      We strip these fences before parsing to avoid json.JSONDecodeError.

    ID ASSIGNMENT:
      Each category has a counter starting at 0.
      FR-001 = functional, 1st requirement
      NFR-003 = non_functional, 3rd requirement
      RSK-001 = risk, 1st requirement
      Format: f"{prefix}-{counter:03d}" → always 3 digits (001, 002, ..., 099, 100)

    RESULT: state["parsed_requirements"] = list of validated requirement dicts
    """
    try:
        # Step 1: Strip markdown code fences if present
        text = state["raw_llm_output"].strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            text = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

        # Step 2: Parse the cleaned text as JSON
        data = json.loads(text)

        # Step 3: Define the mapping from JSON key → RequirementCategory enum value
        category_map = {
            "functional_requirements":     RequirementCategory.functional,
            "non_functional_requirements": RequirementCategory.non_functional,
            "user_roles":                  RequirementCategory.user_role,
            "business_rules":              RequirementCategory.business_rule,
            "constraints":                 RequirementCategory.constraint,
            "assumptions":                 RequirementCategory.assumption,
            "risks":                       RequirementCategory.risk,
            "dependencies":                RequirementCategory.dependency,
        }

        # Step 4: Define the 2-3 letter prefix for each category's IDs
        prefix_map = {
            RequirementCategory.functional:    "FR",   # Functional Requirement
            RequirementCategory.non_functional:"NFR",  # Non-Functional Requirement
            RequirementCategory.user_role:     "UR",   # User Role
            RequirementCategory.business_rule: "BR",   # Business Rule
            RequirementCategory.constraint:    "CON",  # Constraint
            RequirementCategory.assumption:    "ASM",  # Assumption
            RequirementCategory.risk:          "RSK",  # Risk
            RequirementCategory.dependency:    "DEP",  # Dependency
        }

        # Per-category counters for sequential IDs within each category
        counters = {cat: 0 for cat in RequirementCategory}

        requirements = []
        for key, category in category_map.items():
            # Iterate over each item in this category from the LLM output
            for item in data.get(key, []):
                counters[category] += 1
                # Build the human-readable ID: "FR-001", "NFR-003", etc.
                req_id = f"{prefix_map[category]}-{counters[category]:03d}"

                # Validate the priority value — reset to "must_have" if LLM gave an invalid value
                priority = item.get("priority", "must_have")
                if priority not in [p.value for p in RequirementPriority]:
                    priority = "must_have"  # Safe fallback

                requirements.append({
                    "category":    category.value,
                    "priority":    priority,
                    "req_id":      req_id,
                    "title":       item.get("title", "Untitled")[:512],   # DB column limit
                    "description": item.get("description", ""),
                    # Everything except title/description/priority goes into extra_metadata
                    # (e.g., risk impact/likelihood from the risks array).
                    # Named "extra_metadata" because SQLAlchemy reserves "metadata" on Base models.
                    "extra_metadata": {
                        k: v for k, v in item.items()
                        if k not in ("title", "description", "priority")
                    },
                })

        state["parsed_requirements"] = requirements
        logger.info(f"Validated {len(requirements)} requirements")

    except Exception as e:
        # If parsing fails entirely, store the error — node_persist will handle it
        state["error"] = f"Output validation failed: {str(e)}"
        logger.error(f"Requirement validation error: {e}")

    return state


# ── NODE 5: PERSIST TO DATABASE ────────────────────────────────────────────────

async def node_persist(state: AnalysisState) -> AnalysisState:
    """
    PIPELINE NODE 5: Save extracted requirements to PostgreSQL.

    WHAT IT DOES:
      1. If there was an error in a previous node, reverts project status to "draft"
      2. Deletes all existing requirements for this project (re-analysis replaces them)
      3. Inserts all new requirements from state["parsed_requirements"]
      4. Updates the project status from "analyzing" → "analyzed"
      5. Commits the transaction
      6. Indexes the new requirements in ChromaDB for future RAG queries

    WHY DELETE FIRST?
      When an analyst re-runs analysis (maybe they added more input), we want
      fresh results — not a mix of old and new requirements. Deleting first
      ensures the new set is authoritative.

      NOTE: In production you might want to diff old vs new and only update
      changed requirements (preserving manual edits). That's a future enhancement.

    RESULT:
      - Requirements saved to PostgreSQL
      - Project status = "analyzed"
      - Requirements indexed in ChromaDB
    """
    # If a previous node set an error, don't persist — revert project to draft
    if state.get("error"):
        await _set_project_status(state["project_id"], ProjectStatus.draft)
        return state

    async with AsyncSessionLocal() as db:
        project_id = uuid.UUID(state["project_id"])

        # Delete all existing requirements for a clean re-analysis
        existing = await db.execute(
            select(Requirement).where(Requirement.project_id == project_id)
        )
        for r in existing.scalars().all():
            await db.delete(r)

        # Insert all newly extracted requirements
        for req_data in state["parsed_requirements"]:
            req = Requirement(
                project_id=project_id,
                category=RequirementCategory(req_data["category"]),
                priority=RequirementPriority(req_data["priority"]),
                req_id=req_data["req_id"],
                title=req_data["title"],
                description=req_data["description"],
                extra_metadata=req_data.get("extra_metadata", {}),
                version=1,          # Version 1 = first AI-generated version
                is_active=True,     # Active by default
            )
            db.add(req)

        # Update project status to "analyzed" so the UI knows analysis is complete
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project:
            project.status = ProjectStatus.analyzed

        await db.commit()  # Save everything to PostgreSQL atomically

    # Also index requirements in ChromaDB for future RAG-based analysis
    await index_project_requirements(state["project_id"], state["parsed_requirements"])

    logger.info(
        f"Persisted {len(state['parsed_requirements'])} requirements "
        f"for project {state['project_id']}"
    )
    return state


async def _set_project_status(project_id: str, status: ProjectStatus) -> None:
    """
    Helper to update a project's status outside of the main pipeline flow.
    Used when the pipeline fails and we need to revert to "draft".
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Project).where(Project.id == uuid.UUID(project_id))
        )
        project = result.scalar_one_or_none()
        if project:
            project.status = status
        await db.commit()


# ── BUILD THE LANGGRAPH ────────────────────────────────────────────────────────

def build_analysis_graph() -> StateGraph:
    """
    Assemble the 5 nodes into a LangGraph directed graph and compile it.

    The graph looks like a linear pipeline:
      load_inputs → rag_context → extract_requirements → validate_output → persist → END

    WHY USE A GRAPH AT ALL (vs just calling functions in sequence)?
      LangGraph manages state passing automatically between nodes.
      In the future, we could add conditional edges (e.g., if extraction fails,
      go to an error handler node instead of persist). The graph structure
      makes this easy to add without refactoring all the node functions.
    """
    graph = StateGraph(AnalysisState)

    # Node names prefixed with "step_" to avoid clashing with state field names.
    # LangGraph now raises ValueError if a node name matches a TypedDict key.
    # Our state has fields: raw_texts, rag_context, raw_llm_output, etc.
    # Node names like "rag_context" would clash with the state field "rag_context".
    graph.add_node("step_load_inputs",          node_load_inputs)
    graph.add_node("step_rag_context",          node_rag_context)
    graph.add_node("step_extract_requirements", node_extract_requirements)
    graph.add_node("step_validate_output",      node_validate_output)
    graph.add_node("step_persist",              node_persist)

    # Define execution order
    graph.set_entry_point("step_load_inputs")
    graph.add_edge("step_load_inputs",          "step_rag_context")
    graph.add_edge("step_rag_context",          "step_extract_requirements")
    graph.add_edge("step_extract_requirements", "step_validate_output")
    graph.add_edge("step_validate_output",      "step_persist")
    graph.add_edge("step_persist",              END)

    # compile() locks the graph structure and prepares it for execution
    return graph.compile()


# Singleton — build the graph once at module load time, reuse for every call
_analysis_graph = None


def _get_analysis_graph():
    """Return the compiled graph, creating it once on first call."""
    global _analysis_graph
    if _analysis_graph is None:
        _analysis_graph = build_analysis_graph()
    return _analysis_graph


# ── PUBLIC ENTRY POINT ─────────────────────────────────────────────────────────

async def run_requirement_analysis(
    project_id: uuid.UUID,
    input_ids: Optional[list[uuid.UUID]] = None,
) -> None:
    """
    Public function called by the API background task to run the full pipeline.

    This is what requirements.py calls:
        background_tasks.add_task(run_requirement_analysis, project_id=..., input_ids=...)

    FLOW:
      1. Build initial state with the project_id and optional input filter
      2. Get the compiled graph
      3. Invoke the graph asynchronously (runs all 5 nodes in sequence)
      4. If the graph itself throws an unexpected exception, revert project to draft

    Args:
        project_id: The UUID of the project to analyze
        input_ids:  Optional list of specific input UUIDs to analyze.
                    None = analyze all inputs for the project.
    """
    logger.info(f"Starting requirement analysis for project {project_id}")
    graph = _get_analysis_graph()

    # Initial state — all fields start empty, node functions populate them
    initial_state: AnalysisState = {
        "project_id": str(project_id),
        "input_ids": [str(i) for i in input_ids] if input_ids else None,
        "raw_texts": [],
        "rag_context": "",
        "raw_llm_output": "",
        "parsed_requirements": [],
        "error": None,
    }

    try:
        # Execute the graph — this runs all 5 nodes in the defined order
        await graph.ainvoke(initial_state)
    except Exception as e:
        # Catch any unhandled exception from the graph itself
        logger.error(f"Analysis pipeline failed for project {project_id}: {e}")
        # Revert project status so the user can try again
        await _set_project_status(str(project_id), ProjectStatus.draft)