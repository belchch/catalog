"""Tests for prompt logging (plan: 1784059101171-prompt-logging).

Covers: disabled = no files; enabled writes a schema-correct JSON; contextvars
land in the ``context`` block; the stream path records ``assembled_text``; and
write failures are swallowed (warning only) so logging never breaks an LLM call.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from catalog import config
from catalog.llm.base import Message, ToolSpec
from catalog.llm.log_context import prompt_log_context
from catalog.llm.openrouter import OpenRouterProvider
from catalog.llm.prompt_log import write_prompt_log


@pytest.fixture
def log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Enable prompt logging into a tmp dir and return that dir path."""
    monkeypatch.setattr(config, "PROMPT_LOG_ENABLED", True)
    target = tmp_path / "prompt_logs"
    monkeypatch.setattr(config, "PROMPT_LOG_DIR", str(target))
    return target


def _find_log(log_dir: Path) -> Path:
    files = list(log_dir.rglob("*.json"))
    assert len(files) == 1, f"expected exactly one log file, got {files}"
    return files[0]


def _basic_messages() -> list[Message]:
    return [
        Message(role="system", content="You are helpful."),
        Message(role="user", content="Say hi"),
    ]


def test_disabled_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With PROMPT_LOG_ENABLED=false, no file is written."""
    monkeypatch.setattr(config, "PROMPT_LOG_ENABLED", False)
    monkeypatch.setattr(config, "PROMPT_LOG_DIR", str(tmp_path / "prompt_logs"))

    async def _run() -> None:
        await write_prompt_log(
            provider="openrouter",
            model="m",
            messages=_basic_messages(),
            tools=None,
            temperature=0.0,
            tool_choice="auto",
            stream=False,
            response={"content": "hi", "tool_calls": [], "finish_reason": "stop", "usage": {}},
            error=None,
            latency_ms=5,
            base_url="https://openrouter.ai/api/v1",
            url="https://openrouter.ai/api/v1/chat/completions",
        )

    asyncio.run(_run())
    assert not (tmp_path / "prompt_logs").exists() or not list(
        (tmp_path / "prompt_logs").rglob("*.json")
    )


def test_enabled_writes_json(log_dir: Path) -> None:
    """Enabled: a JSON file is written with the full schema and payload."""

    async def _run() -> None:
        await write_prompt_log(
            provider="openrouter",
            model="openai/gpt-4",
            messages=_basic_messages(),
            tools=[ToolSpec(name="get_weather", description="Get weather", parameters={"type": "object"})],
            temperature=0.0,
            tool_choice="auto",
            stream=False,
            response={
                "content": "Hello!",
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {"total_tokens": 18},
            },
            error=None,
            latency_ms=42,
            base_url="https://openrouter.ai/api/v1",
            url="https://openrouter.ai/api/v1/chat/completions",
            http_status=200,
        )

    asyncio.run(_run())

    path = _find_log(log_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 2
    assert payload["provider"] == "openrouter"
    assert payload["request"]["model"] == "openai/gpt-4"
    assert payload["request"]["temperature"] == 0.0
    assert payload["request"]["tool_choice"] == "auto"
    assert payload["request"]["stream"] is False
    assert payload["request"]["base_url"] == "https://openrouter.ai/api/v1"
    assert payload["request"]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert payload["request"]["messages_count"] == 2
    assert payload["request"]["tools_count"] == 1
    # Full messages serialized.
    assert len(payload["request"]["messages"]) == 2
    assert payload["request"]["messages"][0] == {"role": "system", "content": "You are helpful."}
    assert payload["request"]["messages"][1] == {"role": "user", "content": "Say hi"}
    # Tools serialized to the OpenRouter shape.
    assert payload["request"]["tools"][0]["function"]["name"] == "get_weather"
    # Response + meta.
    assert payload["response"]["content"] == "Hello!"
    assert payload["response"]["usage"]["total_tokens"] == 18
    assert payload["meta"]["latency_ms"] == 42
    assert payload["meta"]["ok"] is True
    assert payload["meta"]["error"] is None
    assert payload["meta"]["http_status"] == 200
    # request_id / timestamp present; file name embeds the request_id.
    assert payload["request_id"]
    assert payload["timestamp"]
    assert payload["request_id"] in path.name
    # No HTTP headers leaked.
    assert "Authorization" not in json.dumps(payload)


def test_contextvars_in_meta(log_dir: Path) -> None:
    """session_id/purpose bound via prompt_log_context appear in the context block."""

    async def _run() -> None:
        with prompt_log_context(session_id="s1", purpose="planner"):
            await write_prompt_log(
                provider="openrouter",
                model="m",
                messages=_basic_messages(),
                tools=None,
                temperature=0.0,
                tool_choice="auto",
                stream=False,
                response={"content": "x", "tool_calls": [], "finish_reason": "stop", "usage": {}},
                error=None,
                latency_ms=1,
                base_url="https://openrouter.ai/api/v1",
                url="https://openrouter.ai/api/v1/chat/completions",
            )

    asyncio.run(_run())

    payload = json.loads(_find_log(log_dir).read_text(encoding="utf-8"))
    assert payload["context"]["session_id"] == "s1"
    assert payload["context"]["purpose"] == "planner"


def test_stream_logs_assembled_text(log_dir: Path) -> None:
    """The stream path records the assembled text in the response."""

    sse_lines = [
        'data: {"choices":[{"delta":{"content":"Hello"},"index":0}]}\n\n',
        'data: {"choices":[{"delta":{"content":" world"},"index":0}]}\n\n',
        "data: [DONE]\n\n",
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content="".join(sse_lines),
            headers={"content-type": "text/event-stream"},
        )

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        provider = OpenRouterProvider(client=client, api_key="k", base_url="https://x/api/v1")
        chunks: list[str] = []
        async for delta in provider.stream_complete(
            model="openai/gpt-4",
            messages=[Message(role="user", content="Say hi")],
        ):
            if delta.content:
                chunks.append(delta.content)
        assert chunks == ["Hello", " world"]

    asyncio.run(_run())

    payload = json.loads(_find_log(log_dir).read_text(encoding="utf-8"))
    assert payload["request"]["stream"] is True
    assert payload["request"]["base_url"] == "https://x/api/v1"
    assert payload["request"]["url"] == "https://x/api/v1/chat/completions"
    assert payload["response"]["assembled_text"] == "Hello world"
    assert payload["response"]["finish_reason"] == "stop"
    assert payload["meta"]["ok"] is True
    assert payload["meta"]["http_status"] == 200


def test_write_failure_swallowed(
    log_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write failure (os.replace raises) is swallowed — only a warning."""

    def _boom(src: str, dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("catalog.llm.prompt_log.os.replace", _boom)

    async def _run() -> None:
        # Must not raise.
        await write_prompt_log(
            provider="openrouter",
            model="m",
            messages=_basic_messages(),
            tools=None,
            temperature=0.0,
            tool_choice="auto",
            stream=False,
            response={"content": "x", "tool_calls": [], "finish_reason": "stop", "usage": {}},
            error=None,
            latency_ms=1,
            base_url="https://openrouter.ai/api/v1",
            url="https://openrouter.ai/api/v1/chat/completions",
        )

    asyncio.run(_run())
    # No complete file landed (the tmp may exist, but no final .json).
    assert list(log_dir.rglob("*.json")) == []


def test_error_path_logged(log_dir: Path) -> None:
    """A provider error is logged with ok=false and the error string, then re-raised."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        provider = OpenRouterProvider(
            client=client, api_key="k", base_url="https://x/api/v1", max_retries=0
        )
        with pytest.raises(ValueError, match="Invalid OpenRouter API key"):
            await provider.complete(
                model="openai/gpt-4",
                messages=[Message(role="user", content="Hi")],
            )

    asyncio.run(_run())

    payload = json.loads(_find_log(log_dir).read_text(encoding="utf-8"))
    assert payload["meta"]["ok"] is False
    assert "Invalid OpenRouter API key" in payload["meta"]["error"]
    assert payload["response"] is None
    assert payload["request"]["base_url"] == "https://x/api/v1"
    assert payload["request"]["url"] == "https://x/api/v1/chat/completions"
