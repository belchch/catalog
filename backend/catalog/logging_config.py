"""Application logging configuration (uvicorn-style stdout lines).

A single ``StreamHandler`` on ``sys.stdout`` carries every ``catalog.*`` log line,
rendered to line up byte-for-byte with native uvicorn output
(``INFO:     <message>`` — colored level prefix, no timestamp, no logger name)
via :class:`AppFormatter`, and enriched with a compact correlation tag
(``[run=… iter=… purpose=… session=…]``) read from :mod:`catalog.llm.log_context`
through :class:`ContextFilter`.

Design notes
------------
- ``disable_existing_loggers: False`` so uvicorn's own loggers are never
  silenced when this module is imported (it runs at ``catalog.main`` import time,
  after uvicorn has configured its loggers).
- :class:`AppFormatter` subclasses uvicorn's ``DefaultFormatter`` to reuse its
  exact level-prefix / color logic; a defensive ANSI fallback is kept in case
  the uvicorn internals move.
- Idempotent: calling :func:`setup_logging` more than once just re-applies the
  same dictConfig (safe under reload / test re-import).
- The root logger stays at WARNING; only the ``catalog`` hierarchy is at INFO so
  library noise (httpx, jsonschema, ...) is suppressed by default.
"""

from __future__ import annotations

import logging
import logging.config
import sys
from typing import Any

from catalog.llm.log_context import collect_context

try:  # Reuse uvicorn's exact level/color logic so app lines match uvicorn lines.
    from uvicorn.logging import DefaultFormatter as _UvicornDefaultFormatter

    _HAS_UVICORN = True
except Exception:  # pragma: no cover - uvicorn is a hard dep; fallback is defensive.
    _HAS_UVICORN = False
    _UvicornDefaultFormatter = logging.Formatter  # type: ignore[assignment,misc]

# Defensive ANSI colors (only used if uvicorn internals are unavailable). Match
# uvicorn's ColourizedFormatter palette: DEBUG cyan, INFO green, WARNING yellow,
# ERROR red, CRITICAL bright red.
_ANSI_RESET = "\033[0m"
_ANSI_LEVEL_COLORS: dict[int, str] = {
    logging.DEBUG: "\033[36m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[91m",
}


def _fmt_context(ctx: dict[str, Any]) -> str:
    """Render a context snapshot as compact ``label=value`` pairs.

    Only non-empty values are emitted; ``run_id`` is truncated to its first
    8 characters (the full id stays in the trace / prompt-log / DB). Output
    order is fixed: ``run``, ``iter``, ``purpose``, ``session``.
    """
    parts: list[str] = []
    for src_key, label in (
        ("run_id", "run"),
        ("iteration", "iter"),
        ("purpose", "purpose"),
        ("session_id", "session"),
    ):
        value = ctx.get(src_key)
        if value is None or value == "":
            continue
        if src_key == "run_id":
            value = str(value)[:8]
        parts.append(f"{label}={value}")
    return " ".join(parts)


class ContextFilter(logging.Filter):
    """Attach ``record.ctx`` (compact correlation tag) from prompt-log contextvars.

    Empty context renders as an empty string so :class:`AppFormatter` omits the
    ``[…]`` block entirely.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.ctx = _fmt_context(collect_context())
        return True


class AppFormatter(_UvicornDefaultFormatter):
    """uvicorn-style formatter: ``INFO:     [run=… purpose=…] <message>``.

    Reuses uvicorn's ``DefaultFormatter`` level/color logic (colored level
    prefix, no timestamp, no logger name) so ``catalog.*`` lines line up with native
    uvicorn lines, then injects the compact correlation tag when present.
    """

    def __init__(self, use_colors: bool | None = None) -> None:
        if _HAS_UVICORN:
            super().__init__(use_colors=use_colors)  # type: ignore[call-arg]
        else:  # pragma: no cover - defensive fallback.
            super().__init__()
            self.use_colors = sys.stdout.isatty() if use_colors is None else bool(use_colors)

    def _level_prefix(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        separator = " " * (8 - len(levelname))
        if getattr(self, "use_colors", False):
            if _HAS_UVICORN:
                levelname = self.color_level_name(levelname, record.levelno)
            else:  # pragma: no cover - defensive fallback.
                color = _ANSI_LEVEL_COLORS.get(record.levelno)
                if color:
                    levelname = f"{color}{levelname}{_ANSI_RESET}"
        return f"{levelname}:{separator}"

    def formatMessage(self, record: logging.LogRecord) -> str:
        levelprefix = self._level_prefix(record)
        ctx = getattr(record, "ctx", "")
        tag = f" [{ctx}]" if ctx else ""
        return f"{levelprefix}{tag} {record.getMessage()}"


def setup_logging(level: str | None = None) -> None:
    """Configure stdout logging for the ``catalog`` hierarchy.

    ``level`` overrides the ``catalog`` logger level (defaults to INFO when
    ``None``). Safe to call repeatedly.
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
                    "()": f"{AppFormatter.__module__}.{AppFormatter.__name__}",
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
                "catalog": {
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
