"""Tests for the z.ai (Zhipu / BigModel, GLM) provider (ADR-0013).

z.ai speaks the OpenAI Chat Completions dialect, so :class:`ZaiProvider` is a
thin subclass of :class:`OpenAICompatibleProvider`. These tests cover the two
z.ai specifics: the hardcoded GLM model catalog and ``reasoning_content``
collection (thinking models) in both ``complete`` and ``stream_complete``.
"""

from __future__ import annotations

import asyncio
import json

import httpx

from catalog.llm.base import Message
from catalog.llm.zai import DEFAULT_ZAI_MODEL, ZaiProvider

BASE = "https://api.z.ai/api/paas/v4"
API_KEY = "zai-jwt-token"


def _make_provider(
    handler: httpx.RequestHandler,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.5,
) -> ZaiProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return ZaiProvider(
        client=client,
        api_key=API_KEY,
        base_url=BASE,
        max_retries=max_retries,
        backoff_base=backoff_base,
    )


def test_list_models_returns_hardcoded_catalog() -> None:
    async def _run() -> None:
        transport = httpx.MockTransport(lambda req: httpx.Response(404))
        client = httpx.AsyncClient(transport=transport)
        provider = ZaiProvider(client=client, api_key=API_KEY, base_url=BASE)
        models = await provider.list_models()
        ids = [m.id for m in models]
        assert DEFAULT_ZAI_MODEL in ids
        assert "glm-5.2" in ids
        assert "glm-4.7" in ids
        assert "glm-4.6" in ids
        assert "glm-4.5" in ids
        assert "glm-4.5-x" not in ids
        assert "glm-4-plus" not in ids
        glm52 = next(m for m in models if m.id == "glm-5.2")
        assert glm52.context_length == 1048576
        assert glm52.name == "GLM-5.2"
        assert glm52.supports_reasoning is True
        assert glm52.reasoning_variants == ["high", "max"]
        models2 = await provider.list_models()
        assert models is not models2
        assert [m.id for m in models2] == ids

    asyncio.run(_run())


async def _handler_complete_reasoning(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/api/paas/v4/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    body = json.loads(request.content)
    assert body["model"] == "glm-5.2"
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "max"
    assert "reasoning" not in body
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Paris",
                        "reasoning_content": "The capital of France is Paris.",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": 10},
        },
    )


def test_complete_collects_reasoning() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_complete_reasoning)
        result = await provider.complete(
            model="glm-5.2",
            messages=[Message(role="user", content="Capital of France?")],
            reasoning="max",
        )
        assert result.content == "Paris"
        assert result.reasoning == "The capital of France is Paris."
        assert result.finish_reason == "stop"

    asyncio.run(_run())


def test_complete_strips_zai_model_prefix() -> None:
    async def _run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["model"] == "glm-4.6"
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {},
                },
            )

        provider = _make_provider(handler)
        result = await provider.complete(
            model="zai/glm-4.6",
            messages=[Message(role="user", content="hi")],
        )
        assert result.content == "ok"

    asyncio.run(_run())


async def _handler_stream_reasoning(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    assert body["stream"] is True
    assert body["model"] == "glm-4.6"
    sse_lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"step 1"},"index":0}]}\n\n',
        'data: {"choices":[{"delta":{"content":"Par"},"index":0}]}\n\n',
        'data: {"choices":[{"delta":{"content":"is"},"index":0}]}\n\n',
        "data: [DONE]\n\n",
    ]
    return httpx.Response(
        200, content="".join(sse_lines), headers={"content-type": "text/event-stream"}
    )


def test_stream_collects_content_and_reasoning() -> None:
    async def _run() -> None:
        provider = _make_provider(_handler_stream_reasoning)
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        async for delta in provider.stream_complete(
            model="glm-4.6", messages=[Message(role="user", content="hi")]
        ):
            if delta.content:
                content_parts.append(delta.content)
            if delta.reasoning:
                reasoning_parts.append(delta.reasoning)
        assert content_parts == ["Par", "is"]
        assert reasoning_parts == ["step 1"]

    asyncio.run(_run())


def test_auth_error_message_is_zai_specific() -> None:
    async def _run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "invalid jwt"}})

        provider = _make_provider(handler, max_retries=3, backoff_base=0)
        try:
            await provider.complete(
                model="glm-4.6", messages=[Message(role="user", content="hi")]
            )
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "ZAI_API_KEY" in str(exc)

    asyncio.run(_run())
