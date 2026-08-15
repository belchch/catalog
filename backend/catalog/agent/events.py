from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Type-only import: keeps the agent layer free of a runtime dependency on
    # the skills layer. ``VerifyResult`` is defined in ``catalog.skills.verify``.
    from catalog.skills.verify import VerifyResult


@dataclass
class TokenEvent:
    """A streamed text chunk."""

    delta: str
    step_id: str | None = None


@dataclass
class ToolCallEvent:
    id: str
    name: str
    arguments: dict
    step_id: str | None = None


@dataclass
class ToolResultEvent:
    id: str
    name: str
    ok: bool
    # ok=True -> tool return value; ok=False -> error string.
    result: Any | str
    step_id: str | None = None


@dataclass
class StepEvent:
    """Emitted at the start of each loop iteration."""

    iteration: int
    step_id: str | None = None


@dataclass
class FinishEvent:
    text: str | None
    # "stop" | "tool_calls" | "capped"
    finish_reason: str
    # True when the loop hit max_iterations without a final answer.
    capped: bool
    usage: dict
    step_id: str | None = None


@dataclass
class VerifyEvent:
    """Emitted after a verify pass over the agent's latest output.

    ``iteration`` is 1-based within the apply retry loop (not the inner
    agent loop). ``result`` is the :class:`~catalog.skills.verify.VerifyResult`.
    """

    iteration: int
    result: VerifyResult
    step_id: str | None = None


@dataclass
class RunMetaEvent:
    """Run-level metadata emitted once at the start of an apply (CATALOG-16).

    Surfaces *what* is running so the trace feed can show the model, provider,
    skill kind and the (truncated) system prompt up front — instead of only
    seeing iteration bookends.
    """

    model: str
    provider: str
    skill_kind: str
    system_prompt: str
    input_docs: list[str]


@dataclass
class ScriptEvent:
    """A stage of deterministic ``kind="script"`` execution (CATALOG-3/16).

    ``stage`` is one of ``"start"`` (carrying a code ``snippet``), ``"done"``
    (carrying the ``return_value`` and ``duration`` in seconds) or ``"error"``
    (carrying the ``error`` message + ``duration``).
    """

    stage: str
    snippet: str | None = None
    return_value: str | None = None
    duration: float | None = None
    error: str | None = None
    step_id: str | None = None


@dataclass
class ReasoningEvent:
    """A model's chain-of-thought / "thinking" text (CATALOG-24/16).

    Emitted inside an iteration when the provider returns ``reasoning_content``
    (z.ai/GLM dialect) so the trace can surface the model's reasoning, not just
    the visible answer.
    """

    text: str
    step_id: str | None = None


AgentEvent = (
    TokenEvent
    | ToolCallEvent
    | ToolResultEvent
    | StepEvent
    | FinishEvent
    | VerifyEvent
    | RunMetaEvent
    | ScriptEvent
    | ReasoningEvent
)
