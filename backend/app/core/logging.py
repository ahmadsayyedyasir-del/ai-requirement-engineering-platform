"""
logging.py — Centralised logging configuration.

WHY THIS FILE EXISTS:
  By default, Python's logging module outputs messages in a basic format
  and only shows WARNING level and above. For a production server, we want:
    - A consistent, readable format on every line (timestamp | level | source | message)
    - INFO level so we can trace the AI pipeline's progress step by step
    - Quieter third-party libraries (they tend to spam the logs with irrelevant info)

HOW LOGGING WORKS IN PYTHON:
  Python's logging is hierarchical. There's a root logger at the top, and
  every named logger (e.g., logging.getLogger("reqeng.analysis")) is a child.
  A child logger inherits the level and handlers of its parent unless overridden.

  We call `setup_logging()` once in main.py before the server starts.
  After that, every file creates its own named logger for easy filtering:
    logger = logging.getLogger("reqeng.analysis")
    logger.info("Starting pipeline...")
"""

# Python's built-in logging module
import logging

# sys.stdout sends log messages to the terminal (standard output).
# In Docker, this is captured by `docker compose logs`.
import sys


def setup_logging(level: str = "INFO") -> None:
    """
    Configure the root logger for the entire application.

    WHY `basicConfig`: It's a one-call setup that applies to the root logger,
    which means all child loggers inherit these settings automatically.

    Args:
        level: The minimum severity to log. Options from least to most severe:
               DEBUG < INFO < WARNING < ERROR < CRITICAL
               INFO is good for production (you see pipeline steps but not raw SQL).
               DEBUG is useful during development (shows everything including SQL).
    """
    logging.basicConfig(
        # Convert the string level ("INFO") to the numeric constant (20)
        level=getattr(logging, level.upper(), logging.INFO),

        # Log format: each line shows when, how severe, where from, and what.
        # %(asctime)s   → "2024-01-15 10:23:45,123"
        # %(levelname)  → "INFO    " (padded to 8 chars for alignment)
        # %(name)s      → "reqeng.analysis" (the logger's name)
        # %(message)s   → the actual log message
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",

        # Send all logs to the terminal so Docker can capture them
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Silence noisy third-party libraries.
    # These libraries log a LOT of HTTP request details that clutter our logs.
    # Setting them to WARNING means we only hear from them if something goes wrong.
    logging.getLogger("httpx").setLevel(logging.WARNING)    # HTTP client used by OpenAI SDK
    logging.getLogger("openai").setLevel(logging.WARNING)   # OpenAI Python SDK
    logging.getLogger("chromadb").setLevel(logging.WARNING) # ChromaDB vector store


# A module-level logger for general application messages.
# Other files create their own specialised loggers like:
#   logger = logging.getLogger("reqeng.analysis")
#   logger = logging.getLogger("reqeng.diagrams")
# This lets us filter logs by subsystem if needed.
logger = logging.getLogger("reqeng")
