"""OpenRouter provider — thin subclass of :class:`OpenAICompatibleProvider`.

The shared OpenAI-Chat-Completions logic lives in
:mod:`catalog.llm.openai_compatible`; this module keeps only the OpenRouter
specifics: the ``/models`` catalog endpoint and the provider name / auth-error
message used in logs and exceptions. See ADR-0009 and ADR-0013.
"""

from __future__ import annotations

import logging

import httpx

from catalog.llm.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger("catalog.llm")


# --- Debug HTTP hooks (shared, kept here for import compatibility) ---------


async def _log_request(request: httpx.Request) -> None:
    body_preview = ""
    if request.content:
        body_preview = request.content.decode(errors="replace")[:1000]
    logger.debug("HTTP %s %s body=%s", request.method, request.url, body_preview)


def build_debug_hooks() -> dict:
    return {"request": [_log_request]}


# --- Provider --------------------------------------------------------------


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter (https://openrouter.ai) — the original/default provider.

    Behaviour is identical to the pre-refactor monolith: the model catalog is
    fetched live from ``/models`` and the 401 message points at
    ``OPENROUTER_API_KEY``.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        base_url: str,
        *,
        max_retries: int = 3,
        backoff_base: float = 0.5,
    ) -> None:
        super().__init__(
            client,
            api_key,
            base_url,
            provider_name="openrouter",
            max_retries=max_retries,
            backoff_base=backoff_base,
            auth_error_message=(
                "Invalid OpenRouter API key — check OPENROUTER_API_KEY in .env"
            ),
        )
