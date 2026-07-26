# AI Architecture Diagram — End-to-End Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        AI REQUIREMENT ENGINEERING PLATFORM                       │
│                                Ezitech | AI-017                                  │
└──────────────────────────────────────────────────────────────────────────────────┘

INPUT LAYER
─────────────────────────────────────────────────────────────────────────────────
  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
  │  Text Input  │  │  PDF Upload  │  │ DOCX Upload  │  │ Meeting Transcript   │
  │  (raw idea)  │  │  (pdfplumber)│  │ (python-docx)│  │  (plain text)        │
  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘
         │                  │                  │                      │
         └──────────────────┴──────────────────┴──────────────────────┘
                                        │
                                        ▼
                          PostgreSQL: requirement_inputs table
                          (stores raw text + file path + extracted text)


PHASE 3 — LANGGRAPH ANALYSIS PIPELINE
─────────────────────────────────────────────────────────────────────────────────

  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    LangGraph StateGraph                                  │
  │                                                                          │
  │  ┌──────────────┐    ┌───────────────┐    ┌──────────────────────────┐  │
  │  │ node_load_   │    │ node_rag_     │    │ node_extract_            │  │
  │  │ inputs       │───►│ context       │───►│ requirements             │  │
  │  │              │    │               │    │                          │  │
  │  │ Load raw     │    │ Query ChromaDB│    │ GPT-4o generates         │  │
  │  │ texts from   │    │ for top-k SE  │    │ structured JSON with:    │  │
  │  │ DB           │    │ best practices│    │ - functional_requirements │  │
  │  └──────────────┘    └───────────────┘    │ - non_functional_reqs    │  │
  │                              ▲            │ - user_roles             │  │
  │                              │            │ - business_rules         │  │
  │              ┌───────────────┘            │ - constraints            │  │
  │              │                            │ - assumptions            │  │
  │         ChromaDB                          │ - risks                  │  │
  │         knowledge_base                    │ - dependencies           │  │
  │         (SE patterns,                     └────────────┬─────────────┘  │
  │          templates,                                    │                │
  │          methodologies)                                ▼                │
  │                                        ┌──────────────────────────┐    │
  │                                        │ node_validate_output     │    │
  │                                        │                          │    │
  │                                        │ Parse JSON, assign IDs:  │    │
  │                                        │ FR-001, NFR-003, BR-002  │    │
  │                                        │ Validate priorities      │    │
  │                                        └────────────┬─────────────┘    │
  │                                                     │                  │
  │                                                     ▼                  │
  │                                        ┌──────────────────────────┐    │
  │                                        │ node_persist             │    │
  │                                        │                          │    │
  │                                        │ Save to PostgreSQL       │    │
  │                                        │ Index in ChromaDB        │    │
  │                                        │ Update project status    │    │
  │                                        └──────────────────────────┘    │
  └─────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                          PostgreSQL: requirements table
                          (30-40 structured requirements per project)


PHASE 4-7 — DOWNSTREAM GENERATORS
─────────────────────────────────────────────────────────────────────────────────

  Structured Requirements
         │
         ├──► DOCUMENT GENERATOR (Phase 4)
         │    GPT-4o → JSON → Markdown
         │    ┌─────────────────────────────────────┐
         │    │ SRS │ BRD │ User Stories │ Use Cases │
         │    │ Acceptance Criteria │ Glossary       │
         │    │ Functional Spec │ NFR Spec           │
         │    └─────────────────────────────────────┘
         │    Stored: documents + document_versions tables
         │    (full version history, markdown rendering)
         │
         ├──► PLANNING GENERATOR (Phase 5)
         │    GPT-4o → JSON → Markdown
         │    ┌───────────────────────────────────────────────┐
         │    │ Module Breakdown │ Roadmap │ Sprint Plan       │
         │    │ Team Composition │ Tech Stack │ Timeline       │
         │    │ Cost Estimation │ Risk Assessment Table       │
         │    └───────────────────────────────────────────────┘
         │    Stored: planning_artifacts table
         │
         ├──► DIAGRAM GENERATOR (Phase 6)
         │    GPT-4o → Mermaid.js source code
         │    ┌─────────────────────────────────────────┐
         │    │ Use Case │ Flowchart │ ER Diagram        │
         │    │ Sequence │ Class Diagram │ Architecture  │
         │    └─────────────────────────────────────────┘
         │    Stored: diagrams table
         │    Rendered: Mermaid.js in browser (no server render)
         │
         └──► REVIEW ENGINE (Phase 7)
              GPT-4o (second pass, low temperature)
              ┌─────────────────────────────────────────────────────┐
              │ Quality Score (0-100)                               │
              │ Issues: missing | conflict | duplicate | scope_gap  │
              │ Severity: high | medium | low                       │
              │ Suggestions per issue                               │
              │ Recommended actions                                 │
              └─────────────────────────────────────────────────────┘
              Stored: review_reports table


BONUS FEATURES
─────────────────────────────────────────────────────────────────────────────────

  MoSCoW AI Prioritizer
  ┌─────────────────────────────────────────────────────────────┐
  │ GPT-4o re-evaluates all requirements                        │
  │ Assigns must_have/should_have/could_have/wont_have          │
  │ Provides reasoning per requirement                          │
  │ Updates PostgreSQL + returns change summary                 │
  └─────────────────────────────────────────────────────────────┘

  Version Diff Viewer
  ┌─────────────────────────────────────────────────────────────┐
  │ Compares document_versions v1 vs v2                         │
  │ Python difflib unified diff                                 │
  │ Returns: added_lines, removed_lines, unified_diff string    │
  └─────────────────────────────────────────────────────────────┘
```
