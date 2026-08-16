from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import jsonschema

from catalog.agent.events import (
    AgentEvent,
    FinishEvent,
    ReasoningEvent,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from catalog.agent.logging import log_agent_event
from catalog.agent.registry import ToolRegistry
from catalog.agent.trace import Trace, TraceEntry
from catalog.llm.base import LLMProvider, Message, ToolCall
from catalog.llm.log_context import current_iteration


@dataclass
class _ToolExecResult:
    ok: bool
    payload: Any


# Cap on the serialized size of a tool result fed back into the LLM history.
# Long ``read_document`` outputs (large docx) are truncated to bound context
# growth; the full payload is still carried in the trace and the ToolResultEvent.
MAX_TOOL_RESULT_CHARS = 16000


async def _execute_tool(tools: ToolRegistry, tc: ToolCall) -> _ToolExecResult:
    """Validate + invoke a tool. Errors are reported back, never raised."""
    entry = tools.get(tc.name)
    if entry is None:
        return _ToolExecResult(False, f"error: unknown tool '{tc.name}'")
    spec, func = entry
    try:
        jsonschema.validate(tc.arguments, spec.parameters)
    except jsonschema.ValidationError as exc:
        return _ToolExecResult(False, f"error: invalid args: {exc.message}")
    try:
        result = await func(**tc.arguments)
    except Exception as exc:  # noqa: BLE001 — tool errors are wrapped, not raised
        return _ToolExecResult(False, f"error: {exc}")
    return _ToolExecResult(True, result)


def _serialize_result(result: Any) -> str:
    """Serialize a tool result to a string for the message history.

    Long results are truncated to :data:`MAX_TOOL_RESULT_CHARS` so a huge
    ``read_document`` payload cannot overflow the model context. The full
    payload is still recorded in the trace and emitted via ``ToolResultEvent``;
    only the copy fed back to the LLM is bounded.
    """
    if isinstance(result, (dict, list)):
        s = json.dumps(result, ensure_ascii=False, default=str)
    else:
        s = str(result)
    if len(s) > MAX_TOOL_RESULT_CHARS:
        return (
            s[:MAX_TOOL_RESULT_CHARS]
            + f"\n…[truncated: {len(s)} chars total, kept first {MAX_TOOL_RESULT_CHARS}]"
        )
    return s


async def _run_agent_core(
    *,
    provider: LLMProvider,
    model: str,
    system_prompt: str,
    messages: list[Message],
    tools: ToolRegistry,
    temperature: float,
    max_iterations: int,
    use_stream: bool,
    trace: Trace,
    reasoning: str = "",
) -> AsyncIterator[AgentEvent]:
    """Shared loop: streams events and records ``trace``.

    Both :func:`run_agent` and :func:`run_agent_collect` delegate here so the
    trace and the event stream always agree.
    """
    history: list[Message] = [Message(role="system", content=system_prompt), *messages]
    last_text: str | None = None

    for i in range(1, max_iterations + 1):
        step_event = StepEvent(i)
        yield step_event
        log_agent_event(step_event)
        trace.entries.append(TraceEntry("llm", i, {}))
        from catalog.skills.budget import charge_nested_skill_llm

        charge_nested_skill_llm()
        # Bind the iteration to the prompt-log context for this turn. The
        # session_id/run_id/purpose are set by the API layer; only iteration
        # changes per turn, so it is set directly rather than via the manager.
        current_iteration.set(i)

        if use_stream:
            text = ""
            reasoning_parts: list[str] = []
            async for delta in provider.stream_complete(
                model, history, tools.specs(), temperature, reasoning=reasoning
            ):
                if delta.content:
                    text += delta.content
                    yield TokenEvent(delta.content)
                if delta.reasoning:
                    reasoning_parts.append(delta.reasoning)
            # Stream mode does not parse tool_calls from SSE in this slice;
            # the run finishes at end of stream.
            reasoning_text = "".join(reasoning_parts) or None
            trace.entries[-1].data = {"content": text, "reasoning": reasoning_text}
            # CATALOG-24/16: surface the model's chain-of-thought as its own
            # trace event when the provider emits reasoning_content.
            if reasoning_text:
                reasoning_event = ReasoningEvent(reasoning_text)
                yield reasoning_event
                log_agent_event(reasoning_event)
            history.append(Message(role="assistant", content=text))
            finish_stream = FinishEvent(text, "stop", capped=False, usage={})
            yield finish_stream
            log_agent_event(finish_stream)
            return

        resp = await provider.complete(
            model, history, tools.specs(), temperature, reasoning=reasoning
        )
        trace.entries[-1].data = {
            "finish_reason": resp.finish_reason,
            "content": resp.content,
            "reasoning": resp.reasoning,
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in resp.tool_calls
            ],
        }
        history.append(
            Message(role="assistant", content=resp.content, tool_calls=resp.tool_calls)
        )
        if resp.content is not None:
            last_text = resp.content
        # CATALOG-24/16: surface the model's chain-of-thought as its own trace
        # event when the provider emits reasoning_content for this turn.
        if resp.reasoning:
            reasoning_event = ReasoningEvent(resp.reasoning)
            yield reasoning_event
            log_agent_event(reasoning_event)

        if not resp.tool_calls:
            finish_no_tools = FinishEvent(
                resp.content, resp.finish_reason, capped=False, usage=resp.usage
            )
            yield finish_no_tools
            log_agent_event(finish_no_tools)
            return

        for tc in resp.tool_calls:
            trace.entries.append(
                TraceEntry("tool_call", i, {"name": tc.name, "arguments": tc.arguments})
            )
            call_event = ToolCallEvent(tc.id, tc.name, tc.arguments)
            yield call_event
            log_agent_event(call_event)
            res = await _execute_tool(tools, tc)
            trace.entries.append(
                TraceEntry(
                    "tool_result",
                    i,
                    {"name": tc.name, "result": res.payload, "ok": res.ok},
                )
            )
            result_event = ToolResultEvent(tc.id, tc.name, res.ok, res.payload)
            yield result_event
            log_agent_event(result_event)
            history.append(
                Message(
                    role="tool",
                    content=_serialize_result(res.payload),
                    tool_call_id=tc.id,
                    name=tc.name,
                )
            )

    # Loop exhausted without a final answer.
    finish_capped = FinishEvent(last_text, "capped", capped=True, usage={})
    yield finish_capped
    log_agent_event(finish_capped)


async def run_agent(
    *,
    provider: LLMProvider,
    model: str,
    system_prompt: str,
    messages: list[Message],
    tools: ToolRegistry,
    temperature: float = 0.0,
    max_iterations: int = 8,
    use_stream: bool = True,
    reasoning: str = "",
) -> AsyncIterator[AgentEvent]:
    """Run the function-calling loop, streaming :data:`AgentEvent` items."""
    trace = Trace()
    async for event in _run_agent_core(
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_iterations=max_iterations,
        use_stream=use_stream,
        trace=trace,
        reasoning=reasoning,
    ):
        yield event


async def run_agent_collect(
    *,
    provider: LLMProvider,
    model: str,
    system_prompt: str,
    messages: list[Message],
    tools: ToolRegistry,
    temperature: float = 0.0,
    max_iterations: int = 8,
    use_stream: bool = True,
    reasoning: str = "",
) -> tuple[str | None, Trace, bool]:
    """Drain :func:`run_agent` and return ``(final_text, trace, capped)``."""
    trace = Trace()
    final_text: str | None = None
    capped = False
    async for event in _run_agent_core(
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_iterations=max_iterations,
        use_stream=use_stream,
        trace=trace,
        reasoning=reasoning,
    ):
        if isinstance(event, FinishEvent):
            final_text = event.text
            capped = event.capped
    return final_text, trace, capped
