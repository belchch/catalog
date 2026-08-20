from __future__ import annotations

from catalog.agent.registry import ToolRegistry
from catalog.llm.base import ToolSpec
from catalog.skills.config import SkillOutput

EMIT_OUTPUT_NAME = "emit_output"


def uses_emit_output(outputs: list[SkillOutput]) -> bool:
    return len(outputs) > 1


def named_outputs_prompt(outputs: list[SkillOutput]) -> str:
    lines = [
        "",
        "Именованные выходы. Заполни каждый через emit_output(key, text) "
        "и заверши только после заполнения всех:",
    ]
    for item in outputs:
        lines.append(f"- {item.key}: {item.description}")
    return "\n".join(lines)


def named_output_failures(
    outputs: list[SkillOutput], artifacts: dict[str, str]
) -> list[str]:
    declared = [item.key for item in outputs]
    missing = [key for key in declared if key not in artifacts]
    empty = [
        key
        for key in declared
        if key in artifacts and not (artifacts.get(key) or "").strip()
    ]
    parts: list[str] = []
    if missing:
        parts.append("missing output key(s): " + ", ".join(missing))
    if empty:
        parts.append("empty output value(s): " + ", ".join(empty))
    return parts


def primary_output_text(
    outputs: list[SkillOutput],
    artifacts: dict[str, str],
    fallback: str | None,
) -> str | None:
    if outputs and outputs[0].key in artifacts:
        return artifacts[outputs[0].key]
    return fallback


def emit_output_spec(outputs: list[SkillOutput]) -> ToolSpec:
    keys = [item.key for item in outputs]
    key_lines = "; ".join(f"{item.key}: {item.description}" for item in outputs)
    return ToolSpec(
        name=EMIT_OUTPUT_NAME,
        description=(
            "Write one named skill output. Call once per key, then stop "
            f"after every key is filled. Keys: {key_lines}."
        ),
        parameters={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "enum": keys,
                    "description": "Declared output key.",
                },
                "text": {
                    "type": "string",
                    "description": "Full text for this output.",
                },
            },
            "required": ["key", "text"],
            "additionalProperties": False,
        },
    )


def register_emit_output(
    tools: ToolRegistry,
    outputs: list[SkillOutput],
    sink: dict[str, str],
) -> None:
    spec = emit_output_spec(outputs)

    async def _emit_output(*, key: str, text: str) -> dict[str, object]:
        sink[key] = text
        return {"ok": True, "key": key, "chars": len(text)}

    tools.register(spec, _emit_output)
