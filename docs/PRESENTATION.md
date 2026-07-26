# AI Requirement Engineering Platform
## Technical Presentation — Ezitech AI-017

---

### Slide 1: The Problem

Software projects fail because of:
- Incomplete requirements (scope creep, missed features)
- Inconsistent documentation (SRS written differently every time)
- Manual process that takes 2–4 weeks per project
- No traceability from business idea → technical spec → test

**Result:** 70% of software failures are attributed to poor requirements engineering.

---

### Slide 2: Our Solution

A fully automated AI platform that takes a business idea (text, PDF, DOCX, or meeting transcript) and outputs a complete, structured software engineering document package in minutes, not weeks.

**Input:** Any raw business description
**Output:** SRS + BRD + User Stories + Acceptance Criteria + Sprint Plans + UML Diagrams + AI Review

---

### Slide 3: System Architecture

```
User Input → FastAPI → LangGraph Pipeline → GPT-4o (with RAG)
                  ↓
           PostgreSQL (structured)
                  ↓
    Document Generator → SRS, BRD, User Stories, Use Cases
    Planning Generator → Roadmap, Sprints, Cost, Team, Risk
    Diagram Generator  → 6 Mermaid.js UML diagrams
    Review Engine      → Quality score + issue list
```

All outputs are stored as structured JSON in PostgreSQL, not raw AI text.

---

### Slide 4: Phase-by-Phase Breakdown

| Phase | What it does | Key tech |
|---|---|---|
| 1 | Foundation: API, DB schema, Docker | FastAPI, PostgreSQL, Docker |
| 2 | Input collection: text, PDF, DOCX, transcript | pdfplumber, python-docx |
| 3 | AI analysis: extract 8 requirement categories | LangGraph, ChromaDB RAG, GPT-4o |
| 4 | Doc generation: SRS, BRD, User Stories, etc. | LangChain chains, structured JSON |
| 5 | Software planning: roadmap, cost, team, risk | LLM + formula-based estimation |
| 6 | Diagram generation: 6 Mermaid.js diagrams | LLM → Mermaid syntax → browser render |
| 7 | AI review: quality score + flagged issues | Second-pass LLM reviewer |
| 8 | API + collaboration: versioning, multi-user | FastAPI + JWT + document versioning |

---

### Slide 5: The LangGraph AI Pipeline

```
node_load_inputs
      ↓
node_rag_context    ← ChromaDB: retrieve SE best practices
      ↓
node_extract_requirements  ← GPT-4o: structured JSON output
      ↓
node_validate_output  ← Parse JSON, assign FR-001/NFR-003 IDs, validate priorities
      ↓
node_persist  ← Save to PostgreSQL + index embeddings in ChromaDB
```

**Why LangGraph?** Stateful execution graph means each step has typed input/output. Failures are isolated per node. The graph is testable and extensible (add nodes for custom logic without rewriting the whole pipeline).

---

### Slide 6: RAG Strategy

ChromaDB stores two collections:
1. **knowledge_base** — seeded with 10 software engineering best practice documents (SRS structure, MoSCoW methodology, sprint velocity formulas, etc.)
2. **project_embeddings** — indexed requirements from past analyses for future similarity lookups

When analyzing a new project, the pipeline queries the knowledge base for relevant context **before** prompting the LLM, improving structure and completeness of output.

---

### Slide 7: Output Quality

For a food delivery app input (~150 words), the system generates:
- 30–40 structured requirements (FRs, NFRs, roles, rules, risks)
- 8 documents (SRS, BRD, User Stories, Use Cases, AC, Glossary, Functional Spec, NFR Spec)
- 8 planning artifacts (roadmap, 12-sprint plan, cost estimate, team recommendation, risk table)
- 6 Mermaid diagrams (Use Case, ER, Sequence, Class, Flowchart, Architecture)
- 1 AI review report with quality score and flagged issues

Total: ~50 structured artifacts from a paragraph of input.

---

### Slide 8: Bonus Features

1. **MoSCoW AI Prioritizer** — Re-evaluates all requirements with justification. Identifies what must be in the MVP vs. what can wait. Applies to all must_have/should_have/could_have/won't_have assignments.

2. **Version Diff Viewer** — Every document regeneration creates a new version. The diff API compares any two versions with line-level unified diff output, viewable in the UI.

---

### Slide 9: Key Technical Decisions

| Decision | Choice | Why |
|---|---|---|
| Async DB | SQLAlchemy async + asyncpg | Non-blocking I/O for long AI pipeline tasks |
| JWT auth | PyJWT + bcrypt | Stateless, secure, no session storage needed |
| Document storage | JSON in PostgreSQL | Queryable, no second document DB needed |
| Diagram format | Mermaid.js | Renders in browser, version-controllable as text |
| LLM response format | Structured JSON prompt | Avoids hallucination drift, directly maps to DB schema |

---

### Slide 10: Deployment & Scaling

**Current:** Single `docker compose up` command starts all 6 services.

**Production path:**
- Move Celery workers to Kubernetes pods (scale based on queue depth)
- Add connection pooling via PgBouncer
- Move file storage to S3
- Use Azure OpenAI or AWS Bedrock for enterprise data isolation
- Add Elasticsearch for knowledge base at scale (>100k documents)

---

### Demo Script

1. Open http://localhost:3000
2. Register → Log in
3. Create project: "Online Food Delivery App"
4. Paste business description (3 paragraphs)
5. Click "Analyze Requirements" — show structured requirements appearing
6. Click "Generate Everything" — show all tabs populating
7. Show Documents tab → SRS rendered in markdown
8. Show Diagrams tab → Live Mermaid ER and Architecture diagrams
9. Show Planning tab → Cost estimation table with totals
10. Run MoSCoW AI → show priority changes with reasoning
11. Run Review → show quality score dial + issue list

**Total demo time: ~10 minutes**
