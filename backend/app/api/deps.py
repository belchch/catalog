"""Shared helpers for the API routers.

Dependencies read collaborators from ``app.state`` (populated by the lifespan
in :mod:`app.main`). Tests override ``app.state`` directly after entering the
``TestClient`` lifespan context, which works uniformly for HTTP and WebSocket
endpoints.
"""

from __future__ import annotations

from fastapi import Request, WebSocket

from app.agent.events import (
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
            "result": event.result,
        }
    if isinstance(event, VerifyEvent):
        return {
            "type": "verify",
            "iteration": event.iteration,
            "passed": event.result.passed,
            "failures": list(event.result.failures),
        }
    # FinishEvent is handled by the caller (sessions emits a token+finish pair;
    # runs emit an authoritative finish from the DB after the stream drains).
    return None
