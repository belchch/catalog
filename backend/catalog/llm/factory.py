"""Provider factory — builds available LLM providers and selects the active one.

The factory inspects :class:`~catalog.config.Settings` for configured API keys and
instantiates every provider that can be created. The *active* provider (the one
the agent loop talks to) is selected via ``APP_PROVIDER`` (env), defaulting to
``openrouter`` for backward compatibility. See ADR-0013.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from catalog.config import Settings
from catalog.llm.base import LLMProvider
from catalog.llm.openrouter import OpenRouterProvider
from catalog.llm.providers import KNOWN_PROVIDERS
from catalog.llm.zai import ZaiProvider

logger = logging.getLogger("catalog.llm")


def _build_openrouter(settings: Settings, http_client: httpx.AsyncClient) -> LLMProvider:
    return OpenRouterProvider(http_client, settings.api_key, settings.base_url)


def _build_zai(settings: Settings, http_client: httpx.AsyncClient) -> LLMProvider:
    return ZaiProvider(http_client, settings.zai_api_key, settings.zai_base_url)


_BUILDERS: dict[str, Callable[[Settings, httpx.AsyncClient], LLMProvider]] = {
    "openrouter": _build_openrouter,
    "zai": _build_zai,
}


def build_providers(
    settings: Settings, http_client: httpx.AsyncClient
) -> dict[str, LLMProvider]:
    """Build every provider whose prerequisites (API key) are met.

    OpenRouter is always created (even with an empty key) to preserve the
    pre-factory behaviour where ``main.py`` instantiated it unconditionally.
    z.ai is created only when ``ZAI_API_KEY`` is set.
    """
    providers: dict[str, LLMProvider] = {}

    for spec in KNOWN_PROVIDERS:
        key = getattr(settings, spec.settings_field, "")
        if spec.id != "openrouter" and not key:
            continue
        builder = _BUILDERS[spec.id]
        providers[spec.id] = builder(settings, http_client)

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


def provider_name_for_skill(
    providers: dict[str, LLMProvider] | None,
    active_name: str,
    provider_name: str,
) -> str:
    """Resolve the provider *name* a skill configured (CATALOG-6/16).

    A skill may pin a specific ``provider`` (chosen in the settings modal). If
    it names an available provider, that name is returned; otherwise the app's
    active provider name is returned. This is the single source of truth for
    the pin/fallback rule — :func:`provider_for_skill` and the run stream both
    delegate here instead of re-implementing the condition.
    """
    if provider_name and providers and provider_name in providers:
        return provider_name
    return active_name


def provider_for_skill(
    providers: dict[str, LLMProvider] | None,
    active: LLMProvider,
    provider_name: str,
) -> LLMProvider:
    """Resolve the provider a skill configured (CATALOG-6).

    A skill may pin a specific ``provider`` (chosen in the settings modal). If
    it names an available provider, that one is used; otherwise the app's active
    provider is used (back-compat for skills without a pinned provider, or when
    the named provider is no longer configured).
    """
    name = provider_name_for_skill(providers, "", provider_name)
    if name and providers and name in providers:
        return providers[name]
    return active
