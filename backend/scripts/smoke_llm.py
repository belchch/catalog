from __future__ import annotations

import asyncio
import logging
import sys

import httpx

from app.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_DEFAULT_MODEL,
    OPENROUTER_FALLBACK_MODEL,
)
from app.llm import Message, OpenRouterProvider, ToolSpec
from app.llm.openrouter import build_debug_hooks

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("smoke")


CURRENT_TIME_TOOL = ToolSpec(
    name="current_time",
    description="Returns the current date and time.",
    parameters={"type": "object", "properties": {}},
)


async def check_list_models(provider: OpenRouterProvider) -> None:
    print("\n=== Test 1: list_models ===")
    models = await provider.list_models()
    print(f"Total models: {len(models)}")
    for m in models[:3]:
        print(f"  - {m.id}  (ctx={m.context_length})")
    assert len(models) > 0, "No models returned"
    print("  PASS")


async def check_complete(provider: OpenRouterProvider, model: str) -> None:
    print(f"\n=== Test 2: complete (model={model}) ===")
    result = await provider.complete(
        model=model,
        messages=[
            Message(role="system", content="You are a helpful assistant. Reply briefly."),
            Message(role="user", content="Say hello in one sentence."),
        ],
    )
    print(f"  content: {result.content}")
    print(f"  finish_reason: {result.finish_reason}")
    print(f"  usage: {result.usage}")
    assert result.content is not None and len(result.content) > 0
    print("  PASS")


async def check_tool_call(provider: OpenRouterProvider, model: str) -> bool:
    print(f"\n=== Test 3: tool-call proof (model={model}) ===")
    result = await provider.complete(
        model=model,
        messages=[
            Message(role="system", content="You must call tools when asked."),
            Message(role="user", content="What time is it right now?"),
        ],
        tools=[CURRENT_TIME_TOOL],
        tool_choice="auto",
    )
    print(f"  content: {result.content}")
    print(f"  tool_calls: {[tc.name for tc in result.tool_calls]}")
    print(f"  finish_reason: {result.finish_reason}")
    if result.tool_calls and result.tool_calls[0].name == "current_time":
        print("  PASS")
        return True
    print("  FAIL — no tool_calls or wrong name")
    return False


async def check_stream(provider: OpenRouterProvider, model: str) -> None:
    print(f"\n=== Test 4: stream_complete (model={model}) ===")
    chunks: list[str] = []
    async for chunk in provider.stream_complete(
        model=model,
        messages=[Message(role="user", content="Count from 1 to 3, numbers only.")],
    ):
        chunks.append(chunk)
    text = "".join(chunks)
    print(f"  chunks={len(chunks)} text={text!r}")
    assert chunks, "no chunks streamed"
    assert len(chunks) >= 2, "expected multiple chunks (true streaming)"
    print("  PASS")


async def main() -> None:
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY is not set. Add it to backend/.env")
        sys.exit(1)

    client = httpx.AsyncClient(timeout=30.0, event_hooks=build_debug_hooks())
    provider = OpenRouterProvider(
        client=client,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
    )
    try:
        await check_list_models(provider)
        await check_complete(provider, OPENROUTER_DEFAULT_MODEL)
        await check_stream(provider, OPENROUTER_DEFAULT_MODEL)

        tool_ok = await check_tool_call(provider, OPENROUTER_DEFAULT_MODEL)
        if not tool_ok:
            logger.info(
                "free model failed tool-calling, retrying with fallback %s",
                OPENROUTER_FALLBACK_MODEL,
            )
            tool_ok = await check_tool_call(provider, OPENROUTER_FALLBACK_MODEL)
            assert tool_ok, f"Tool-calling also failed with fallback {OPENROUTER_FALLBACK_MODEL}"

        print("\n=== All smoke tests passed ===")
    finally:
        await client.aclose()


asyncio.run(main())
