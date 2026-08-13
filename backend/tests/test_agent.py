from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from catalog.agent.events import (
    FinishEvent,
    ReasoningEvent,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from catalog.agent.registry import ToolRegistry
from catalog.agent.runner import run_agent, run_agent_collect
from catalog.llm.base import (
    CompletionResult,
    LLMProvider,
    Message,
    ModelInfo,
    StreamDelta,
    ToolCall,
    ToolSpec,
)


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
        reasoning: str = "",
    ) -> CompletionResult:
        return self.script.pop(0)

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        reasoning: str = "",
    ) -> Any:
        for chunk in self.stream_script:
            yield StreamDelta(content=chunk)


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


def test_reasoning_event_non_stream() -> None:
    """A non-stream completion carrying reasoning emits a ReasoningEvent.

    CATALOG-24/16: the runner surfaces the model's chain-of-thought as its own
    trace event (right after the StepEvent, before the FinishEvent) so the
    apply stream can render it instead of burying it in the trace data.
    """

    async def _run() -> None:
        provider = FakeProvider(
            script=[
                CompletionResult(
                    content="answer",
                    tool_calls=[],
                    finish_reason="stop",
                    reasoning="step-by-step thinking",
                )
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
        reasoning = [e for e in events if isinstance(e, ReasoningEvent)]
        assert len(reasoning) == 1
        assert reasoning[0].text == "step-by-step thinking"
        # Reasoning is emitted before the finish, after the step.
        assert isinstance(events[0], StepEvent)
        assert isinstance(events[-1], FinishEvent)
        assert events.index(reasoning[0]) < events.index(events[-1])

    asyncio.run(_run())


def test_reasoning_event_stream() -> None:
    """A streaming completion carrying reasoning emits a ReasoningEvent too."""

    class _ReasoningStreamProvider(FakeProvider):
        async def stream_complete(
            self,
            model: str,
            messages: list[Message],
            tools: list[ToolSpec] | None = None,
            temperature: float = 0.0,
            reasoning: str = "",
        ) -> Any:
            yield StreamDelta(reasoning="thinking...")
            yield StreamDelta(content="Hel")
            yield StreamDelta(content="lo")

    async def _run() -> None:
        provider = _ReasoningStreamProvider()
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
        reasoning = [e for e in events if isinstance(e, ReasoningEvent)]
        assert len(reasoning) == 1
        assert reasoning[0].text == "thinking..."
        finish = events[-1]
        assert isinstance(finish, FinishEvent)
        assert finish.text == "Hello"

    asyncio.run(_run())


def test_no_reasoning_event_when_absent() -> None:
    """No ReasoningEvent is emitted when the provider returns no reasoning."""

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
        assert not any(isinstance(e, ReasoningEvent) for e in events)

    asyncio.run(_run())


def test_serialize_result_truncates_long_payloads() -> None:
    """_serialize_result bounds the LLM history: oversized payloads are
    truncated with a marker so a huge read_document cannot overflow the model
    context, while short payloads (str, dict, list) pass through unchanged."""
    from catalog.agent.runner import MAX_TOOL_RESULT_CHARS, _serialize_result

    short_str = "hello world"
    assert _serialize_result(short_str) == short_str

    small_dict = {"a": 1, "b": [2, 3]}
    assert _serialize_result(small_dict) == json.dumps(
        small_dict, ensure_ascii=False, default=str
    )

    huge = "x" * (MAX_TOOL_RESULT_CHARS * 3)
    out = _serialize_result(huge)
    assert out.startswith("x" * MAX_TOOL_RESULT_CHARS)
    assert "truncated" in out
    assert str(len(huge)) in out

    huge_list = [{"k": "y" * (MAX_TOOL_RESULT_CHARS + 500)}]
    full = json.dumps(huge_list, ensure_ascii=False, default=str)
    out_list = _serialize_result(huge_list)
    assert len(out_list) < len(full)
    assert "truncated" in out_list


# --------------------------------------------------------------------------- #
# Cancellation (CATALOG-11)
# --------------------------------------------------------------------------- #


class _BlockingProvider(FakeProvider):
    """Provider whose ``complete`` blocks until cancelled or released.

    Used to simulate a long LLM call so the agent task can be cancelled
    mid-flight. ``complete`` awaits an event that is never set, so the only
    way out is ``CancelledError``.
    """

    def __init__(self) -> None:
        super().__init__(script=[])
        self.was_cancelled = False

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
        reasoning: str = "",
    ) -> CompletionResult:
        try:
            await asyncio.Event().wait()  # blocks forever
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise
        return CompletionResult(content="unreachable", tool_calls=[], finish_reason="stop")


def test_run_agent_propagates_cancel() -> None:
    """Cancelling the task running run_agent raises CancelledError (CATALOG-11).

    The standard asyncio cancellation must propagate through the whole stack
    (run_agent -> _run_agent_core -> provider.complete) without being masked.
    """

    async def _run() -> None:
        provider = _BlockingProvider()
        task = asyncio.ensure_future(
            _drain(
                run_agent(
                    provider=provider,
                    model="m",
                    system_prompt="sys",
                    messages=[Message(role="user", content="x")],
                    tools=_registry(),
                    use_stream=False,
                )
            )
        )
        # Give the task a chance to enter provider.complete().
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # The provider observed the cancellation at its await point.
        assert provider.was_cancelled is True

    asyncio.run(_run())
