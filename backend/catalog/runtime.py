from __future__ import annotations

import httpx
from fastapi import FastAPI

from catalog.config import Settings
from catalog.llm.factory import build_providers, select_provider
from catalog.llm.zai import DEFAULT_ZAI_MODEL


def model_fits_provider(provider: str, model: str) -> bool:
    if not model:
        return False
    is_zai_style = "/" not in model
    if provider == "zai":
        return is_zai_style
    return not is_zai_style


def coerce_model_for_provider(
    provider: str,
    model: str | None,
    fallback: str,
) -> str:
    candidate = (model or "").strip()
    if candidate and model_fits_provider(provider, candidate):
        return candidate
    if provider == "zai":
        if "/" in (fallback or "") or not fallback:
            return DEFAULT_ZAI_MODEL
        return fallback
    return fallback or ""


def apply_runtime_providers(app: FastAPI, settings: Settings) -> None:
    http_client: httpx.AsyncClient = app.state.http_client
    providers = build_providers(settings, http_client)
    app.state.providers = providers
    active_name = getattr(app.state, "active_provider", None) or settings.app_provider
    if active_name not in providers:
        selected = select_provider(providers, settings.app_provider)
        active_name = next(
            (name for name, inst in providers.items() if inst is selected),
            next(iter(providers), "openrouter"),
        )
    app.state.active_provider = active_name
    app.state.provider = providers[active_name]
    app.state.active_model = coerce_model_for_provider(
        active_name,
        getattr(app.state, "active_model", None),
        settings.default_model,
    )
    app.state.settings = settings
