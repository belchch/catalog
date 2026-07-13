from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.llm.base import Message, ToolSpec
from app.llm.openrouter import OpenRouterProvider

BASE = "https://openrouter.ai/api/v1"
API_KEY = "test-key-123"


def _make_provider(handler: httpx.RequestHandler) -> OpenRouterProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return OpenRouterProvider(client=client, api_key=API_KEY, base_url=BASE)


async def _handler_list_models(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/api/v1/models"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    return httpx.Response(
        200,
        json={
            "data": [
                {"id": "openai/gpt-4", "name": "GPT-4", "context_length": 8192},
                {"id": "anthropic/claude-3", "name": "Claude 3", "context_length": 200000},
                {"id": "meta/llama-3", "name": "Llama 3"},
            ]
        },
    )


def test_list_models() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_list_models)
        models = await provider.list_models()
        assert len(models) == 3
        assert models[0].id == "openai/gpt-4"
        assert models[0].context_length == 8192
        assert models[2].context_length is None

    asyncio.run(_run())


async def _handler_complete_text(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/api/v1/chat/completions"
    body = json.loads(request.content)
    assert body["model"] == "openai/gpt-4"
    assert len(body["messages"]) == 2
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello! How can I help?"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
        },
    )


def test_complete_text() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_complete_text)
        result = await provider.complete(
            model="openai/gpt-4",
            messages=[
                Message(role="system", content="You are helpful."),
                Message(role="user", content="Say hi"),
            ],
        )
        assert result.content == "Hello! How can I help?"
        assert result.tool_calls == []
        assert result.finish_reason == "stop"
        assert result.usage["total_tokens"] == 18

    asyncio.run(_run())


async def _handler_complete_tools(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    assert "tools" in body
    assert body["tool_choice"] == "auto"
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc123",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"city": "Tokyo"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35},
        },
    )


def test_complete_with_tool_calls() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_complete_tools)
        result = await provider.complete(
            model="openai/gpt-4",
            messages=[Message(role="user", content="What is the weather in Tokyo?")],
            tools=[ToolSpec(name="get_weather", description="Get weather", parameters={"type": "object"})],
        )
        assert result.content is None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_weather"
        assert result.tool_calls[0].arguments == {"city": "Tokyo"}
        assert result.tool_calls[0].id == "call_abc123"
        assert result.finish_reason == "tool_calls"

    asyncio.run(_run())


async def _handler_stream(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    assert body["stream"] is True
    sse_lines = [
        'data: {"choices":[{"delta":{"content":"Hello"},"index":0}]}\n\n',
        'data: {"choices":[{"delta":{"content":" world"},"index":0}]}\n\n',
        'data: {"choices":[{"delta":{},"index":0}]}\n\n',
        "data: [DONE]\n\n",
    ]
    return httpx.Response(200, content="".join(sse_lines), headers={"content-type": "text/event-stream"})


def test_stream_complete() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_stream)
        chunks: list[str] = []
        async for chunk in provider.stream_complete(
            model="openai/gpt-4",
            messages=[Message(role="user", content="Say hi")],
        ):
            chunks.append(chunk)
        assert chunks == ["Hello", " world"]

    asyncio.run(_run())


async def _handler_auth_error(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, json={"error": {"message": "Invalid API key"}})


def test_auth_error() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_auth_error)
        with pytest.raises(ValueError, match="Invalid OpenRouter API key"):
            await provider.complete(
                model="openai/gpt-4",
                messages=[Message(role="user", content="Hi")],
            )

    asyncio.run(_run())


async def _handler_rate_limit(request: httpx.Request) -> httpx.Response:
    return httpx.Response(429, json={"error": {"message": "Rate limited"}})


def test_rate_limit_error() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_rate_limit)
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            await provider.complete(
                model="openai/gpt-4",
                messages=[Message(role="user", content="Hi")],
            )

    asyncio.run(_run())
