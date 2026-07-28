"""
diagram.py â€” Stores AI-generated technical diagrams as Mermaid.js source code.

WHY THIS FILE EXISTS:
  Good software documentation always includes visual diagrams. This model stores
  the diagrams the AI generates for each project.

WHY STORE SOURCE CODE (NOT IMAGES)?
  Traditional diagram tools generate images (PNG, SVG). We take a different approach:
  we store the Mermaid.js TEXT SOURCE CODE.

  Benefits of storing source code:
    1. VERSION CONTROL: Text diffs between versions are meaningful
    2. EDITABLE: Users can copy the Mermaid code and modify it in any editor
    3. LIGHTWEIGHT: A 200-character text string vs a 50KB PNG
    4. RENDERLESS: The browser renders it into SVG using the Mermaid.js library â€”
       no server-side image generation needed
    5. PORTABLE: Mermaid is supported by GitHub, Notion, Confluence, GitLab, etc.

WHAT IS MERMAID.JS?
  Mermaid is a "diagram as code" language. You write text like:
      graph TD
          A[User] --> B[Login Page]
          B --> C{Valid credentials?}
          C -->|Yes| D[Dashboard]
          C -->|No| E[Error message]
  And the browser draws it as a flowchart automatically.

TABLE STRUCTURE:
  id               UUID        Primary key
  project_id       UUID        FK â†’ projects.id
  diagram_type     ENUM        use_case | flowchart | er_diagram | ...
  diagram_format   ENUM        mermaid | plantuml (we use mermaid)
  title            VARCHAR     Human-readable diagram name
  source_code      TEXT        The Mermaid.js source code
  render_path      VARCHAR     Optional path to a rendered SVG/PNG file
  created_at       TIMESTAMP
  updated_at       TIMESTAMP
"""

import uuid
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.core.database import Base
from app.models import TimestampMixin


class DiagramType(str, enum.Enum):
    """
    The six types of UML/technical diagrams generated for each project.

    use_case      â€” Shows ACTORS (users/systems) and the USE CASES (things they can do).
                    Answers: "Who uses this system and what can they do?"
                    Standard: UML Use Case Diagram

    flowchart     â€” Shows the step-by-step flow of the most important process.
                    Answers: "How does the core workflow actually work?"
                    Shows: decision points, branches, start/end states

    er_diagram    â€” Entity Relationship diagram of the database structure.
                    Answers: "What data does the system store and how is it related?"
                    Shows: tables, columns, primary keys, foreign keys, relationships

    sequence      â€” Shows how components interact over time for a specific scenario.
                    Answers: "What happens step-by-step when a user does X?"
                    Shows: Browser â†’ API â†’ Service â†’ Database â†’ back again

    class_diagram â€” Shows the object-oriented domain model (classes and relationships).
                    Answers: "How is the code structured? What are the main entities?"
                    Shows: classes, attributes, methods, inheritance, associations

    architecture  â€” High-level system architecture overview.
                    Answers: "What are the main components and how do they connect?"
                    Shows: Frontend, Backend, DB, Cache, external services
    """
    use_case = "use_case"
    flowchart = "flowchart"
    er_diagram = "er_diagram"
    sequence = "sequence"
    class_diagram = "class_diagram"
    architecture = "architecture"


class DiagramFormat(str, enum.Enum):
    """
    Which diagram syntax format is used in the source_code column.

    mermaid  â€” Mermaid.js syntax (what we use). Renders in browser with mermaid.js library.
    plantuml â€” PlantUML syntax (alternative). Requires server-side rendering.
               We chose Mermaid because it renders client-side (no extra server needed).
    """
    mermaid = "mermaid"
    plantuml = "plantuml"


class Diagram(Base, TimestampMixin):
    """
    ORM model for the `diagrams` table.

    Each row stores one diagram (one per type per project).
    If the diagram is regenerated, the source_code is updated in-place
    (unlike documents, which create new version rows).
    """

    __tablename__ = "diagrams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Which project this diagram belongs to
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # What kind of diagram this is (use_case, er_diagram, etc.)
    diagram_type: Mapped[DiagramType] = mapped_column(
        SAEnum(DiagramType), nullable=False, index=True
    )

    # Which format the source_code uses (almost always mermaid)
    diagram_format: Mapped[DiagramFormat] = mapped_column(
        SAEnum(DiagramFormat), default=DiagramFormat.mermaid, nullable=False
    )

    # Human-readable title shown in the UI
    # Example: "Entity Relationship Diagram", "System Architecture Diagram"
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # The actual Mermaid.js source code string.
    # This is what the browser's mermaid.render() function receives.
    # Example:
    #   erDiagram
    #       USER { uuid id PK; string email }
    #       ORDER { uuid id PK; uuid user_id FK }
    #       USER ||--o{ ORDER : places
    source_code: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional path to a pre-rendered SVG or PNG file.
    # Not currently used (rendering is done client-side), but reserved for
    # future export functionality.
    render_path: Mapped[str] = mapped_column(String(1024), nullable=True)

    # Relationship back to the parent project
    project: Mapped["Project"] = relationship("Project", back_populates="diagrams")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Diagram [{self.diagram_type}] project={self.project_id}>"
