"""ContextVars for prompt-log correlation.

The API layer (planner session / skill builder) knows the ``session_id`` and
``purpose`` of an LLM call; the agent loop knows the current ``iteration``.
These are propagated to :mod:`app.llm.prompt_log` via contextvars so the
``LLMProvider`` Protocol stays free of logging concerns (ADR: single choke
point at the provider, no signature changes).

Use :func:`prompt_log_context` in the API layer to bind ``session_id`` /
``run_id`` / ``purpose`` for the duration of a block; use
:data:`current_iteration` directly in the agent loop (it changes every
iteration, so a context manager would be awkward).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from collections.abc import Iterator
from typing import Any

# All default to None: a value is only present when explicitly bound.
current_session_id: ContextVar[str | None] = ContextVar("prompt_log_session_id", default=None)
current_run_id: ContextVar[str | None] = ContextVar("prompt_log_run_id", default=None)
current_iteration: ContextVar[int | None] = ContextVar("prompt_log_iteration", default=None)
current_purpose: ContextVar[str | None] = ContextVar("prompt_log_purpose", default=None)


@contextmanager
def prompt_log_context(
    *,
    session_id: str | None = None,
    run_id: str | None = None,
    purpose: str | None = None,
) -> Iterator[None]:
    """Bind ``session_id`` / ``run_id`` / ``purpose`` for the duration of a block.

    Only non-None values are bound (and reset on exit), so a caller can set a
    subset without clobbering an outer context. ``iteration`` is intentionally
    not handled here — it changes every loop turn and is set directly via
    :data:`current_iteration` in the agent runner.
    """
    tokens: list[tuple[ContextVar[Any], Token[Any]]] = []
    bindings: list[tuple[ContextVar[Any], Any]] = [
        (current_session_id, session_id),
        (current_run_id, run_id),
        (current_purpose, purpose),
    ]
    for cv, value in bindings:
        if value is not None:
            tokens.append((cv, cv.set(value)))
    try:
        yield
    finally:
        # Reset in reverse order so nested contexts unwind correctly.
        for cv, tok in reversed(tokens):
            cv.reset(tok)


def collect_context() -> dict[str, Any]:
    """Snapshot the current prompt-log context for the log ``context`` block."""
    return {
        "session_id": current_session_id.get(),
        "run_id": current_run_id.get(),
        "iteration": current_iteration.get(),
        "purpose": current_purpose.get(),
    }
