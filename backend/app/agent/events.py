from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Type-only import: keeps the agent layer free of a runtime dependency on
    # the skills layer. ``VerifyResult`` is defined in ``app.skills.verify``.
    from app.skills.verify import VerifyResult


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


@dataclass
class VerifyEvent:
    """Emitted after a verify pass over the agent's latest output.

    ``iteration`` is 1-based within the apply retry loop (not the inner
    agent loop). ``result`` is the :class:`~app.skills.verify.VerifyResult`.
    """

    iteration: int
    result: VerifyResult


AgentEvent = TokenEvent | ToolCallEvent | ToolResultEvent | StepEvent | FinishEvent | VerifyEvent
