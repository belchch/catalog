"""``GET /models``, ``GET /providers`` (CATALOG-6).

These power the skill pre-save settings modal: the list of models (with
reasoning capability) comes from the active provider's catalog, and the list of
providers comes from the provider dict built in the lifespan. The structure is
ready for multiple providers (CATALOG-24); with a single configured provider it
returns a one-element list.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_app_db, get_provider
from app.api.schemas import ModelOut, ProviderOut, SettingsOut, SettingsUpdate
from app.llm.base import LLMProvider
from app.storage.db import Database
from app.storage.repo_app_settings import get_app_settings, set_app_settings

router = APIRouter()


@router.get("/models", response_model=list[ModelOut])
async def list_models_endpoint(
    provider: LLMProvider = Depends(get_provider),
) -> list[ModelOut]:
    try:
        models = await provider.list_models()
    except Exception as exc:  # noqa: BLE001 — surface catalog fetch failures
        raise HTTPException(status_code=502, detail=f"failed to list models: {exc}") from exc
    return [
        ModelOut(
            id=m.id,
            name=m.name,
            context_length=m.context_length,
            supports_reasoning=m.supports_reasoning,
            reasoning_variants=list(m.reasoning_variants),
        )
        for m in models
    ]


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers_endpoint(request: Request) -> list[ProviderOut]:
    providers: dict[str, LLMProvider] | None = getattr(request.app.state, "providers", None)
    active: LLMProvider | None = getattr(request.app.state, "provider", None)
    if not providers:
        # Single-provider fallback (e.g. tests that only set the active provider).
        name = getattr(active, "provider_name", "provider") if active else "provider"
        return [ProviderOut(id=name, name=name, active=True)]
    out = [
        ProviderOut(id=name, name=name, active=inst is active)
        for name, inst in providers.items()
    ]
    # If the active provider was swapped after lifespan (e.g. tests inject a
    # fake), it is not in the dict — surface it as an explicit active entry.
    if active is not None and not any(inst is active for inst in providers.values()):
        name = getattr(active, "provider_name", "active") or "active"
        out.append(ProviderOut(id=name, name=name, active=True))
    return out


@router.get("/providers/{provider_id}/models", response_model=list[ModelOut])
async def list_provider_models_endpoint(
    provider_id: str, request: Request
) -> list[ModelOut]:
    """List models for a specific (not necessarily active) provider (CATALOG-14)."""
    providers: dict[str, LLMProvider] | None = getattr(request.app.state, "providers", None)
    provider = (providers or {}).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider_id!r}")
    try:
        models = await provider.list_models()
    except Exception as exc:  # noqa: BLE001 — surface catalog fetch failures
        raise HTTPException(status_code=502, detail=f"failed to list models: {exc}") from exc
    return [
        ModelOut(
            id=m.id,
            name=m.name,
            context_length=m.context_length,
            supports_reasoning=m.supports_reasoning,
            reasoning_variants=list(m.reasoning_variants),
        )
        for m in models
    ]


@router.get("/settings", response_model=SettingsOut)
async def get_settings_endpoint(
    request: Request, app_db: Database = Depends(get_app_db)
) -> SettingsOut:
    """Return the current runtime provider/model selection (CATALOG-14)."""
    provider = getattr(request.app.state, "active_provider", None) or ""
    model = getattr(request.app.state, "active_model", None) or ""
    if not provider and not model:
        provider, model = get_app_settings(app_db)
    return SettingsOut(provider=provider, model=model)


@router.post("/settings", response_model=SettingsOut)
async def update_settings_endpoint(
    req: SettingsUpdate,
    request: Request,
    app_db: Database = Depends(get_app_db),
) -> SettingsOut:
    """Switch the runtime active provider and/or model (CATALOG-14).

    Switching the provider also updates the resolved active provider instance
    (``app.state.provider``) so the planner and apply pick it up. An unknown
    provider is rejected with 404; an empty body is a no-op.
    """
    providers: dict[str, LLMProvider] = getattr(request.app.state, "providers", None) or {}
    if req.provider is not None:
        if req.provider not in providers:
            raise HTTPException(status_code=404, detail=f"unknown provider: {req.provider!r}")
        request.app.state.active_provider = req.provider
        request.app.state.provider = providers[req.provider]
    if req.model is not None:
        request.app.state.active_model = req.model
    set_app_settings(
        app_db,
        provider=request.app.state.active_provider,
        model=request.app.state.active_model,
    )
    return SettingsOut(
        provider=request.app.state.active_provider,
        model=request.app.state.active_model,
    )
