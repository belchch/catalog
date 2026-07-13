from __future__ import annotations

import asyncio
from typing import Any

from app.agent.events import (
    FinishEvent,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.agent.registry import ToolRegistry
from app.agent.runner import run_agent, run_agent_collect
from app.llm.base import CompletionResult, LLMProvider, Message, ModelInfo, ToolCall, ToolSpec


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


async def _drain(gen: Any) -> list[Any]:
    out: list[Any] = []
    async for event in gen:
        out.append(event)
    return out


def test_loop_with_tool_calls() -> None:
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
        events = await _drain(
            run_agent(
                provider=provider,
                model="m",
                system_prompt="sys",
                messages=[Message(role="user", content="read a")],
                tools=_registry(),
                use_stream=False,
            )
        )

        # Event sequence: Step, ToolCall, ToolResult, Step, Finish.
        assert isinstance(events[0], StepEvent)
        assert isinstance(events[1], ToolCallEvent)
        assert isinstance(events[1].name, str) and events[1].name == "read_doc"
        assert isinstance(events[2], ToolResultEvent)
        assert events[2].ok is True
        assert events[2].result == {"path": "a", "content": "hello world"}
        finish = events[-1]
        assert isinstance(finish, FinishEvent)
        assert finish.text == "done"
        assert finish.capped is False

        # Trace mirrors the loop: llm, tool_call, tool_result, llm.
        _, trace, capped = await run_agent_collect(
            provider=FakeProvider(
                script=[
                    CompletionResult(
                        content=None,
                        tool_calls=[
                            ToolCall(id="call_1", name="read_doc", arguments={"path": "a"})
                        ],
                        finish_reason="tool_calls",
                    ),
                    CompletionResult(content="done", tool_calls=[], finish_reason="stop"),
                ]
            ),
            model="m",
            system_prompt="sys",
            messages=[Message(role="user", content="read a")],
            tools=_registry(),
            use_stream=False,
        )
        kinds = [e.kind for e in trace.entries]
        assert kinds == ["llm", "tool_call", "tool_result", "llm"]
        assert capped is False

    asyncio.run(_run())


def test_unknown_tool_returns_error() -> None:
    async def _run() -> None:
        provider = FakeProvider(
            script=[
                CompletionResult(
                    content=None,
                    tool_calls=[
                        ToolCall(id="call_1", name="nope", arguments={})
                    ],
                    finish_reason="tool_calls",
                ),
                CompletionResult(content="recovered", tool_calls=[], finish_reason="stop"),
            ]
        )
        events = await _drain(
            run_agent(
                provider=provider,
                model="m",
                system_prompt="sys",
                messages=[Message(role="user", content="x")],
                tools=_registry(),
                use_stream=False,
            )
        )
        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].ok is False
        assert "error: unknown tool" in str(result_events[0].result)
        finish = events[-1]
        assert isinstance(finish, FinishEvent)
        assert finish.text == "recovered"
        assert finish.capped is False

    asyncio.run(_run())


def test_invalid_args_validation() -> None:
    calls: list[dict] = []

    async def _spy_read(**arguments: Any) -> dict:
        calls.append(arguments)
        return {"ok": True}

    reg = ToolRegistry()
    reg.register(_doc_spec(), _spy_read)

    async def _run() -> None:
        provider = FakeProvider(
            script=[
                CompletionResult(
                    content=None,
                    tool_calls=[
                        ToolCall(id="call_1", name="read_doc", arguments={"path": 123})
                    ],
                    finish_reason="tool_calls",
                ),
                CompletionResult(content="after", tool_calls=[], finish_reason="stop"),
            ]
        )
        events = await _drain(
            run_agent(
                provider=provider,
                model="m",
                system_prompt="sys",
                messages=[Message(role="user", content="x")],
                tools=reg,
                use_stream=False,
            )
        )
        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].ok is False
        assert "error: invalid args" in str(result_events[0].result)
        # Tool must not have been invoked.
        assert calls == []

    asyncio.run(_run())


def test_max_iterations_cap() -> None:
    async def _run() -> None:
        # Every response requests a tool call -> never stops on its own.
        looping = CompletionResult(
            content=None,
            tool_calls=[ToolCall(id="call_1", name="read_doc", arguments={"path": "a"})],
            finish_reason="tool_calls",
        )
        provider = FakeProvider(script=[looping, looping, looping])
        events = await _drain(
            run_agent(
                provider=provider,
                model="m",
                system_prompt="sys",
                messages=[Message(role="user", content="x")],
                tools=_registry(),
                use_stream=False,
                max_iterations=3,
            )
        )
        finish = events[-1]
        assert isinstance(finish, FinishEvent)
        assert finish.capped is True
        assert finish.finish_reason == "capped"
        # Three iterations -> three StepEvents.
        assert sum(1 for e in events if isinstance(e, StepEvent)) == 3

    asyncio.run(_run())


def test_no_tools_immediate_finish() -> None:
    async def _run() -> None:
        provider = FakeProvider(
            script=[CompletionResult(content="hi", tool_calls=[], finish_reason="stop")]
        )
        events = await _drain(
            run_agent(
                provider=provider,
                model="m",
                system_prompt="sys",
                messages=[Message(role="user", content="x")],
                tools=_registry(),
                use_stream=False,
            )
        )
        assert isinstance(events[0], StepEvent)
        finish = events[-1]
        assert isinstance(finish, FinishEvent)
        assert finish.text == "hi"
        assert finish.capped is False
        # Single iteration.
        assert sum(1 for e in events if isinstance(e, StepEvent)) == 1

    asyncio.run(_run())


def test_tool_exception_wrapped() -> None:
    async def _boom(**arguments: Any) -> dict:
        raise RuntimeError("boom!")

    reg = ToolRegistry()
    reg.register(_doc_spec(), _boom)

    async def _run() -> None:
        provider = FakeProvider(
            script=[
                CompletionResult(
                    content=None,
                    tool_calls=[
                        ToolCall(id="call_1", name="read_doc", arguments={"path": "a"})
                    ],
                    finish_reason="tool_calls",
                ),
                CompletionResult(content="after", tool_calls=[], finish_reason="stop"),
            ]
        )
        events = await _drain(
            run_agent(
                provider=provider,
                model="m",
                system_prompt="sys",
                messages=[Message(role="user", content="x")],
                tools=reg,
                use_stream=False,
            )
        )
        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].ok is False
        assert "error:" in str(result_events[0].result)
        assert "boom" in str(result_events[0].result)

    asyncio.run(_run())


def test_run_agent_collect() -> None:
    async def _run() -> None:
        provider = FakeProvider(
            script=[
                CompletionResult(
                    content=None,
                    tool_calls=[
                        ToolCall(id="call_1", name="read_doc", arguments={"path": "a"})
                    ],
                    finish_reason="tool_calls",
                ),
                CompletionResult(content="final", tool_calls=[], finish_reason="stop"),
            ]
        )
        text, trace, capped = await run_agent_collect(
            provider=provider,
            model="m",
            system_prompt="sys",
            messages=[Message(role="user", content="x")],
            tools=_registry(),
            use_stream=False,
        )
        assert text == "final"
        assert capped is False
        assert [e.kind for e in trace.entries] == ["llm", "tool_call", "tool_result", "llm"]
        # to_json must be valid JSON with the expected shape.
        import json

        parsed = json.loads(trace.to_json())
        assert parsed[0]["kind"] == "llm"
        assert parsed[1]["kind"] == "tool_call"

    asyncio.run(_run())


def test_stream_mode_emits_tokens() -> None:
    async def _run() -> None:
        provider = FakeProvider(stream_script=["Hel", "lo"])
        events = await _drain(
            run_agent(
                provider=provider,
                model="m",
                system_prompt="sys",
                messages=[Message(role="user", content="x")],
                tools=_registry(),
                use_stream=True,
            )
        )
        tokens = [e for e in events if isinstance(e, TokenEvent)]
        assert [t.delta for t in tokens] == ["Hel", "lo"]
        finish = events[-1]
        assert isinstance(finish, FinishEvent)
        assert finish.text == "Hello"
        assert finish.capped is False

    asyncio.run(_run())


def test_registry_specs_and_lookup() -> None:
    reg = _registry()
    assert reg.names() == ["read_doc"]
    specs = reg.specs()
    assert len(specs) == 1
    assert specs[0].name == "read_doc"
    entry = reg.get("read_doc")
    assert entry is not None
    spec, func = entry
    assert spec.name == "read_doc"
    assert callable(func)
    assert reg.get("missing") is None
