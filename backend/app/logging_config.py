"""Application logging configuration (plan: skill-execution-logging).

A single ``StreamHandler`` on ``sys.stdout`` carries every ``app.*`` log line,
enriched with a correlation context (``run_id`` / ``session_id`` / ``iteration``
/ ``purpose``) read from :mod:`app.llm.log_context` via :class:`ContextFilter`.

Design notes
------------
- ``disable_existing_loggers: False`` so uvicorn's own loggers are never
  silenced when this module is imported (it runs at ``app.main`` import time,
  after uvicorn has configured its loggers).
- Idempotent: calling :func:`setup_logging` more than once just re-applies the
  same dictConfig (safe under reload / test re-import).
- The root logger stays at WARNING; only the ``app`` hierarchy is at INFO so
  library noise (httpx, jsonschema, ...) is suppressed by default.
"""

from __future__ import annotations

import logging
import logging.config
import sys
from typing import Any

from app.llm.log_context import collect_context

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(ctx)s] %(message)s"


def _fmt_context(ctx: dict[str, Any]) -> str:
    """Render a context snapshot as ``key=value`` pairs (only non-empty)."""
    parts: list[str] = []
    for key in ("session_id", "run_id", "iteration", "purpose"):
        value = ctx.get(key)
        if value is not None and value != "":
            parts.append(f"{key}={value}")
    return " ".join(parts)


class ContextFilter(logging.Filter):
    """Attach ``record.ctx`` from the current prompt-log contextvars.

    The formatter references ``%(ctx)s``; without this filter the attribute
    would be missing and formatting would fail. Empty context renders as an
    empty string so the brackets stay ``[]``.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.ctx = _fmt_context(collect_context())
        return True


def setup_logging(level: str | None = None) -> None:
    """Configure stdout logging for the ``app`` hierarchy.

    ``level`` overrides the ``app`` logger level (defaults to ``LOG_LEVEL``
    from :mod:`app.config`` when ``None``). Safe to call repeatedly.
    """
    resolved = (level or logging.getLevelName(logging.INFO)).upper()

    logging.config.dictConfig(
        {
            "version": 1,
            # Do not silence uvicorn / pre-existing loggers on re-configuration.
            "disable_existing_loggers": False,
            "filters": {
                "context": {
                    "()": f"{ContextFilter.__module__}.{ContextFilter.__name__}",
                },
            },
            "formatters": {
                "default": {
                    "format": _LOG_FORMAT,
                },
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "level": "INFO",
                    "formatter": "default",
                    "filters": ["context"],
                },
            },
            "loggers": {
                "app": {
                    "level": resolved,
                    "handlers": ["stdout"],
                    "propagate": False,
                },
            },
            # Root stays quiet: only warnings+ from libraries we don't own.
            "root": {
                "level": "WARNING",
                "handlers": ["stdout"],
            },
        }
    )
