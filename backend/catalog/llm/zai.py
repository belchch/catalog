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
  :class:`~catalog.llm.base.CompletionResult.reasoning` and
  :class:`~catalog.llm.base.StreamDelta.reasoning`.

See ADR-0013.
"""

from __future__ import annotations

from typing import Any

from catalog.llm.base import ModelInfo
from catalog.llm.openai_compatible import OpenAICompatibleProvider

_REASONING_VARIANTS = ["high", "max"]
_ZAI_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="glm-5.2",
        name="GLM-5.2",
        context_length=1048576,
        supports_reasoning=True,
        reasoning_variants=list(_REASONING_VARIANTS),
    ),
    ModelInfo(
        id="glm-5.1",
        name="GLM-5.1",
        context_length=200000,
        supports_reasoning=True,
        reasoning_variants=list(_REASONING_VARIANTS),
    ),
    ModelInfo(
        id="glm-5",
        name="GLM-5",
        context_length=200000,
        supports_reasoning=True,
        reasoning_variants=list(_REASONING_VARIANTS),
    ),
    ModelInfo(
        id="glm-5-turbo",
        name="GLM-5-Turbo",
        context_length=200000,
        supports_reasoning=True,
        reasoning_variants=list(_REASONING_VARIANTS),
    ),
    ModelInfo(
        id="glm-4.7",
        name="GLM-4.7",
        context_length=200000,
        supports_reasoning=True,
        reasoning_variants=list(_REASONING_VARIANTS),
    ),
    ModelInfo(
        id="glm-4.6",
        name="GLM-4.6",
        context_length=200000,
        supports_reasoning=True,
        reasoning_variants=list(_REASONING_VARIANTS),
    ),
    ModelInfo(id="glm-4.5", name="GLM-4.5", context_length=131072),
    ModelInfo(id="glm-4.5-air", name="GLM-4.5-Air", context_length=131072),
]

DEFAULT_ZAI_MODEL = "glm-5.2"


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

    def _normalize_model(self, model: str) -> str:
        prefix = f"{self._provider_name}/"
        if model.startswith(prefix):
            return model[len(prefix) :]
        return model

    def _apply_reasoning(self, body: dict[str, Any], reasoning: str) -> None:
        if not reasoning:
            return
        body["thinking"] = {"type": "enabled"}
        body["reasoning_effort"] = reasoning

    async def list_models(self) -> list[ModelInfo]:
        """Return the hardcoded GLM catalog (z.ai /models is unreliable)."""
        return list(_ZAI_MODELS)
