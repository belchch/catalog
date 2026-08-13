from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from catalog.api.deps import get_app_db, get_provider
from catalog.api.schemas import (
    ModelOut,
    ProviderOut,
    SettingsOut,
    SettingsUpdate,
    SetupKeysUpdate,
    SetupOut,
)
from catalog.config import keys_are_configured, with_resolved_keys
from catalog.llm.base import LLMProvider
from catalog.runtime import apply_runtime_providers, coerce_model_for_provider
from catalog.storage.db import Database
from catalog.storage.repo_app_settings import (
    get_api_keys,
    get_app_settings,
    set_api_keys,
    set_app_settings,
)

router = APIRouter()


def _setup_status(request: Request, app_db: Database) -> SetupOut:
    settings = getattr(request.app.state, "settings", None)
    provider = getattr(request.app.state, "active_provider", None) or ""
    if settings is None:
        provider_db, _model = get_app_settings(app_db)
        persisted_or, persisted_zai = get_api_keys(app_db)
        return SetupOut(
            keys_configured=bool(persisted_or or persisted_zai),
            provider=provider or provider_db,
            openrouter_configured=bool(persisted_or),
            zai_configured=bool(persisted_zai),
        )
    return SetupOut(
        keys_configured=keys_are_configured(settings),
        provider=provider,
        openrouter_configured=bool(settings.api_key.strip()),
        zai_configured=bool(settings.zai_api_key.strip()),
    )


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
        name = getattr(active, "provider_name", "provider") if active else "provider"
        return [ProviderOut(id=name, name=name, active=True)]
    out = [
        ProviderOut(id=name, name=name, active=inst is active)
        for name, inst in providers.items()
    ]
    if active is not None and not any(inst is active for inst in providers.values()):
        name = getattr(active, "provider_name", "active") or "active"
        out.append(ProviderOut(id=name, name=name, active=True))
    return out


@router.get("/providers/{provider_id}/models", response_model=list[ModelOut])
async def list_provider_models_endpoint(
    provider_id: str, request: Request
) -> list[ModelOut]:
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
    provider = getattr(request.app.state, "active_provider", None) or ""
    model = getattr(request.app.state, "active_model", None) or ""
    if not provider and not model:
        provider, model = get_app_settings(app_db)
    settings = getattr(request.app.state, "settings", None)
    configured = keys_are_configured(settings) if settings is not None else False
    return SettingsOut(provider=provider, model=model, keys_configured=configured)


@router.post("/settings", response_model=SettingsOut)
async def update_settings_endpoint(
    req: SettingsUpdate,
    request: Request,
    app_db: Database = Depends(get_app_db),
) -> SettingsOut:
    providers: dict[str, LLMProvider] = getattr(request.app.state, "providers", None) or {}
    if req.provider is not None:
        if req.provider not in providers:
            raise HTTPException(status_code=404, detail=f"unknown provider: {req.provider!r}")
        request.app.state.active_provider = req.provider
        request.app.state.provider = providers[req.provider]
    if req.model is not None:
        request.app.state.active_model = req.model
    elif req.provider is not None:
        settings = getattr(request.app.state, "settings", None)
        fallback = settings.default_model if settings is not None else ""
        request.app.state.active_model = coerce_model_for_provider(
            request.app.state.active_provider,
            getattr(request.app.state, "active_model", None),
            fallback,
        )
    set_app_settings(
        app_db,
        provider=request.app.state.active_provider,
        model=request.app.state.active_model,
    )
    settings = getattr(request.app.state, "settings", None)
    configured = keys_are_configured(settings) if settings is not None else False
    return SettingsOut(
        provider=request.app.state.active_provider,
        model=request.app.state.active_model,
        keys_configured=configured,
    )


@router.get("/setup", response_model=SetupOut)
async def get_setup_endpoint(
    request: Request, app_db: Database = Depends(get_app_db)
) -> SetupOut:
    return _setup_status(request, app_db)


@router.put("/setup/keys", response_model=SetupOut)
async def put_setup_keys_endpoint(
    req: SetupKeysUpdate,
    request: Request,
    app_db: Database = Depends(get_app_db),
) -> SetupOut:
    if req.openrouter_api_key is None and req.zai_api_key is None:
        raise HTTPException(status_code=422, detail="at least one api key field is required")
    set_api_keys(
        app_db,
        openrouter_api_key=req.openrouter_api_key,
        zai_api_key=req.zai_api_key,
    )
    persisted_or, persisted_zai = get_api_keys(app_db)
    base_settings = getattr(request.app.state, "settings", None)
    if base_settings is None:
        raise HTTPException(status_code=503, detail="settings not initialized")
    settings = with_resolved_keys(
        base_settings,
        persisted_openrouter=persisted_or,
        persisted_zai=persisted_zai,
    )
    apply_runtime_providers(request.app, settings)
    return _setup_status(request, app_db)
