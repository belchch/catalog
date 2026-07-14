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
    """Frozen agent configuration consumed by :func:`apply_skill`."""

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
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, s: str) -> SkillConfig:
        """Deserialize from a JSON string produced by :meth:`to_json`."""
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
        )
