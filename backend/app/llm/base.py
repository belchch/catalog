from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class Message:
    role: str
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ModelInfo:
    id: str
    name: str
    context_length: int | None = None


@dataclass
class CompletionResult:
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str
    usage: dict = field(default_factory=dict)
    # Chain-of-thought / "thinking" text emitted by reasoning models
    # (``reasoning_content`` in the z.ai/GLM dialect). ``None`` when the
    # provider does not emit reasoning for this response. See ADR-0013.
    reasoning: str | None = None


@dataclass
class StreamDelta:
    """One chunk from a streaming completion.

    ``content`` is the visible text delta; ``reasoning`` carries the model's
    chain-of-thought (``reasoning_content`` in the z.ai/GLM dialect) when the
    provider emits it, otherwise ``None``. A delta may carry only ``content``,
    only ``reasoning``, or both. See ADR-0013 for the streaming contract.
    """

    content: str = ""
    reasoning: str | None = None


class LLMProvider(Protocol):
    async def list_models(self) -> list[ModelInfo]: ...

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
    ) -> CompletionResult: ...

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[StreamDelta]: ...


# --- Serialization helpers --------------------------------------------------
# Shared by the OpenRouter provider (request body) and the prompt logger
# (capturing the raw request). Kept here so both consume one definition and
# the logged payload matches what was actually sent over the wire.


def message_to_dict(msg: Message) -> dict[str, Any]:
    """Serialize a :class:`Message` to the OpenRouter chat-completions shape.

    Only set fields are included so the payload matches what the provider sends.
    ``tool_calls`` arguments are JSON-encoded to a string (API contract).
    """
    d: dict[str, Any] = {"role": msg.role}
    if msg.content is not None:
        d["content"] = msg.content
    if msg.tool_calls is not None:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in msg.tool_calls
        ]
    if msg.tool_call_id is not None:
        d["tool_call_id"] = msg.tool_call_id
    if msg.name is not None:
        d["name"] = msg.name
    return d


def tool_specs_to_dicts(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Serialize :class:`ToolSpec` items to the OpenRouter ``tools`` shape."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]
