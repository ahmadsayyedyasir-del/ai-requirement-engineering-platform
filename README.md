# AI Requirement Engineering Platform
### Ezitech | AI-017

An end-to-end AI platform that turns a raw business idea into a complete software
engineering document package — SRS, BRD, User Stories, UML diagrams, sprint plans,
cost estimates, and a quality review — in minutes, not weeks.

---

## LLM Provider — Groq (NOT OpenAI)

> **Clarification:** The actual default LLM wired up in `llm_client.py` is
> **Groq** using **`llama-3.3-70b-versatile`** — NOT OpenAI GPT-4o.
>
> Groq was chosen because it offers a free tier, is extremely fast
> (~500 tokens/second via LPU hardware), and produces high-quality structured
> JSON output. GPT-4o is supported as a drop-in alternative — set
> `LLM_PROVIDER=openai` and `OPENAI_API_KEY` in your `.env` to switch.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│         React + Vite Frontend  (Vercel)          │
│         https://your-app.vercel.app              │
└────────────────────┬─────────────────────────────┘
                     │  HTTPS (VITE_API_URL)
┌────────────────────▼─────────────────────────────┐
│       FastAPI Backend  (Railway / Render)         │
│       /api/v1  · JWT auth · async endpoints      │
└──┬───────────┬──────────────┬────────────────────┘
   │           │              │
┌──▼──┐  ┌────▼───┐  ┌───────▼──────┐  ┌──────────────┐
│  DB │  │ Redis  │  │  ChromaDB    │  │  Groq API    │
│  PG │  │Celery  │  │  RAG vectors │  │ llama-3.3-70b│
└─────┘  └────────┘  └──────────────┘  └──────────────┘
```

### AI Pipeline (LangGraph — 5 nodes)

```
Input text/PDF → step_load_inputs → step_rag_context
              → step_extract_requirements (Groq LLM)
              → step_validate_output → step_persist → PostgreSQL
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI |
| AI Orchestration | LangChain + LangGraph |
| LLM (default) | **Groq — llama-3.3-70b-versatile** |
| LLM (alternative) | OpenAI GPT-4o (set `LLM_PROVIDER=openai`) |
| Vector Store / RAG | ChromaDB |
| Database | PostgreSQL 16 |
| Cache / Queue | Redis 7 + Celery |
| Diagrams | Mermaid.js (client-side render) |
| Frontend | React 18 + Vite |
| Containers | Docker + Compose |

---

## Quick Start (Local — Docker)

**Prerequisites:** Docker Desktop + a free Groq key from https://console.groq.com

```bash
# 1. Clone
git clone https://github.com/ahmadsayyedyasir-del/ai-requirement-engineering-platform.git
cd ai-requirement-engineering-platform

# 2. Configure
cp backend/.env.example backend/.env
# Open backend/.env and set:  GROQ_API_KEY=gsk_...

# 3. Start (first run takes 5-10 min to download images)
docker compose up --build

# 4. Open
#   Frontend:  http://localhost:3000
#   API docs:  http://localhost:8000/api/docs
```

**Windows one-click scripts** (no terminal needed after first setup):
- `start.bat` — starts all services and opens the browser automatically
- `stop.bat`  — stops all services (your database data is preserved)

---

## Production Deployment

### Option A — Railway (API) + Vercel (Frontend)

#### Step 1 — Deploy the backend API on Railway

1. Go to [railway.app](https://railway.app) → **Login with GitHub**
2. **New Project → Deploy from GitHub repo** → select this repo
3. Railway detects `railway.json` — it builds from `backend/Dockerfile`
4. Click **Add Plugin → PostgreSQL** — Railway creates a managed database
5. Click **Add Plugin → Redis** — Railway creates a managed Redis
6. Go to **your API service → Variables** and add every variable from the table below
7. Copy the **public URL** Railway assigns (e.g. `https://reqeng-api.railway.app`)

**Railway environment variables to paste:**

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `SECRET_KEY` | run `python -c "import secrets; print(secrets.token_hex(32))"` |
| `LLM_PROVIDER` | `groq` |
| `GROQ_API_KEY` | your `gsk_...` key from console.groq.com |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` |
| `DATABASE_URL` | copy from Railway PostgreSQL → change `postgresql://` to `postgresql+asyncpg://` |
| `REDIS_URL` | copy from Railway Redis plugin |
| `CELERY_BROKER_URL` | same Redis URL with `/1` appended |
| `CELERY_RESULT_BACKEND` | same Redis URL with `/2` appended |
| `FRONTEND_URL` | your Vercel URL — fill in after Step 2 |
| `CHROMA_HOST` | add a second Railway service running `chromadb/chroma:0.5.23`, or leave empty to disable RAG |
| `CHROMA_PORT` | `8000` |
| `UPLOAD_DIR` | `/tmp/req_uploads` |
| `MAX_UPLOAD_SIZE_MB` | `50` |

#### Step 2 — Deploy the Celery worker on Railway

1. In the same Railway project, click **New Service → GitHub Repo** again
2. In **Settings → Build**, set **Dockerfile Path** to `backend/Dockerfile.worker`
3. Add the same environment variables as the API service above

#### Step 3 — Deploy the frontend on Vercel

1. Go to [vercel.com](https://vercel.com) → **Login with GitHub**
2. **New Project → Import** this GitHub repo
3. Vercel detects `frontend/vercel.json` automatically
4. Set **Root Directory** to `frontend`
5. Add this environment variable in **Settings → Environment Variables**:

| Variable | Value |
|---|---|
| `VITE_API_URL` | your Railway API URL (e.g. `https://reqeng-api.railway.app`) |

6. Click **Deploy**
7. Copy the Vercel URL → go back to Railway → update `FRONTEND_URL` with it

---

### Option B — Render (all services)

1. Go to [render.com](https://render.com) → **Login with GitHub**
2. **New → Blueprint** → select this repo
3. Render reads `render.yaml` and creates all services automatically
4. Fill in the `sync: false` variables (marked with a lock icon) in the Render dashboard:
   - `SECRET_KEY`
   - `GROQ_API_KEY`
   - `FRONTEND_URL` (fill in after frontend is deployed)
   - `CHROMA_HOST` (optional — for RAG)

---

## All Environment Variables

See [`backend/.env.example`](backend/.env.example) for the full annotated list of
backend variables, and [`frontend/.env.example`](frontend/.env.example) for
frontend variables.

**Critical ones at a glance:**

| Variable | Where | What it does |
|---|---|---|
| `GROQ_API_KEY` | backend | Groq API key (required) |
| `SECRET_KEY` | backend | JWT signing secret (required, must be random) |
| `DATABASE_URL` | backend | PostgreSQL asyncpg connection string |
| `REDIS_URL` | backend | Redis connection string |
| `FRONTEND_URL` | backend | Your Vercel URL — added to CORS allowed origins |
| `VITE_API_URL` | frontend | Your Railway/Render API URL |

---

## Demo Walkthrough

1. Register at `/register` — create your analyst account
2. **New Project** — name it `Food Delivery App`, domain `ecommerce`
3. Paste this into the text box and click **Submit**:
   > *"Build a food delivery app. Customers browse restaurants, place orders,
   > pay online, and track delivery in real time. Restaurant owners manage
   > menus and earnings. Riders receive notifications and update status."*
4. Click **Analyze Requirements** — wait ~30 seconds (Groq is fast)
5. Click **Generate Everything** — wait ~3-5 minutes
6. Browse:
   - **Requirements** — 30+ structured FRs, NFRs, risks, rules
   - **Documents** — SRS, BRD, User Stories, Acceptance Criteria
   - **Planning** — roadmap, sprint plan, cost estimate
   - **Diagrams** — ER diagram, sequence diagram, architecture
   - **AI Review** — quality score (0-100) + issue list

---

## API Documentation

Auto-generated at `/api/docs` (Swagger UI) and `/api/redoc`.

Key endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Create account |
| `POST` | `/api/v1/auth/login` | Get JWT token |
| `POST` | `/api/v1/projects/` | Create project |
| `POST` | `/api/v1/projects/{id}/inputs/text` | Submit text |
| `POST` | `/api/v1/projects/{id}/inputs/upload` | Upload PDF/DOCX |
| `POST` | `/api/v1/projects/{id}/requirements/analyze` | Run AI analysis |
| `GET` | `/api/v1/projects/{id}/requirements/` | List requirements |
| `POST` | `/api/v1/projects/{id}/documents/generate` | Generate documents |
| `POST` | `/api/v1/projects/{id}/planning/generate` | Generate planning |
| `POST` | `/api/v1/projects/{id}/diagrams/generate` | Generate diagrams |
| `POST` | `/api/v1/projects/{id}/review/run` | Run AI review |
| `POST` | `/api/v1/projects/{id}/prioritize/moscow` | MoSCoW re-prioritize |
| `GET` | `/api/v1/projects/{id}/documents/{type}/diff` | Version diff |

---

## Project Structure

```
ai-requirement-engineering-platform/
├── railway.json              ← Railway deployment config (API service)
├── render.yaml               ← Render Blueprint (all services)
├── docker-compose.yml        ← Local Docker Compose (6 services)
├── start.bat / stop.bat      ← Windows one-click launchers
├── backend/
│   ├── .env.example          ← All backend env vars documented
│   ├── Dockerfile            ← API container
│   ├── Dockerfile.worker     ← Celery worker container
│   ├── requirements.txt
│   └── app/
│       ├── main.py           ← FastAPI entry point + CORS
│       ├── core/             ← config, database, security, logging
│       ├── models/           ← SQLAlchemy ORM (8 models)
│       ├── schemas/          ← Pydantic schemas
│       ├── api/v1/endpoints/ ← REST endpoints (11 files)
│       └── services/         ← AI pipeline + business logic
│           ├── llm_client.py           ← Groq / OpenAI factory
│           ├── requirement_analysis.py ← LangGraph 5-node pipeline
│           ├── document_generator.py   ← SRS, BRD, User Stories...
│           ├── planning_generator.py   ← Roadmap, sprints, cost...
│           ├── diagram_generator.py    ← Mermaid.js diagrams
│           ├── review_engine.py        ← AI quality reviewer
│           └── rag_service.py          ← ChromaDB RAG
└── frontend/
    ├── .env.example          ← Frontend env vars documented
    ├── vercel.json           ← Vercel deployment config
    ├── Dockerfile            ← Production Nginx container
    ├── vite.config.js
    └── src/
        ├── api/client.js     ← Axios (reads VITE_API_URL)
        ├── context/          ← Auth context
        ├── components/       ← Layout
        └── pages/            ← 7 pages
```

---

## Phase Checklist

| Phase | Description | Status |
|---|---|---|
| 1 | Structure, DB schema, Docker, REST skeleton | Done |
| 2 | Text, PDF, DOCX, transcript input | Done |
| 3 | LangGraph pipeline, ChromaDB RAG | Done |
| 4 | SRS, BRD, User Stories, Use Cases, Glossary | Done |
| 5 | Roadmap, sprints, team, cost, risk | Done |
| 6 | 6 Mermaid diagrams | Done |
| 7 | AI Review Engine, quality score | Done |
| 8 | OpenAPI docs, versioning, multi-user | Done |
| Bonus | MoSCoW AI + version diff viewer | Done |
| Deploy | Railway + Vercel configs, env documentation | Done |
| PDF export | ReportLab/Pandoc post-processing | Deferred |
| Voice transcription | Whisper API integration | Deferred |
