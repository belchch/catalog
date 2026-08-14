from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnownProvider:
    id: str
    display_name: str
    env_var: str
    settings_field: str


KNOWN_PROVIDERS: tuple[KnownProvider, ...] = (
    KnownProvider(
        id="openrouter",
        display_name="OpenRouter",
        env_var="OPENROUTER_API_KEY",
        settings_field="api_key",
    ),
    KnownProvider(
        id="zai",
        display_name="z.ai",
        env_var="ZAI_API_KEY",
        settings_field="zai_api_key",
    ),
)

_BY_ID = {spec.id: spec for spec in KNOWN_PROVIDERS}


def provider_display_name(provider_id: str) -> str:
    spec = _BY_ID.get(provider_id)
    return spec.display_name if spec is not None else provider_id
