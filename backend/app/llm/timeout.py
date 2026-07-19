from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

DEFAULT_LLM_TIMEOUT_SECONDS = 60
LLM_TIMEOUT_MIN_SECONDS = 30
LLM_TIMEOUT_MAX_SECONDS = 300


@dataclass(frozen=True, slots=True)
class LLMTimeoutBudget:
    seconds: float
    deadline: float


_llm_timeout: ContextVar[LLMTimeoutBudget | None] = ContextVar(
    "llm_timeout", default=None
)


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
    budget = _llm_timeout.get()
    return None if budget is None else budget.seconds


def current_llm_deadline() -> float | None:
    budget = _llm_timeout.get()
    return None if budget is None else budget.deadline


def remaining_llm_timeout() -> float | None:
    budget = _llm_timeout.get()
    if budget is None:
        return None
    return budget.deadline - time.monotonic()


@contextmanager
def llm_timeout_context(seconds: float | None) -> Iterator[None]:
    if seconds is None:
        token = _llm_timeout.set(None)
    else:
        value = float(seconds)
        token = _llm_timeout.set(
            LLMTimeoutBudget(seconds=value, deadline=time.monotonic() + value)
        )
    try:
        yield
    finally:
        _llm_timeout.reset(token)
