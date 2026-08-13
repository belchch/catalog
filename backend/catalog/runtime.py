from __future__ import annotations

import httpx
from fastapi import FastAPI

from catalog.config import Settings
from catalog.llm.factory import build_providers, select_provider


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
    app.state.settings = settings
