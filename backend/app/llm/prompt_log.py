"""Write raw LLM prompt/request/response payloads to disk for quality analysis.

Opt-in via ``PROMPT_LOG_ENABLED`` (default off). One JSON file per request under
``${PROMPT_LOG_DIR}/YYYY-MM-DD/<HHMMSSffffff>_<request_id>.json``.

Design notes
------------
- Called from the provider choke point (:class:`OpenRouterProvider`), so every
  LLM call (agent loop, skill builder, stream / non-stream) is captured.
- Writes are offloaded to a worker thread via :func:`asyncio.to_thread` and are
  atomic (write to ``.tmp`` then :func:`os.replace`) so a crash mid-write never
  leaves a partial file.
- Any failure is swallowed and logged at WARNING — prompt logging must never
  break an LLM call. HTTP headers (incl. ``Authorization``) are never logged;
  only the request body (messages/tools/model/...) and the parsed response.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app import config
from app.llm.base import Message, ToolSpec, message_to_dict, tool_specs_to_dicts
from app.llm.log_context import collect_context

logger = logging.getLogger("app.llm.prompt_log")

_SCHEMA_VERSION = 1


def is_enabled() -> bool:
    """Whether prompt logging is currently enabled (reads config at call time)."""
    return config.PROMPT_LOG_ENABLED


def _write_atomic(path: str, payload: dict[str, Any]) -> None:
    """Write ``payload`` as JSON to ``path`` atomically (tmp + replace)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, default=str)
    os.replace(tmp, path)


async def write_prompt_log(
    *,
    provider: str,
    model: str,
    messages: list[Message],
    tools: list[ToolSpec] | None,
    temperature: float,
    tool_choice: str,
    stream: bool,
    response: dict[str, Any] | None,
    error: str | None,
    latency_ms: int,
) -> None:
    """Persist one prompt-log JSON file. Best-effort: never raises.

    Early-returns when disabled. Any I/O or serialization error is caught and
    logged at WARNING so the calling LLM request is unaffected.
    """
    if not is_enabled():
        return

    try:
        request_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now(timezone.utc)
        day_dir = timestamp.strftime("%Y-%m-%d")
        fname = f"{timestamp.strftime('%H%M%S%f')}_{request_id}.json"
        path = os.path.join(config.PROMPT_LOG_DIR, day_dir, fname)

        payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "request_id": request_id,
            "timestamp": timestamp.isoformat(),
            "provider": provider,
            "context": collect_context(),
            "request": {
                "model": model,
                "temperature": temperature,
                "tool_choice": tool_choice,
                "stream": stream,
                "tools": tool_specs_to_dicts(tools) if tools else [],
                "messages": [message_to_dict(m) for m in messages],
            },
            "response": response,
            "meta": {
                "latency_ms": latency_ms,
                "ok": error is None,
                "error": error,
            },
        }

        await asyncio.to_thread(_write_atomic, path, payload)
    except Exception as exc:  # noqa: BLE001 — logging must not break the LLM call
        logger.warning("prompt log write failed: %s", exc)
