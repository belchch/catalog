"""Event → log mapper for the agent loop (plan: skill-execution-logging).

Single source of truth that turns an :data:`AgentEvent` into one structured
``app.agent`` log line. ``TokenEvent`` is intentionally skipped — the token
stream is high-frequency noise that already lands in the trace and the
prompt-log.

Kept deliberately simple and side-effect-free: a logging failure must never
break an agent run, so the mapper only formats and delegates to ``logger.info``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent.events import (
    AgentEvent,
    FinishEvent,
    ReasoningEvent,
    RunMetaEvent,
    ScriptEvent,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    VerifyEvent,
)

logger = logging.getLogger("app.agent")

# Bound on the serialized form of a logged payload. The full value is still
# preserved in the trace and the prompt-log; this only caps the stdout line.
_TRUNC_LIMIT = 300
_TRUNC_SUFFIX = "…[truncated]"


def _trunc(v: Any, limit: int = _TRUNC_LIMIT) -> str:
    """Serialize + truncate a value for inclusion in a log line.

    ``dict`` / ``list`` are JSON-encoded (``ensure_ascii=False``); anything else
    is ``str(v)``. Output longer than ``limit`` is cut and suffixed with
    ``…[truncated]`` so a huge ``read_document`` payload cannot flood stdout.
    """
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False, default=str)
    else:
        s = str(v)
    if len(s) > limit:
        return s[:limit] + _TRUNC_SUFFIX
    return s


def log_agent_event(event: AgentEvent) -> None:
    """Emit one structured log line for ``event`` (no-op for ``TokenEvent``)."""
    if isinstance(event, StepEvent):
        logger.info("agent iteration %d", event.iteration)
        return
    if isinstance(event, TokenEvent):
        # Token stream is intentionally not logged (noise).
        return
    if isinstance(event, ToolCallEvent):
        logger.info(
            "tool_call name=%s args=%s", event.name, _trunc(event.arguments)
        )
        return
    if isinstance(event, ToolResultEvent):
        logger.info(
            "tool_result name=%s ok=%s result=%s",
            event.name,
            event.ok,
            _trunc(event.result),
        )
        return
    if isinstance(event, VerifyEvent):
        logger.info(
            "verify attempt=%d passed=%s failures=%s",
            event.iteration,
            event.result.passed,
            list(event.result.failures),
        )
        return
    if isinstance(event, FinishEvent):
        logger.info(
            "finish reason=%s capped=%s text=%s",
            event.finish_reason,
            event.capped,
            _trunc(event.text),
        )
        return
    if isinstance(event, RunMetaEvent):
        logger.info(
            "run_meta model=%s provider=%s kind=%s prompt=%s input_docs=%d",
            event.model,
            event.provider,
            event.skill_kind,
            _trunc(event.system_prompt),
            len(event.input_docs),
        )
        return
    if isinstance(event, ScriptEvent):
        logger.info(
            "script stage=%s duration=%s snippet=%s return=%s error=%s",
            event.stage,
            event.duration,
            _trunc(event.snippet) if event.snippet is not None else None,
            _trunc(event.return_value) if event.return_value is not None else None,
            event.error,
        )
        return
    if isinstance(event, ReasoningEvent):
        logger.info("reasoning text=%s", _trunc(event.text))
        return
