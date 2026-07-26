"""
worker.py — Celery application definition for background AI task processing.

WHY THIS FILE EXISTS:
  The Celery worker container runs with: celery -A app.worker worker ...
  The `-A app.worker` flag tells Celery "find the Celery app object in app/worker.py".
  Without this file, the worker container crashes on startup with ModuleNotFoundError.

HOW CELERY WORKS IN THIS PROJECT:
  The current architecture uses FastAPI's built-in BackgroundTasks for AI pipeline jobs
  (analysis, document generation, diagram generation). These run inside the API process.

  This file provides the Celery app object so the dedicated worker container
  can be used for heavier workloads. As the project scales, long-running jobs
  (GPT-4o calls that take 30–60 seconds) can be moved here to keep the API
  process free for handling new requests.

  Current state: Celery is set up and connected to Redis but tasks are still
  handled by BackgroundTasks in the API. This file is the foundation to migrate
  tasks to Celery workers in future iterations.

CONFIGURATION:
  broker_url       — Redis database 1 (tasks are sent here by the API)
  result_backend   — Redis database 2 (task results are stored here)
  task_serializer  — JSON format for task messages (human-readable, safe)
  accept_content   — Only accept JSON-serialized task messages
  timezone         — UTC for consistent timestamps across environments
  enable_utc       — Store all datetimes as UTC

AUTODISCOVERY:
  celery.autodiscover_tasks(['app']) tells Celery to look for tasks in
  app/tasks.py (or app/*/tasks.py). This allows adding Celery tasks later
  without modifying this file.
"""

# Celery is the distributed task queue library
from celery import Celery

# Import settings to get Redis connection URLs from the .env file
from app.core.config import settings

# Import the logging setup so Celery worker logs are formatted consistently
from app.core.logging import setup_logging

# Set up logging before anything else runs
setup_logging()

# ── Create the Celery application ─────────────────────────────────────────────
# The first argument ("reqeng") is the name of this Celery application.
# It appears in log messages and the Celery monitoring dashboard.
celery_app = Celery(
    "reqeng",
    broker=settings.CELERY_BROKER_URL,        # Where to send task messages (Redis db 1)
    backend=settings.CELERY_RESULT_BACKEND,    # Where to store results (Redis db 2)
)

# ── Configure the Celery application ──────────────────────────────────────────
celery_app.conf.update(
    # Use JSON for serializing task arguments and results.
    # JSON is safer than pickle (no arbitrary code execution) and human-readable.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # All timestamps in UTC — prevents timezone confusion across servers
    timezone="UTC",
    enable_utc=True,

    # How long task results are kept in Redis before expiring (24 hours)
    result_expires=86400,

    # Retry a failed task once before marking it as FAILED
    task_acks_late=True,

    # Prevent workers from prefetching too many tasks at once
    # (important when tasks are long-running AI jobs)
    worker_prefetch_multiplier=1,
)

# ── Autodiscovery ──────────────────────────────────────────────────────────────
# Tell Celery to look for @celery_app.task decorated functions in the app package.
# When a tasks.py file is added later, it will be found automatically.
celery_app.autodiscover_tasks(["app"])

# ── Example of how to define a Celery task (for future use) ───────────────────
# To move an AI pipeline to Celery instead of BackgroundTasks, define it like:
#
#   @celery_app.task(bind=True, max_retries=3)
#   def analyze_requirements_task(self, project_id: str, input_ids=None):
#       import asyncio
#       from app.services.requirement_analysis import run_requirement_analysis
#       import uuid
#       asyncio.run(run_requirement_analysis(uuid.UUID(project_id), input_ids))
#
# Then call it from the endpoint as:
#   analyze_requirements_task.delay(str(project_id))
# instead of:
#   background_tasks.add_task(run_requirement_analysis, project_id=project_id)
