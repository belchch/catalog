"""Skill configuration dataclasses with JSON (de)serialization.

A :class:`SkillConfig` is the *frozen* description of an agent run (ADR-0002):
system prompt, allowed tools, model, sampling params, and the deterministic
``verify`` checks. It is stored verbatim as ``config_json`` in the ``skill``
table so a committed skill is fully reproducible from its row alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class VerifyCheck:
    """A single deterministic check reference.

    ``check`` is the registry id from ``docs/verification-checks.md``;
    ``params`` is forwarded to the check function.
    """

    check: str
    params: dict = field(default_factory=dict)


@dataclass
class SkillConfig:
    """Frozen skill configuration consumed by :func:`apply_skill`.

    A skill has a ``kind`` (ADR-0014):

    - ``"agent"`` — the classic frozen agent config (ADR-0002): a
      function-calling loop driven by an LLM over ``allowed_tools``. This is
      the default for backward compatibility (old ``config_json`` without a
      ``kind`` deserializes as ``"agent"``).
    - ``"script"`` — a *deterministic* skill: pure Python source in ``code``
      executed by the script-runner with no agent loop and no LLM call at
      runtime. ``allowed_tools``/``model`` are irrelevant for scripts.
    """

    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str]
    model: str
    temperature: float = 0.0
    max_iterations: int = 8
    max_retries: int = 2
    verify_checks: list[VerifyCheck] = field(default_factory=list)
    output_kind: str = "md"
    # ``"agent"`` | ``"script"`` (ADR-0014). Default keeps legacy skills agent.
    kind: str = "agent"
    # Python source for ``kind="script"`` skills (empty for agent skills).
    code: str = ""
    # For ``kind="agent"``: the model's explanation of why the task is not
    # deterministic (CATALOG-3). Empty for ``script`` skills. Persisted so the
    # reason is captured alongside the config (DoD requirement).
    non_determinism_reason: str = ""
    # Expected number of input documents (CATALOG-4): ``1``, ``2``, ... or
    # ``None`` for an arbitrary-length list. ``None`` (the default) keeps the
    # legacy "any number >= 1" behaviour, so old configs deserialize unchanged.
    input_arity: int | None = None
    # LLM provider name for this skill (CATALOG-6), e.g. ``"openrouter"`` or
    # ``"zai"``. Empty = the app's active provider (back-compat default).
    provider: str = ""
    # Selected reasoning variant (CATALOG-6), e.g. ``"low"``/``"medium"``/
    # ``"high"`` for a reasoning-capable model. Empty = no explicit reasoning.
    reasoning: str = ""

    def to_json(self) -> str:
        """Serialize to a JSON string (stable, utf-8 friendly)."""
        return json.dumps(
            {
                "name": self.name,
                "description": self.description,
                "system_prompt": self.system_prompt,
                "allowed_tools": list(self.allowed_tools),
                "model": self.model,
                "temperature": self.temperature,
                "max_iterations": self.max_iterations,
                "max_retries": self.max_retries,
                "verify_checks": [
                    {"check": c.check, "params": dict(c.params)}
                    for c in self.verify_checks
                ],
                "output_kind": self.output_kind,
                "kind": self.kind,
                "code": self.code,
                "non_determinism_reason": self.non_determinism_reason,
                "input_arity": self.input_arity,
                "provider": self.provider,
                "reasoning": self.reasoning,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, s: str) -> SkillConfig:
        """Deserialize from a JSON string produced by :meth:`to_json`.

        Old ``config_json`` written before ``kind``/``code`` existed lacks
        those keys; they default to ``"agent"`` / ``""`` so legacy skills keep
        working without a migration.
        """
        data = json.loads(s)
        return cls(
            name=data["name"],
            description=data["description"],
            system_prompt=data["system_prompt"],
            allowed_tools=list(data.get("allowed_tools", [])),
            model=data["model"],
            temperature=data.get("temperature", 0.0),
            max_iterations=data.get("max_iterations", 8),
            max_retries=data.get("max_retries", 2),
            verify_checks=[
                VerifyCheck(
                    check=vc["check"], params=dict(vc.get("params", {}))
                )
                for vc in data.get("verify_checks", [])
            ],
            output_kind=data.get("output_kind", "md"),
            kind=data.get("kind", "agent"),
            code=data.get("code", ""),
            non_determinism_reason=data.get("non_determinism_reason", ""),
            input_arity=data.get("input_arity"),
            provider=data.get("provider", ""),
            reasoning=data.get("reasoning", ""),
        )


def ensure_read_document_tool(allowed_tools: list[str]) -> list[str]:
    tools = list(allowed_tools)
    if "read_document" not in tools:
        tools.append("read_document")
    return tools


def compute_tags(config: SkillConfig) -> list[str]:
    """Derive capability tags from a skill config (CATALOG-8).

    The tags are a *derived*, user-facing view of what a skill can do:

    - ``"python"`` — the skill contains deterministic Python code
      (``kind == "script"`` or non-empty ``code``).
    - ``"ai"`` — the skill is LLM-driven / non-deterministic
      (``kind == "agent"`` or a non-empty ``system_prompt`` on a non-script
      skill).

    A genuinely mixed skill (e.g. an agent that also carries ``code``) gets
    both tags; the result is a list, not a mutually-exclusive enum.

    ``model`` is intentionally *not* used as a signal: it is always populated
    (even ``kind="script"`` skills store the default model for config
    uniformity — see ``_args_to_config``), so it cannot distinguish an agent
    from a script and would mis-tag pure scripts as ``"ai"``.
    """
    tags: list[str] = []
    if config.kind == "script" or bool(config.code):
        tags.append("python")
    if config.kind == "agent" or (
        bool(config.system_prompt) and config.kind != "script"
    ):
        tags.append("ai")
    return tags
