"""z.ai (Zhipu / BigModel, GLM) provider.

z.ai exposes an OpenAI-compatible Chat Completions API at
``https://api.z.ai/api/paas/v4``. The wire dialect is the same as OpenRouter
(``/chat/completions``, SSE ``data:`` + ``[DONE]``, function calling,
``Authorization: Bearer``), so this provider is a thin subclass of
:class:`OpenAICompatibleProvider`.

Two z.ai specifics:

* **Model catalog** — z.ai's ``/models`` endpoint is unreliable / differently
  shaped, so :meth:`list_models` returns a hardcoded GLM catalog.
* **Reasoning models** — GLM thinking models emit ``reasoning_content``
  alongside ``content`` (in both the non-streaming ``message`` and the
  streaming ``delta``). The base class already collects and forwards it via
  :class:`~app.llm.base.CompletionResult.reasoning` and
  :class:`~app.llm.base.StreamDelta.reasoning`.

See ADR-0013.
"""

from __future__ import annotations

from app.llm.base import ModelInfo
from app.llm.openai_compatible import OpenAICompatibleProvider

# Hardcoded GLM model catalog (z.ai /models is unreliable). Context lengths
# are the documented maximums; update here when z.ai ships new models.
# GLM "thinking"/"X" models expose an explicit reasoning mode (CATALOG-6).
_REASONING_VARIANTS = ["low", "medium", "high"]
_ZAI_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="glm-4.6",
        name="GLM-4.6",
        context_length=131072,
        supports_reasoning=True,
        reasoning_variants=list(_REASONING_VARIANTS),
    ),
    ModelInfo(id="glm-4.5", name="GLM-4.5", context_length=131072),
    ModelInfo(id="glm-4.5-air", name="GLM-4.5-Air", context_length=131072),
    ModelInfo(id="glm-4.5-flash", name="GLM-4.5-Flash", context_length=131072),
    ModelInfo(
        id="glm-4.5-x",
        name="GLM-4.5-X",
        context_length=131072,
        supports_reasoning=True,
        reasoning_variants=list(_REASONING_VARIANTS),
    ),
    ModelInfo(id="glm-4-plus", name="GLM-4-Plus", context_length=131072),
]


class ZaiProvider(OpenAICompatibleProvider):
    """z.ai / GLM provider (https://api.z.ai/api/paas/v4)."""

    def __init__(
        self,
        client,
        api_key: str,
        base_url: str = "https://api.z.ai/api/paas/v4",
        *,
        max_retries: int = 3,
        backoff_base: float = 0.5,
    ) -> None:
        super().__init__(
            client,
            api_key,
            base_url,
            provider_name="zai",
            max_retries=max_retries,
            backoff_base=backoff_base,
            auth_error_message="Invalid z.ai API key — check ZAI_API_KEY in .env",
        )

    async def list_models(self) -> list[ModelInfo]:
        """Return the hardcoded GLM catalog (z.ai /models is unreliable)."""
        return list(_ZAI_MODELS)
