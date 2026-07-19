"""Tests for the shared :class:`OpenAICompatibleProvider` base class (ADR-0013).

Covers the contract every OpenAI-Chat-Completions dialect shares: retry/backoff
on 429/5xx, an immediate (non-retried) 401 with a provider-specific message,
tool-call parsing, SSE ``[DONE]`` termination, and ``reasoning_content``
collection in both ``complete`` and ``stream_complete``.

The base class is concrete enough to instantiate directly (it has no abstract
methods), so these tests exercise it as-is — subclasses (OpenRouter, z.ai) only
override ``provider_name``/``base_url``/``list_models``/``auth_error_message``.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.llm.base import Message, StreamDelta, ToolSpec
from app.llm.openai_compatible import OpenAICompatibleProvider

BASE = "https://example.test/api/v1"
API_KEY = "test-key-123"
AUTH_ERROR = "Invalid test API key — check TEST_API_KEY in .env"


def _make_provider(
    handler: httpx.RequestHandler,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.5,
) -> OpenAICompatibleProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return OpenAICompatibleProvider(
        client=client,
        api_key=API_KEY,
        base_url=BASE,
        provider_name="test",
        max_retries=max_retries,
        backoff_base=backoff_base,
        auth_error_message=AUTH_ERROR,
    )


# --------------------------------------------------------------------------- #
# complete — text + reasoning_content
# --------------------------------------------------------------------------- #


async def _handler_complete_with_reasoning(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/api/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "The answer is 42.",
                        "reasoning_content": "First I consider...",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
        },
    )


def test_complete_collects_reasoning_content() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_complete_with_reasoning)
        result = await provider.complete(
            model="m",
            messages=[Message(role="user", content="What is the answer?")],
        )
        assert result.content == "The answer is 42."
        assert result.reasoning == "First I consider..."
        assert result.finish_reason == "stop"
        assert result.usage["total_tokens"] == 9

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# complete — reasoning variant reaches the request body (CATALOG-6)
# --------------------------------------------------------------------------- #


def test_complete_sends_reasoning_variant_in_body() -> None:
    async def _handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # The selected reasoning variant must reach the provider request body.
        assert body["reasoning"] == {"effort": "high"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {},
            },
        )

    async def _run() -> None:
        provider = _make_provider(_handler)
        await provider.complete(
            model="m",
            messages=[Message(role="user", content="hi")],
            reasoning="high",
        )

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# complete — tool_calls parsing
# --------------------------------------------------------------------------- #


async def _handler_complete_tools(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
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
                                "id": "call_1",
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
            "usage": {"total_tokens": 1},
        },
    )


def test_complete_parses_tool_calls() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_complete_tools)
        result = await provider.complete(
            model="m",
            messages=[Message(role="user", content="weather?")],
            tools=[ToolSpec(name="get_weather", description="weather", parameters={"type": "object"})],
        )
        assert result.content is None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_weather"
        assert result.tool_calls[0].arguments == {"city": "Tokyo"}
        assert result.tool_calls[0].id == "call_1"
        assert result.finish_reason == "tool_calls"

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# 401 — provider-specific message, never retried
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("body", [{"error": {"message": "bad"}}, {}])
def test_auth_error_uses_provider_message(body: dict) -> None:
    async def _run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json=body)

        calls = {"n": 0}

        async def counting_handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return await handler(request)

        provider = _make_provider(counting_handler, max_retries=3, backoff_base=0)
        with pytest.raises(ValueError, match="Invalid test API key"):
            await provider.complete(
                model="m", messages=[Message(role="user", content="hi")]
            )
        # 401 must not be retried.
        assert calls["n"] == 1

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# Retry on 429 / 5xx then succeed
# --------------------------------------------------------------------------- #


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
            ],
            "usage": {"total_tokens": 1},
        },
    )


def test_retries_on_429_then_succeeds() -> None:
    async def _run() -> None:
        calls = {"n": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, json={"error": "rate"})
            return _ok_response()

        provider = _make_provider(handler, max_retries=2, backoff_base=0)
        result = await provider.complete(
            model="m", messages=[Message(role="user", content="hi")]
        )
        assert result.content == "ok"
        assert calls["n"] == 2

    asyncio.run(_run())


def test_retries_on_5xx_then_succeeds() -> None:
    async def _run() -> None:
        calls = {"n": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(503, json={"error": "down"})
            return _ok_response()

        provider = _make_provider(handler, max_retries=3, backoff_base=0)
        result = await provider.complete(
            model="m", messages=[Message(role="user", content="hi")]
        )
        assert result.content == "ok"
        assert calls["n"] == 3

    asyncio.run(_run())


def test_persistent_429_raises_runtime_error() -> None:
    async def _run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "rate"})

        provider = _make_provider(handler, max_retries=1, backoff_base=0)
        with pytest.raises(RuntimeError, match="429"):
            await provider.complete(
                model="m", messages=[Message(role="user", content="hi")]
            )

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# Streaming — SSE [DONE] + reasoning_content
# --------------------------------------------------------------------------- #


async def _handler_stream_with_reasoning(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    assert body["stream"] is True
    sse_lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"thinking..."},"index":0}]}\n\n',
        'data: {"choices":[{"delta":{"content":"Hello"},"index":0}]}\n\n',
        'data: {"choices":[{"delta":{"content":" world"},"index":0}]}\n\n',
        'data: {"choices":[{"delta":{},"index":0}]}\n\n',
        "data: [DONE]\n\n",
    ]
    return httpx.Response(
        200, content="".join(sse_lines), headers={"content-type": "text/event-stream"}
    )


def test_stream_collects_content_and_reasoning() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_stream_with_reasoning)
        chunks: list[StreamDelta] = []
        async for delta in provider.stream_complete(
            model="m", messages=[Message(role="user", content="hi")]
        ):
            chunks.append(delta)
        # [DONE] terminates the stream; the empty delta is not yielded.
        contents = [d.content for d in chunks if d.content]
        reasoning = [d.reasoning for d in chunks if d.reasoning]
        assert contents == ["Hello", " world"]
        assert reasoning == ["thinking..."]

    asyncio.run(_run())


def test_stream_401_raises_provider_error() -> None:
    async def _run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        provider = _make_provider(handler)
        with pytest.raises(ValueError, match="Invalid test API key"):
            async for _ in provider.stream_complete(
                model="m", messages=[Message(role="user", content="hi")]
            ):
                pass

    asyncio.run(_run())


def test_complete_logs_provider_base_url_and_url(caplog: pytest.LogCaptureFixture) -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_complete_with_reasoning)
        with caplog.at_level("INFO", logger="app.llm"):
            await provider.complete(
                model="m",
                messages=[Message(role="user", content="What is the answer?")],
            )

    asyncio.run(_run())

    request_logs = [r.message for r in caplog.records if "complete request:" in r.message]
    response_logs = [r.message for r in caplog.records if "complete response:" in r.message]
    assert len(request_logs) == 1
    assert "provider=test" in request_logs[0]
    assert f"base_url={BASE}" in request_logs[0]
    assert f"url={BASE}/chat/completions" in request_logs[0]
    assert len(response_logs) == 1
    assert "http_status=200" in response_logs[0]
    assert f"url={BASE}/chat/completions" in response_logs[0]


def test_list_models_logs_provider_and_base_url(caplog: pytest.LogCaptureFixture) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "m1", "name": "Model 1", "context_length": 8}]},
        )

    async def _run() -> None:
        provider = _make_provider(handler)
        with caplog.at_level("INFO", logger="app.llm"):
            models = await provider.list_models()
        assert len(models) == 1

    asyncio.run(_run())

    logs = [r.message for r in caplog.records if "list_models:" in r.message]
    assert len(logs) == 1
    assert "provider=test" in logs[0]
    assert f"base_url={BASE}" in logs[0]
    assert f"url={BASE}/models" in logs[0]


def test_http_error_logs_url(caplog: pytest.LogCaptureFixture) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad model"}})

    async def _run() -> None:
        provider = _make_provider(handler, max_retries=0)
        with caplog.at_level("WARNING", logger="app.llm"):
            with pytest.raises(RuntimeError, match="bad model"):
                await provider.complete(
                    model="m", messages=[Message(role="user", content="hi")]
                )

    asyncio.run(_run())

    warnings = [r.message for r in caplog.records if "complete HTTP 400" in r.message]
    assert len(warnings) == 1
    assert f"url={BASE}/chat/completions" in warnings[0]
    assert "provider=test" in warnings[0]
