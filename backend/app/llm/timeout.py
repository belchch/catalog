from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

DEFAULT_LLM_TIMEOUT_SECONDS = 60
LLM_TIMEOUT_MIN_SECONDS = 30
LLM_TIMEOUT_MAX_SECONDS = 300

_llm_timeout: ContextVar[float | None] = ContextVar("llm_timeout", default=None)


class LLMTimeoutError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.timeout_seconds = timeout_seconds


def current_llm_timeout() -> float | None:
    return _llm_timeout.get()


@contextmanager
def llm_timeout_context(seconds: float | None) -> Iterator[None]:
    token = _llm_timeout.set(seconds)
    try:
        yield
    finally:
        _llm_timeout.reset(token)
