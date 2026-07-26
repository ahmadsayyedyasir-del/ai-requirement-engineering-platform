"""
schemas/diagram.py — Pydantic schemas for diagram generation and response.

WHY THIS FILE EXISTS:
  Diagrams are simpler than documents — there's no versioning (regeneration
  overwrites the source_code in-place). So we only need two schemas:
    GenerateDiagramsRequest → trigger generation (optional type filter)
    DiagramOut              → return the Mermaid.js source code + metadata
"""

import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.diagram import DiagramType, DiagramFormat


class GenerateDiagramsRequest(BaseModel):
    """
    Optional request body for POST /diagrams/generate.

    diagram_types: Specific diagram types to generate.
    If None (omitted), all 6 types are generated.

    Example: {"diagram_types": ["er_diagram"]} regenerates only the ER diagram.
    Useful when requirements changed a lot and only one diagram needs updating.
    """
    diagram_types: list[DiagramType] | None = None  # None = generate all 6 types

    # If True, ignores diagram_types and instead regenerates only the diagram
    # types that failed on the last run (read from Project.generation_errors).
    retry_failed_only: bool = False


class DiagramOut(BaseModel):
    """
    Response schema for all diagram endpoints.

    THE MOST IMPORTANT FIELD: source_code
      This is the raw Mermaid.js text that the frontend renders into an SVG.
      Example value (ER diagram):
        'erDiagram\n  USER {\n    uuid id PK\n    string email\n  }\n  ...'

      The frontend does:
        mermaid.render('diagram-id', source_code)
        → returns { svg: "<svg>...</svg>" }
        → inject into DOM

    WHY STORE FORMAT TOO?
      diagram_format records whether the source is Mermaid or PlantUML.
      Currently always "mermaid", but if we add PlantUML support in the future,
      the frontend will know which renderer to use without code changes.
    """
    id: uuid.UUID
    project_id: uuid.UUID
    diagram_type: DiagramType         # use_case | flowchart | er_diagram | ...
    diagram_format: DiagramFormat     # mermaid (always currently)
    title: str                        # e.g., "Entity Relationship Diagram"
    source_code: str                  # The raw Mermaid.js text to pass to mermaid.render()
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}