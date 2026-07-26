# AI Requirement Engineering Platform
### Ezitech | AI-017

An end-to-end, AI-powered platform that automates the software requirement engineering lifecycle — from a raw business idea to a complete, structured documentation package including SRS, BRD, User Stories, UML diagrams, sprint plans, cost estimates, and AI-driven quality reviews.

---

## Architecture Overview

```
                         ┌─────────────────────────────────────────────┐
                         │           React + Vite Frontend              │
                         │  Dashboard → Project → Requirements → Docs  │
                         └─────────────────┬───────────────────────────┘
                                           │ HTTPS (REST API)
                         ┌─────────────────▼───────────────────────────┐
                         │          FastAPI (Python 3.12)               │
                         │  /api/v1/  — JWT auth, CRUD, async tasks     │
                         └────┬────────────┬──────────────┬────────────┘
                              │            │              │
               ┌──────────────▼──┐  ┌──────▼──────┐  ┌──▼──────────────┐
               │  PostgreSQL 16  │  │  Redis 7    │  │  ChromaDB       │
               │  (primary data) │  │  (cache +   │  │  (vector store  │
               │                 │  │  Celery)    │  │   for RAG)      │
               └─────────────────┘  └─────────────┘  └─────────────────┘
                                           │
                         ┌─────────────────▼───────────────────────────┐
                         │          LangGraph AI Pipeline               │
                         │  Input → RAG Context → LLM → Validate →    │
                         │  Persist (requirements, docs, diagrams)     │
                         └─────────────────────────────────────────────┘
```

### AI Pipeline Flow

```
Raw Input (text/PDF/DOCX/transcript)
        │
        ▼
[Phase 3] LangGraph Analysis Pipeline
  1. load_inputs    — fetch all raw text from DB
  2. rag_context    — retrieve relevant SE knowledge from ChromaDB
  3. extract_reqs   — LLM (GPT-4o) extracts structured JSON requirements
  4. validate_output — assign req_ids (FR-001, NFR-003...), validate priorities
  5. persist        — save to PostgreSQL + index in ChromaDB
        │
        ▼
Structured Requirements (PostgreSQL)
        │
        ├─► [Phase 4] Document Generator (SRS, BRD, User Stories, Use Cases...)
        ├─► [Phase 5] Planning Generator (Roadmap, Sprints, Cost, Team, Risk)
        ├─► [Phase 6] Diagram Generator (Mermaid.js Use Case, ER, Sequence...)
        └─► [Phase 7] AI Review Engine (quality score, issues, suggestions)
```

---

## Tech Stack

| Layer | Technology | Justification |
|---|---|---|
| Backend | Python 3.12, FastAPI | Async-native, excellent OpenAPI support |
| AI Orchestration | LangChain + LangGraph | Stateful AI pipelines, easy node composition |
| LLM | OpenAI GPT-4o | Best structured JSON output reliability |
| Vector Store / RAG | ChromaDB | Lightweight, Docker-friendly, Python-native |
| Database | PostgreSQL 16 | Full ACID, JSON columns, UUID support |
| Cache / Queue | Redis 7 | Celery broker + API response caching |
| Diagrams | Mermaid.js | Renders in browser, no server-side render needed |
| Frontend | React 18 + Vite | Fast HMR, lightweight, Mermaid integration |
| Containerization | Docker + Compose | One-command setup for all services |

---

## Prerequisites

- **Docker Desktop** 24+ (with Compose v2)
- **OpenAI API Key** (GPT-4o access required)

---

## Setup & Run

### 1. Clone and configure

```bash
git clone https://github.com/ezitech/ai-req-platform.git
cd ai-req-platform

# Create backend .env from template
cp backend/.env.example backend/.env
```

Edit `backend/.env` and set your OpenAI API key:
```
OPENAI_API_KEY=sk-your-key-here
```

### 2. Start all services

```bash
docker compose up --build
```

This starts:
- **PostgreSQL** on port `5432`
- **Redis** on port `6379`
- **ChromaDB** on port `8001`
- **FastAPI API** on port `8000`
- **Celery Worker** (background AI tasks)
- **React Frontend** on port `3000`

### 3. Open the platform

| Service | URL |
|---|---|
| Frontend UI | http://localhost:3000 |
| API Swagger Docs | http://localhost:8000/api/docs |
| API ReDoc | http://localhost:8000/api/redoc |
| Health Check | http://localhost:8000/health |

### 4. Register a user

Go to http://localhost:3000/register — create your analyst account.

---

## Local Development (without Docker)

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env           # fill in values
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                    # starts on http://localhost:5173
```

Requires PostgreSQL, Redis, and ChromaDB running locally or via Docker:
```bash
docker compose up db redis chroma
```

---

## Demo Walkthrough

### Step-by-step: raw idea → full document package

**1. Register and log in** at http://localhost:3000

**2. Create a project:**
- Click "New Project"
- Name: `Online Food Delivery App`
- Domain: `ecommerce`

**3. Submit business input (paste this):**
> "We want to build a mobile and web app for food delivery similar to Uber Eats. Customers should be able to browse restaurants, view menus, add items to cart, place orders, track delivery in real-time, and pay online via cards or wallets. Restaurant owners should manage their menu, accept/reject orders, and track earnings. Delivery riders should receive order notifications, navigate to restaurant and customer, and update delivery status. The platform needs user authentication, ratings and reviews, admin dashboard, push notifications, and promotional discount codes."

**4. Click "Analyze Requirements"** — wait ~30-60 seconds.

**5. View Requirements tab** — you should see 30+ structured requirements across FR/NFR/user roles/business rules/risks.

**6. Click "Generate Everything"** — generates all 8 document types + 8 planning artifacts + 6 Mermaid diagrams.

**7. Browse Documents tab** — view SRS, BRD, User Stories, etc. in rendered markdown.

**8. Browse Diagrams tab** — view live Mermaid renderings of ER, Sequence, Architecture diagrams.

**9. Run MoSCoW AI** (Requirements tab) — AI re-prioritizes with reasoning.

**10. Run AI Review** — get a quality score (0-100) and structured issue report with suggestions.

---

## API Documentation

All endpoints are auto-documented at `/api/docs` (Swagger UI).

Key endpoints:

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Create analyst account |
| POST | `/api/v1/auth/login` | Get JWT token |
| POST | `/api/v1/projects/` | Create project |
| POST | `/api/v1/projects/{id}/inputs/text` | Submit text input |
| POST | `/api/v1/projects/{id}/inputs/upload` | Upload PDF/DOCX |
| POST | `/api/v1/projects/{id}/requirements/analyze` | Trigger AI analysis |
| GET | `/api/v1/projects/{id}/requirements/` | List requirements |
| POST | `/api/v1/projects/{id}/documents/generate` | Generate docs |
| GET | `/api/v1/projects/{id}/documents/{type}` | Get document |
| POST | `/api/v1/projects/{id}/planning/generate` | Generate planning |
| POST | `/api/v1/projects/{id}/diagrams/generate` | Generate diagrams |
| POST | `/api/v1/projects/{id}/review/run` | Run AI review |
| GET | `/api/v1/projects/{id}/review/latest` | Get review report |
| POST | `/api/v1/projects/{id}/prioritize/moscow` | MoSCoW AI prioritize |
| GET | `/api/v1/projects/{id}/documents/{type}/diff` | Version diff |

---

## Database Migrations

```bash
# Generate a migration after model changes
cd backend
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

---

## Project Structure

```
ai-req-platform/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app entry point
│   │   ├── core/                 # Config, DB, security, logging
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   ├── api/v1/
│   │   │   ├── router.py         # Central API router
│   │   │   └── endpoints/        # One file per domain
│   │   └── services/             # All AI + business logic
│   │       ├── requirement_analysis.py   # Phase 3: LangGraph pipeline
│   │       ├── document_generator.py     # Phase 4: SRS, BRD, etc.
│   │       ├── planning_generator.py     # Phase 5: Roadmap, sprints, cost
│   │       ├── diagram_generator.py      # Phase 6: Mermaid diagrams
│   │       ├── review_engine.py          # Phase 7: AI QA review
│   │       ├── moscow_prioritizer.py     # Bonus: MoSCoW AI
│   │       ├── diff_service.py           # Bonus: version diff
│   │       ├── rag_service.py            # ChromaDB RAG integration
│   │       ├── llm_client.py             # LangChain LLM factory
│   │       └── document_parser.py        # PDF/DOCX text extraction
│   ├── alembic/                  # DB migrations
│   ├── requirements.txt
│   ├── Dockerfile
│   └── Dockerfile.worker
├── frontend/
│   └── src/
│       ├── api/                  # Axios API clients
│       ├── context/              # Auth context
│       ├── components/           # Layout, shared UI
│       └── pages/                # One page per route
├── docker-compose.yml
└── README.md
```

---

## Assumptions Made

1. **OpenAI GPT-4o** is the LLM. The system is designed to swap models by changing `OPENAI_MODEL` in `.env`. Compatible with any OpenAI-API-compatible endpoint (e.g. Azure OpenAI, LiteLLM proxy).

2. **Background tasks** use FastAPI's built-in `BackgroundTasks` for simplicity. In a production deployment with >10 concurrent users, migrate AI pipeline calls to Celery workers (infrastructure already in place — Celery + Redis are in docker-compose).

3. **File uploads** are stored to disk (`/tmp/req_uploads`). In production, replace with S3/Azure Blob Storage by swapping `document_parser.py` to read from presigned URLs.

4. **Multi-tenancy** is per-user project isolation (each user only sees their own projects). Full organization-level multi-tenancy would require an `Organization` model — deferred per scope.

5. **PDF export** of generated documents is not implemented. The structured JSON + Markdown content is available via API; a ReportLab or Pandoc post-processing step could produce PDFs.

---

## Checklist vs Requirements

| Requirement | Status |
|---|---|
| Phase 1: Structure, DB schema, Docker, REST skeleton | ✅ |
| Phase 2: Text, PDF, DOCX, transcript input | ✅ |
| Phase 3: LangGraph AI pipeline, RAG with ChromaDB | ✅ |
| Phase 4: SRS, BRD, User Stories, Use Cases, AC, Glossary | ✅ |
| Phase 5: Modules, roadmap, sprints, team, tech stack, cost, risk | ✅ |
| Phase 6: 6 Mermaid diagrams (Use Case, ER, Sequence, Class, Flow, Arch) | ✅ |
| Phase 7: AI Review Engine with quality score + structured issues | ✅ |
| Phase 8: OpenAPI docs, versioning, multi-user support | ✅ |
| Bonus: MoSCoW AI prioritization | ✅ |
| Bonus: Version diff viewer | ✅ |
| PDF/DOCX export | ⚠️ deferred (see Assumptions) |
| Jira ticket generation | ⚠️ deferred (requires Jira credentials) |
| Voice transcription | ⚠️ deferred (add Whisper API in document_parser.py) |