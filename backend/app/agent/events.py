from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TokenEvent:
    """A streamed text chunk."""

    delta: str


@dataclass
class ToolCallEvent:
    id: str
    name: str
    arguments: dict


@dataclass
class ToolResultEvent:
    id: str
    name: str
    ok: bool
    # ok=True -> tool return value; ok=False -> error string.
    result: Any | str


@dataclass
class StepEvent:
    """Emitted at the start of each loop iteration."""

    iteration: int


@dataclass
class FinishEvent:
    text: str | None
    # "stop" | "tool_calls" | "capped"
    finish_reason: str
    # True when the loop hit max_iterations without a final answer.
    capped: bool
    usage: dict


AgentEvent = TokenEvent | ToolCallEvent | ToolResultEvent | StepEvent | FinishEvent
