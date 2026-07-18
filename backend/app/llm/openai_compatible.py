"""Base class for OpenAI-Chat-Completions-compatible LLM providers.

Every concrete provider in this codebase (OpenRouter, z.ai/GLM, …) speaks the
same wire dialect: ``POST /chat/completions``, ``choices[].message``,
SSE ``data:`` + ``[DONE]``, function calling, ``Authorization: Bearer``.
This module captures that shared logic — retry/backoff, tool-call parsing,
SSE streaming, prompt logging — so subclasses stay thin. See ADR-0013 for the
multi-provider architecture and the ``reasoning`` streaming contract.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.base import (
    CompletionResult,
    Message,
    ModelInfo,
    StreamDelta,
    ToolCall,
    ToolSpec,
    message_to_dict,
    tool_specs_to_dicts,
)
from app.llm.prompt_log import write_prompt_log

logger = logging.getLogger("app.llm")

# Transient HTTP statuses that are safe to retry with backoff (ADR-0009).
# 401 is NOT here — an invalid key is permanent and must surface immediately.
_RETRY_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 0.5  # seconds; doubled each attempt (0.5, 1.0, 2.0 ...)


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


class OpenAICompatibleProvider:
    """Shared logic for OpenAI-compatible providers (ADR-0013).

    Subclasses set ``provider_name`` and ``base_url`` and may override
    :meth:`list_models` (e.g. to return a hardcoded catalog) and the
    ``auth_error_message`` shown on a 401.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        base_url: str,
        provider_name: str,
        *,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
        auth_error_message: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._provider_name = provider_name
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._auth_error_message = (
            auth_error_message
            or f"Invalid {provider_name} API key — check the API key in .env"
        )

    # --- hooks / helpers ---------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff for ``attempt`` (0-based): base * 2**attempt."""
        return self._backoff_base * (2**attempt)

    def _error_detail(self, resp: httpx.Response) -> str:
        """Build a readable ``"provider error <status>: <detail>"`` message.

        Most OpenAI-compatible providers return ``{"error": {"message": …}}``
        on failure (CATALOG-23) — that message is far more useful to a user
        than the generic text ``httpx.HTTPStatusError`` would otherwise raise
        (e.g. a rejected/unknown model on a 400, or an access-denied model on
        a 403). Falls back to the raw response body when it isn't JSON.
        """
        try:
            body = resp.json()
            detail = body.get("error", {}).get("message") or body.get("error")
        except (json.JSONDecodeError, AttributeError):
            detail = None
        if not detail:
            detail = resp.text[:300]
        return f"{self._provider_name} error {resp.status_code}: {detail}"

    def _parse_model(self, m: dict[str, Any]) -> ModelInfo:
        ctx = m.get("context_length")
        return ModelInfo(
            id=m.get("id", ""),
            name=m.get("name", m.get("id", "")),
            context_length=int(ctx) if ctx is not None else None,
        )

    def _normalize_model(self, model: str) -> str:
        return model

    def _apply_reasoning(self, body: dict[str, Any], reasoning: str) -> None:
        if reasoning:
            body["reasoning"] = {"effort": reasoning}

    # --- HTTP with retry ---------------------------------------------------

    async def _post_with_retry(
        self, url: str, body: dict[str, Any]
    ) -> httpx.Response:
        """POST ``body`` to ``url`` with retry/backoff on transient failures.

        Retries on rate-limit (429), server errors (5xx) and network/timeout
        exceptions. A 401 surfaces immediately as a :class:`ValueError` (a bad
        key is permanent). After exhausting retries the last error is raised
        with a clear, UI-friendly message.
        """
        resp: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._client.post(
                    url, headers=self._auth_headers(), json=body
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < self._max_retries:
                    logger.warning(
                        "complete network error (attempt %d/%d): %s",
                        attempt + 1,
                        self._max_retries,
                        exc,
                    )
                    await asyncio.sleep(self._backoff_delay(attempt))
                    continue
                raise RuntimeError(
                    f"{self._provider_name} request failed after "
                    f"{self._max_retries} retries: {exc}"
                ) from exc

            # 401 is permanent — never retry, surface a clear message.
            if resp.status_code == 401:
                raise ValueError(self._auth_error_message)
            # Transient status with retries left → back off and try again.
            if (
                resp.status_code in _RETRY_STATUS
                and attempt < self._max_retries
            ):
                logger.warning(
                    "complete HTTP %d (attempt %d/%d), retrying",
                    resp.status_code,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(self._backoff_delay(attempt))
                continue
            break

        assert resp is not None  # loop runs at least once
        if resp.status_code >= 400:
            logger.warning(
                "complete HTTP %d body: %s", resp.status_code, resp.text[:1000]
            )
            if resp.status_code in _RETRY_STATUS:
                raise RuntimeError(
                    f"{self._provider_name} returned HTTP {resp.status_code} after "
                    f"{self._max_retries} retries"
                )
            raise RuntimeError(self._error_detail(resp))
        return resp

    # --- model catalog -----------------------------------------------------

    async def list_models(self) -> list[ModelInfo]:
        """Fetch the model catalog from ``/models``.

        Subclasses may override to return a hardcoded catalog (e.g. z.ai).
        """
        resp = await self._client.get(
            f"{self._base_url}/models",
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        raw_models = data.get("data", [])
        models = [self._parse_model(m) for m in raw_models]
        logger.info("list_models: fetched %d models", len(models))
        return models

    # --- completion (non-streaming) ----------------------------------------

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
        reasoning: str = "",
    ) -> CompletionResult:
        model = self._normalize_model(model)
        body: dict[str, Any] = {
            "model": model,
            "messages": [message_to_dict(m) for m in messages],
            "temperature": temperature,
        }
        if tools is not None:
            body["tools"] = tool_specs_to_dicts(tools)
            body["tool_choice"] = tool_choice
        self._apply_reasoning(body, reasoning)

        logger.info(
            "complete request: model=%s messages=%d tools=%s temperature=%.1f",
            model,
            len(messages),
            [t.name for t in tools] if tools else None,
            temperature,
        )

        t0 = time.monotonic()
        try:
            resp = await self._post_with_retry(
                f"{self._base_url}/chat/completions", body
            )
        except Exception as exc:
            latency_ms = round((time.monotonic() - t0) * 1000)
            await write_prompt_log(
                provider=self._provider_name,
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                tool_choice=tool_choice,
                stream=False,
                response=None,
                error=str(exc),
                latency_ms=latency_ms,
            )
            raise

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            latency_ms = round((time.monotonic() - t0) * 1000)
            err = RuntimeError(
                f"{self._provider_name} returned no choices (finish/error info): "
                f"{json.dumps(data, ensure_ascii=False)[:1000]}"
            )
            await write_prompt_log(
                provider=self._provider_name,
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                tool_choice=tool_choice,
                stream=False,
                response=None,
                error=str(err),
                latency_ms=latency_ms,
            )
            raise err
        choice = choices[0]
        message = choice["message"]
        content = message.get("content")
        reasoning = message.get("reasoning_content")
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

        await write_prompt_log(
            provider=self._provider_name,
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            tool_choice=tool_choice,
            stream=False,
            response={
                "content": content,
                "reasoning": reasoning,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
                "finish_reason": finish_reason,
                "usage": usage,
            },
            error=None,
            latency_ms=round((time.monotonic() - t0) * 1000),
        )

        return CompletionResult(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning=reasoning,
        )

    # --- completion (streaming) --------------------------------------------

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        reasoning: str = "",
    ) -> AsyncIterator[StreamDelta]:
        model = self._normalize_model(model)
        body: dict[str, Any] = {
            "model": model,
            "messages": [message_to_dict(m) for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if tools is not None:
            body["tools"] = tool_specs_to_dicts(tools)
        self._apply_reasoning(body, reasoning)

        logger.info(
            "stream_complete request: model=%s messages=%d tools=%s temperature=%.1f",
            model,
            len(messages),
            [t.name for t in tools] if tools else None,
            temperature,
        )

        t0 = time.monotonic()
        assembled_text = ""
        assembled_reasoning = ""
        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._auth_headers(),
                json=body,
            ) as resp:
                if resp.status_code == 401:
                    raise ValueError(self._auth_error_message)
                if resp.status_code == 429:
                    raise RuntimeError("Rate limit exceeded")
                if resp.status_code >= 400:
                    await resp.aread()
                    logger.warning(
                        "stream_complete HTTP %d body: %s",
                        resp.status_code,
                        resp.text[:1000],
                    )
                    raise RuntimeError(self._error_detail(resp))

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
                    reasoning = delta.get("reasoning_content")
                    if content:
                        logger.debug("stream chunk: %s", repr(content[:100]))
                        assembled_text += content
                    if reasoning:
                        assembled_reasoning += reasoning
                    if content or reasoning:
                        yield StreamDelta(content=content or "", reasoning=reasoning)
        except Exception as exc:
            await write_prompt_log(
                provider=self._provider_name,
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                tool_choice="auto",
                stream=True,
                response={
                    "assembled_text": assembled_text,
                    "assembled_reasoning": assembled_reasoning or None,
                    "usage": {},
                    "finish_reason": "error",
                },
                error=str(exc),
                latency_ms=round((time.monotonic() - t0) * 1000),
            )
            raise

        await write_prompt_log(
            provider=self._provider_name,
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            tool_choice="auto",
            stream=True,
            response={
                "assembled_text": assembled_text,
                "assembled_reasoning": assembled_reasoning or None,
                "usage": {},
                "finish_reason": "stop",
            },
            error=None,
            latency_ms=round((time.monotonic() - t0) * 1000),
        )
