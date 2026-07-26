# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile — Builds the FastAPI backend container image.
#
# HOW A DOCKERFILE WORKS:
#   Each instruction (FROM, RUN, COPY, etc.) creates a new "layer" in the image.
#   Docker caches each layer — if a layer hasn't changed, it reuses the cache.
#   This is why we COPY requirements.txt and pip install BEFORE copying the app code:
#     - requirements.txt changes rarely  → layer is cached → pip install is skipped
#     - App code changes often           → only the COPY . . layer rebuilds (fast)
#
# BASE IMAGE:
#   python:3.12-slim is the official Python 3.12 image stripped of dev tools.
#   "slim" saves ~200MB vs the full image. We add back only what we need below.
#
# SYSTEM DEPENDENCIES (why each one is needed):
#   gcc       — C compiler, required for building some Python packages (e.g., cryptography)
#   libpq-dev — PostgreSQL client headers, required by psycopg2-binary
#   libffi-dev — Foreign Function Interface library, required by cryptography/bcrypt
#   curl      — Used by the Docker HEALTHCHECK to GET the /health endpoint
#
# NOTE ON INLINE COMMENTS IN RUN:
#   Dockerfile RUN continuations use backslash (\) for line continuation.
#   You CANNOT put comments after a backslash — the build will fail.
#   Comments must be on their own line starting with #, which is only valid
#   at the start of a Dockerfile instruction, not inside a RUN block.
#   That is why the apt-get package list has no inline comments.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# Set working directory — all subsequent commands are relative to /app
WORKDIR /app

# Install system-level dependencies needed by Python packages.
# --no-install-recommends: only install listed packages, not "nice to have" extras.
# rm -rf /var/lib/apt/lists/*: delete the apt index after install to reduce image size.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker's layer caching.
# If requirements.txt is unchanged, Docker skips the pip install step on rebuild.
COPY requirements.txt .

# Install all Python dependencies.
# --no-cache-dir: don't store the downloaded .whl files — saves ~100MB in image size.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
# This layer rebuilds on every code change, but it's just a file copy — fast.
COPY . .

# Create the upload directory for PDF/DOCX files.
# In Docker Compose this maps to a named volume (persists across restarts).
RUN mkdir -p /tmp/req_uploads

# Document that the container listens on port 8000.
# This is metadata only — actual port mapping is in docker-compose.yml.
EXPOSE 8000

# Start the FastAPI server.
# uvicorn: async-capable ASGI server (required for FastAPI's async endpoints)
# app.main:app   → the `app` FastAPI object defined in backend/app/main.py
# --host 0.0.0.0 → listen on all interfaces (required inside Docker containers)
# --port 8000    → must match the EXPOSE above
# --workers 2    → 2 worker processes for handling concurrent requests
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
