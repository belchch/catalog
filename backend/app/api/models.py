"""``GET /models``, ``GET /providers`` (CATALOG-6).

These power the skill pre-save settings modal: the list of models (with
reasoning capability) comes from the active provider's catalog, and the list of
providers comes from the provider dict built in the lifespan. The structure is
ready for multiple providers (CATALOG-24); with a single configured provider it
returns a one-element list.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_provider
from app.api.schemas import ModelOut, ProviderOut
from app.llm.base import LLMProvider

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
