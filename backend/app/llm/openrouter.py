from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.base import (
    CompletionResult,
    Message,
    ModelInfo,
    ToolCall,
    ToolSpec,
)

logger = logging.getLogger("app.llm")


async def _log_request(request: httpx.Request) -> None:
    body_preview = ""
    if request.content:
        body_preview = request.content.decode(errors="replace")[:1000]
    logger.debug("HTTP %s %s body=%s", request.method, request.url, body_preview)


def build_debug_hooks() -> dict:
    return {"request": [_log_request]}


def _message_to_dict(msg: Message) -> dict[str, Any]:
    d: dict[str, Any] = {"role": msg.role}
    if msg.content is not None:
        d["content"] = msg.content
    if msg.tool_calls is not None:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in msg.tool_calls
        ]
    if msg.tool_call_id is not None:
        d["tool_call_id"] = msg.tool_call_id
    if msg.name is not None:
        d["name"] = msg.name
    return d


def _tools_to_dicts(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _parse_tool_calls(raw: list[dict[str, Any]]) -> list[ToolCall]:
    result: list[ToolCall] = []
    for tc in raw:
        fn = tc.get("function", {})
        args_str = fn.get("arguments", "{}")
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            logger.warning(
                "tool_call arguments not valid JSON (%s): %r", fn.get("name"), args_str
            )
            args = {}
        result.append(
            ToolCall(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=args,
            )
        )
    return result


class OpenRouterProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        base_url: str,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def list_models(self) -> list[ModelInfo]:
        resp = await self._client.get(
            f"{self._base_url}/models",
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        raw_models = data.get("data", [])
        models: list[ModelInfo] = []
        for m in raw_models:
            ctx = m.get("context_length")
            models.append(
                ModelInfo(
                    id=m.get("id", ""),
                    name=m.get("name", m.get("id", "")),
                    context_length=int(ctx) if ctx is not None else None,
                )
            )
        logger.info("list_models: fetched %d models", len(models))
        return models

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
    ) -> CompletionResult:
        body: dict[str, Any] = {
            "model": model,
            "messages": [_message_to_dict(m) for m in messages],
            "temperature": temperature,
        }
        if tools is not None:
            body["tools"] = _tools_to_dicts(tools)
            body["tool_choice"] = tool_choice

        logger.info(
            "complete request: model=%s messages=%d tools=%s temperature=%.1f",
            model,
            len(messages),
            [t.name for t in tools] if tools else None,
            temperature,
        )

        resp = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers=self._auth_headers(),
            json=body,
        )
        if resp.status_code == 401:
            raise ValueError(
                "Invalid OpenRouter API key — check OPENROUTER_API_KEY in .env"
            )
        if resp.status_code == 429:
            raise RuntimeError("Rate limit exceeded")
        if resp.status_code >= 400:
            logger.warning(
                "complete HTTP %d body: %s", resp.status_code, resp.text[:1000]
            )
            resp.raise_for_status()

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(
                "OpenRouter returned no choices (finish/error info): "
                f"{json.dumps(data, ensure_ascii=False)[:1000]}"
            )
        choice = choices[0]
        message = choice["message"]
        content = message.get("content")
        raw_tool_calls = message.get("tool_calls")
        tool_calls = _parse_tool_calls(raw_tool_calls) if raw_tool_calls else []
        finish_reason = choice.get("finish_reason", "")
        usage = data.get("usage", {})

        log_content = (content or "")[:200]
        log_tools = [tc.name for tc in tool_calls] if tool_calls else None
        logger.info(
            "complete response: model=%s finish_reason=%s content=%s tool_calls=%s usage=%s",
            model,
            finish_reason,
            repr(log_content),
            log_tools,
            usage,
        )

        return CompletionResult(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [_message_to_dict(m) for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if tools is not None:
            body["tools"] = _tools_to_dicts(tools)

        logger.info(
            "stream_complete request: model=%s messages=%d tools=%s temperature=%.1f",
            model,
            len(messages),
            [t.name for t in tools] if tools else None,
            temperature,
        )

        async with self._client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            headers=self._auth_headers(),
            json=body,
        ) as resp:
            if resp.status_code == 401:
                raise ValueError(
                    "Invalid OpenRouter API key — check OPENROUTER_API_KEY in .env"
                )
            if resp.status_code == 429:
                raise RuntimeError("Rate limit exceeded")
            if resp.status_code >= 400:
                err_body = (await resp.aread()).decode(errors="replace")
                logger.warning(
                    "stream_complete HTTP %d body: %s",
                    resp.status_code,
                    err_body[:1000],
                )
                resp.raise_for_status()

            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    logger.debug("stream: skipping unparseable line: %s", line)
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    logger.debug("stream chunk: %s", repr(content[:100]))
                    yield content
