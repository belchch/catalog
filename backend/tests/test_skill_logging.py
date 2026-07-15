"""Tests for skill-execution stdout logging (plan: skill-execution-logging).

Covers:
- the agent loop logs one line per non-token action (step/tool_call/tool_result/finish);
- the token stream is NOT logged;
- the apply loop logs start/verify/persist/done with the right fields;
- :class:`ContextFilter` renders the prompt-log contextvars into ``record.ctx``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest

from app.agent.events import (
    FinishEvent,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    VerifyEvent,
)
from app.agent.logging import _trunc, log_agent_event
from app.agent.registry import ToolRegistry
from app.agent.runner import run_agent, run_agent_collect
from app.documents.ingest import ingest_file
from app.documents.tools import build_document_tools
from app.llm.base import CompletionResult, LLMProvider, Message, ModelInfo, ToolCall, ToolSpec
from app.logging_config import ContextFilter
from app.llm.log_context import prompt_log_context
from app.skills.apply import apply_skill_collect
from app.skills.config import SkillConfig, VerifyCheck
from app.skills.repo_skill import create_skill
from app.storage.db import Database


# --------------------------------------------------------------------------- #
# Shared helpers (mirror tests/test_agent.py + tests/test_apply.py)
# --------------------------------------------------------------------------- #


class FakeProvider:
    """In-process provider implementing the LLMProvider protocol."""

    def __init__(
        self,
        script: list[CompletionResult] | None = None,
        stream_script: list[str] | None = None,
    ) -> None:
        self.script: list[CompletionResult] = list(script or [])
        self.stream_script: list[str] = list(stream_script or [])

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
    ) -> CompletionResult:
        return self.script.pop(0)

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
    ):  # type: ignore[no-untyped-def]
        for chunk in self.stream_script:
            yield chunk


# Static check: FakeProvider satisfies the protocol.
_PROVIDER: LLMProvider = FakeProvider()  # type: ignore[assignment]


def _doc_spec() -> ToolSpec:
    return ToolSpec(
        name="read_doc",
        description="Read a document by path",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )


async def _read_doc(**arguments: Any) -> dict:
    return {"path": arguments["path"], "content": "hello world"}


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(_doc_spec(), _read_doc)
    return reg


def _messages() -> list[Message]:
    return [Message(role="user", content="read a")]


def _apply_skill(
    *,
    name: str = "summarizer",
    verify_checks: list[VerifyCheck] | None = None,
    max_retries: int = 2,
) -> SkillConfig:
    return SkillConfig(
        name=name,
        description="test skill",
        system_prompt="You are a summarizer.",
        allowed_tools=["read_document"],
        model="test/model",
        temperature=0.0,
        max_iterations=4,
        max_retries=max_retries,
        verify_checks=verify_checks if verify_checks is not None else [],
    )


@pytest.fixture()
def db() -> Database:
    d = Database(":memory:")
    d.init_schema()
    return d


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_runner_logs_each_action(caplog: pytest.LogCaptureFixture) -> None:
    """run_agent emits one log line per non-token action."""
    caplog.set_level(logging.INFO, logger="app")

    async def _run() -> None:
        provider = FakeProvider(
            script=[
                CompletionResult(
                    content=None,
                    tool_calls=[ToolCall(id="call_1", name="read_doc", arguments={"path": "a"})],
                    finish_reason="tool_calls",
                ),
                CompletionResult(content="done", tool_calls=[], finish_reason="stop"),
            ]
        )
        _, _, _ = await run_agent_collect(
            provider=provider,
            model="m",
            system_prompt="sys",
            messages=_messages(),
            tools=_registry(),
            use_stream=False,
        )

    asyncio.run(_run())

    messages = [r.getMessage() for r in caplog.records]
    joined = "\n".join(messages)
    assert any(m.startswith("agent iteration") for m in messages), joined
    assert any(m.startswith("tool_call name=read_doc") for m in messages), joined
    assert any(
        m.startswith("tool_result name=read_doc ok=True") for m in messages
    ), joined
    assert any(m.startswith("finish reason=stop") for m in messages), joined


def test_tokens_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Stream mode emits TokenEvents but they never reach the log."""
    caplog.set_level(logging.INFO, logger="app")

    async def _run() -> None:
        provider = FakeProvider(stream_script=["Hel", "lo"])
        events = []
        async for event in run_agent(
            provider=provider,
            model="m",
            system_prompt="sys",
            messages=_messages(),
            tools=_registry(),
            use_stream=True,
        ):
            events.append(event)
        # Sanity: tokens really were emitted.
        assert [e.delta for e in events if isinstance(e, TokenEvent)] == ["Hel", "lo"]
        assert isinstance(events[-1], FinishEvent)

    asyncio.run(_run())

    messages = [r.getMessage() for r in caplog.records]
    # No token-specific log line is ever emitted (TokenEvent is skipped)...
    assert not any("token" in m for m in messages), messages
    # ...and the individual deltas are never logged standalone (the only place
    # "Hello" appears is inside the assembled finish text, never as "Hel"/"lo"
    # chunks). The finish line carries the full assembled text.
    finish_lines = [m for m in messages if m.startswith("finish reason=stop")]
    assert finish_lines, messages
    assert "text=Hello" in finish_lines[0]


def test_apply_logging(
    db: Database, workspace: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """apply_skill_collect logs start/verify/persist/done with the right fields."""
    caplog.set_level(logging.INFO, logger="app")

    skill = _apply_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = ingest_file(db, workspace, filename="input.md", content=b"source text").id
    provider = FakeProvider(
        script=[CompletionResult(content="# Summary\n\nGreat document.", tool_calls=[], finish_reason="stop")]
    )

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_id=input_doc_id,
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None

    messages = [r.getMessage() for r in caplog.records]
    joined = "\n".join(messages)

    assert any(
        m.startswith("apply_skill start") and f"skill_id={skill_id}" in m and f"input_doc={input_doc_id}" in m
        for m in messages
    ), joined
    assert any(
        m.startswith("verify attempt=1 passed=True") for m in messages
    ), joined
    assert any(
        m.startswith(f"apply_skill persisted output_doc_id={result.output_doc_id}")
        for m in messages
    ), joined
    assert any(
        m.startswith("apply_skill done status=ok") for m in messages
    ), joined


def test_context_filter_formats_context() -> None:
    """ContextFilter renders bound contextvars into record.ctx."""
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    flt = ContextFilter()
    with prompt_log_context(run_id="R1", purpose="apply_skill"):
        assert flt.filter(record) is True
    ctx = record.ctx
    assert "run_id=R1" in ctx
    assert "purpose=apply_skill" in ctx


def test_context_filter_empty_when_no_context() -> None:
    """With nothing bound, record.ctx is an empty string (brackets stay [])."""
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    flt = ContextFilter()
    assert flt.filter(record) is True
    assert record.ctx == ""


def test_trunc_truncates_long_payloads() -> None:
    """_trunc bounds the serialized form and marks truncation."""
    long_str = "x" * 500
    out = _trunc(long_str, limit=10)
    assert out.endswith("…[truncated]")
    assert out.startswith("x" * 10)

    # dict/list are JSON-encoded.
    payload = {"a": 1, "b": [2, 3]}
    assert _trunc(payload) == '{"a": 1, "b": [2, 3]}'

    # Short values pass through unchanged.
    assert _trunc("hi") == "hi"
    assert _trunc(42) == "42"


def test_log_agent_event_handles_all_event_types(caplog: pytest.LogCaptureFixture) -> None:
    """Every non-token event type maps to exactly one log line; token is skipped."""
    caplog.set_level(logging.INFO, logger="app")

    from app.skills.verify import VerifyResult

    log_agent_event(StepEvent(1))
    log_agent_event(ToolCallEvent("id", "read_doc", {"path": "a"}))
    log_agent_event(ToolResultEvent("id", "read_doc", True, {"ok": 1}))
    log_agent_event(VerifyEvent(1, VerifyResult(passed=True, failures=[])))
    log_agent_event(FinishEvent("done", "stop", capped=False, usage={}))
    # Token must NOT produce a record.
    log_agent_event(TokenEvent("Hel"))

    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 5
    assert messages[0].startswith("agent iteration 1")
    assert messages[-1].startswith("finish reason=stop")
