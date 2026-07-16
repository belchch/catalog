"""Provider factory — builds available LLM providers and selects the active one.

The factory inspects :class:`~app.config.Settings` for configured API keys and
instantiates every provider that can be created. The *active* provider (the one
the agent loop talks to) is selected via ``APP_PROVIDER`` (env), defaulting to
``openrouter`` for backward compatibility. See ADR-0013.
"""

from __future__ import annotations

import logging

import httpx

from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.openrouter import OpenRouterProvider
from app.llm.zai import ZaiProvider

logger = logging.getLogger("app.llm")


def build_providers(
    settings: Settings, http_client: httpx.AsyncClient
) -> dict[str, LLMProvider]:
    """Build every provider whose prerequisites (API key) are met.

    OpenRouter is always created (even with an empty key) to preserve the
    pre-factory behaviour where ``main.py`` instantiated it unconditionally.
    z.ai is created only when ``ZAI_API_KEY`` is set.
    """
    providers: dict[str, LLMProvider] = {}

    providers["openrouter"] = OpenRouterProvider(
        http_client, settings.api_key, settings.base_url
    )

    if settings.zai_api_key:
        providers["zai"] = ZaiProvider(
            http_client, settings.zai_api_key, settings.zai_base_url
        )

    logger.info(
        "build_providers: available=%s active_env=%s",
        list(providers),
        settings.app_provider or "(auto)",
    )
    return providers


def select_provider(
    providers: dict[str, LLMProvider], app_provider: str
) -> LLMProvider:
    """Pick the active provider.

    If ``app_provider`` names an available provider, use it. Otherwise default
    to ``openrouter`` (backward compat), falling back to the first available
    provider if OpenRouter is somehow absent.
    """
    if app_provider and app_provider in providers:
        return providers[app_provider]
    if "openrouter" in providers:
        return providers["openrouter"]
    # Defensive: should not happen (openrouter is always created).
    return next(iter(providers.values()))
