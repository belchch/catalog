"""Shared helpers for the API routers.

Dependencies read collaborators from ``app.state`` (populated by the lifespan
in :mod:`app.main`). Tests override ``app.state`` directly after entering the
``TestClient`` lifespan context, which works uniformly for HTTP and WebSocket
endpoints.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request, WebSocket

from app.agent.events import (
    ReasoningEvent,
    RunMetaEvent,
    ScriptEvent,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    VerifyEvent,
)
from app.agent.registry import ToolRegistry
from app.config import Settings
from app.llm.base import LLMProvider
from app.storage.db import Database


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_provider(request: Request) -> LLMProvider:
    return request.app.state.provider


def get_workspace(request: Request) -> str:
    return request.app.state.workspace


def get_repo_root(request: Request) -> str:
    """The connected KB repo root (ADR-0022) — same value as ``get_workspace``.

    Distinct dependency name so KB-repo code (git/scan/skill materialization)
    reads its intent from the call site rather than the pre-ADR-0022 name.
    """
    return request.app.state.repo_root


def get_tools(request: Request) -> ToolRegistry:
    return request.app.state.tools


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def ws_get(websocket: WebSocket, name: str):
    """Read a collaborator from ``app.state`` inside a WebSocket handler."""
    return getattr(websocket.app.state, name)


def agent_event_to_frame(event) -> dict | None:
    """Map an :data:`AgentEvent` to a WS JSON frame.

    Returns ``None`` for events with no direct wire representation (notably
    inner-agent :class:`FinishEvent` in the runs stream, where the authoritative
    finish is emitted separately from the persisted run row).
    """
    if isinstance(event, StepEvent):
        return {"type": "step", "iteration": event.iteration}
    if isinstance(event, TokenEvent):
        return {"type": "token", "delta": event.delta}
    if isinstance(event, ToolCallEvent):
        return {
            "type": "tool_call",
            "id": event.id,
            "name": event.name,
            "arguments": event.arguments,
        }
    if isinstance(event, ToolResultEvent):
        return {
            "type": "tool_result",
            "id": event.id,
            "name": event.name,
            "ok": event.ok,
            "result": _snip_result(event.result),
        }
    if isinstance(event, VerifyEvent):
        return {
            "type": "verify",
            "iteration": event.iteration,
            "passed": event.result.passed,
            "failures": list(event.result.failures),
        }
    if isinstance(event, RunMetaEvent):
        return {
            "type": "meta",
            "model": event.model,
            "provider": event.provider,
            "skill_kind": event.skill_kind,
            "system_prompt": _snip(event.system_prompt),
            "input_docs": list(event.input_docs),
        }
    if isinstance(event, ScriptEvent):
        frame: dict = {"type": "script", "stage": event.stage}
        if event.snippet is not None:
            frame["snippet"] = _snip(event.snippet)
        if event.return_value is not None:
            frame["return_value"] = _snip(event.return_value)
        if event.duration is not None:
            frame["duration"] = event.duration
        if event.error is not None:
            frame["error"] = event.error
        return frame
    if isinstance(event, ReasoningEvent):
        return {"type": "reasoning", "text": _snip(event.text)}
    # FinishEvent is handled by the caller (sessions emits a token+finish pair;
    # runs emit an authoritative finish from the DB after the stream drains).
    return None


def _snip(s: str | None, limit: int = 400) -> str:
    """Bound a free-text field (prompt/snippet/result) carried by a frame.

    The full value is preserved in the trace and the prompt-log; this only caps
    the wire frame so a huge system prompt or ``read_document`` payload cannot
    flood the trace feed.
    """
    if s is None:
        return ""
    if len(s) > limit:
        return s[:limit] + "…[truncated]"
    return s


def _snip_result(result: Any, limit: int = 400) -> str:
    """Bound a tool result carried by a ``tool_result`` frame.

    ``result`` may be a free-text error string or a structured tool return
    value (dict/list, e.g. a ``read_document`` payload). Structured values are
    serialized to JSON before truncation so a huge document cannot flood the
    trace feed; the full value is preserved in the trace/prompt-log.
    """
    if isinstance(result, str):
        return _snip(result, limit)
    try:
        return _snip(json.dumps(result, ensure_ascii=False, default=str), limit)
    except (TypeError, ValueError):
        return _snip(str(result), limit)
