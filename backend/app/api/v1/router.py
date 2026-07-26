"""
router.py — The master API router that assembles every sub-router into one.

WHY THIS FILE EXISTS:
  With 10+ groups of endpoints (auth, projects, requirements, documents, etc.),
  putting every route in a single file would create a 2000+ line monster.
  Instead, each domain has its OWN router file in the endpoints/ folder.
  This file simply imports all of them and wires them together.

HOW FastAPI ROUTERS WORK:
  Think of each APIRouter as a "mini-application" with its own routes.
  The master router (this file) combines them all.
  Then main.py mounts the master router under "/api/v1".

  Result — the full URL for any endpoint is:
      /api/v1  ← mounted in main.py
         + /projects  ← prefix in this file
              + /  ← defined in projects.py
    = /api/v1/projects/

URL STRUCTURE OVERVIEW:
  /api/v1/auth/...                            → login, register, get current user
  /api/v1/users/...                           → list users, update user (admin)
  /api/v1/projects/...                        → CRUD for projects
  /api/v1/projects/{id}/inputs/...            → submit text or upload files
  /api/v1/projects/{id}/requirements/...      → trigger analysis, list requirements
  /api/v1/projects/{id}/documents/...         → generate & retrieve documents
  /api/v1/projects/{id}/planning/...          → generate & retrieve planning artifacts
  /api/v1/projects/{id}/diagrams/...          → generate & retrieve diagrams
  /api/v1/projects/{id}/review/...            → run AI review, get report
  /api/v1/projects/{id}/prioritize/moscow     → MoSCoW AI re-prioritization (bonus)
  /api/v1/projects/{id}/documents/{t}/diff    → version diff viewer (bonus)
  /api/v1/projects/{id}/requirements/compare → scope comparator (bonus)
"""

# APIRouter is FastAPI's way of grouping related endpoints into modules
from fastapi import APIRouter

# Import every sub-router from the endpoints package.
# Each of these files defines its own APIRouter with its specific routes.
from app.api.v1.endpoints import (
    auth,          # Register, login, get current user
    users,         # User management (admin operations)
    projects,      # Project CRUD (create, list, get, update, delete)
    inputs,        # Requirement input submission (text + file upload)
    requirements,  # AI analysis trigger + requirement CRUD
    documents,     # Document generation + version history
    planning,      # Planning artifact generation + retrieval
    diagrams,      # Mermaid diagram generation + retrieval
    review,        # AI review engine
    bonus,         # MoSCoW prioritization + diff viewer + scope comparator
)

# Create the master router that all sub-routers attach to
api_router = APIRouter()

# ── Mount each sub-router with its URL prefix ─────────────────────────────────
# The `prefix` is prepended to every route defined in that sub-router.
# The `tags` list controls which Swagger UI section the endpoints appear under.

# Authentication — no project context needed (these are global endpoints)
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# User management — admin-level user operations
api_router.include_router(users.router, prefix="/users", tags=["Users"])

# Projects — top-level CRUD for projects
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])

# All remaining endpoints live under /projects/{project_id}/...
# The {project_id} path parameter is part of the prefix — FastAPI will automatically
# extract it and pass it to every endpoint function in these routers.

api_router.include_router(
    inputs.router,
    prefix="/projects/{project_id}/inputs",
    tags=["Requirement Inputs"],
)
api_router.include_router(
    requirements.router,
    prefix="/projects/{project_id}/requirements",
    tags=["Requirements"],
)
api_router.include_router(
    documents.router,
    prefix="/projects/{project_id}/documents",
    tags=["Documents"],
)
api_router.include_router(
    planning.router,
    prefix="/projects/{project_id}/planning",
    tags=["Planning"],
)
api_router.include_router(
    diagrams.router,
    prefix="/projects/{project_id}/diagrams",
    tags=["Diagrams"],
)
api_router.include_router(
    review.router,
    prefix="/projects/{project_id}/review",
    tags=["AI Review"],
)

# Bonus features router has NO prefix here because its endpoints define
# their own full paths (they span multiple resource types — prioritize, diff, compare)
api_router.include_router(bonus.router, prefix="", tags=["Bonus Features"])
