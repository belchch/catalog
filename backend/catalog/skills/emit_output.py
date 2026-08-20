from __future__ import annotations

from catalog.agent.registry import ToolRegistry
from catalog.llm.base import ToolSpec
from catalog.skills.config import SkillOutput

EMIT_OUTPUT_NAME = "emit_output"

# ADR-0025: the value of a single named output — ``list[str]`` for a
# ``multiple`` key (one element per call), ``str`` otherwise. Duplicated from
# ``catalog.skills.apply.ArtifactValue`` (same structural type) to avoid a
# circular import (``apply.py`` imports this module).
ArtifactValue = str | list[str]


def uses_emit_output(outputs: list[SkillOutput]) -> bool:
    # ADR-0025: a single *collection* output still needs the tool — the model
    # calls it once per element, not once for the whole result.
    return len(outputs) > 1 or any(item.multiple for item in outputs)


def named_outputs_prompt(outputs: list[SkillOutput]) -> str:
    lines = [
        "",
        "Именованные выходы. Заполни каждый через emit_output(key, text) "
        "и заверши только после заполнения всех:",
    ]
    for item in outputs:
        if item.multiple:
            lines.append(
                f"- {item.key} (коллекция): {item.description}. Вызывай "
                "emit_output для этого ключа отдельно на каждый элемент — "
                "вызовы накапливаются в список, а не перезаписывают друг "
                "друга."
            )
        else:
            lines.append(f"- {item.key}: {item.description}")
    return "\n".join(lines)


def named_output_failures(
    outputs: list[SkillOutput], artifacts: dict[str, ArtifactValue]
) -> list[str]:
    missing: list[str] = []
    empty: list[str] = []
    for item in outputs:
        key = item.key
        if key not in artifacts:
            missing.append(key)
            continue
        value = artifacts[key]
        if item.multiple:
            elements = value if isinstance(value, list) else []
            if not elements or any(not (elem or "").strip() for elem in elements):
                empty.append(key)
        else:
            text = value if isinstance(value, str) else ""
            if not text.strip():
                empty.append(key)
    parts: list[str] = []
    if missing:
        parts.append("missing output key(s): " + ", ".join(missing))
    if empty:
        parts.append("empty output value(s): " + ", ".join(empty))
    return parts


def _join_collection(value: list[str]) -> str:
    if len(value) == 1:
        return value[0]
    return "\n\n---\n\n".join(value)


def primary_output_text(
    outputs: list[SkillOutput],
    artifacts: dict[str, ArtifactValue],
    fallback: str | None,
) -> str | None:
    if outputs and outputs[0].key in artifacts:
        value = artifacts[outputs[0].key]
        if isinstance(value, list):
            return _join_collection(value)
        return value
    return fallback


def emit_output_spec(outputs: list[SkillOutput]) -> ToolSpec:
    keys = [item.key for item in outputs]
    key_lines = "; ".join(
        f"{item.key}{' [multiple: call once per element]' if item.multiple else ''}"
        f": {item.description}"
        for item in outputs
    )
    return ToolSpec(
        name=EMIT_OUTPUT_NAME,
        description=(
            "Write one named skill output. Call once per key, then stop "
            "after every key is filled. For a 'multiple' key, call again for "
            "each collection element instead of writing them all in one "
            f"call — calls accumulate into a list. Keys: {key_lines}."
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
                    "description": "Full text for this output (or this element).",
                },
            },
            "required": ["key", "text"],
            "additionalProperties": False,
        },
    )


def register_emit_output(
    tools: ToolRegistry,
    outputs: list[SkillOutput],
    sink: dict[str, ArtifactValue],
) -> None:
    spec = emit_output_spec(outputs)
    multiple_keys = {item.key for item in outputs if item.multiple}

    async def _emit_output(*, key: str, text: str) -> dict[str, object]:
        if key in multiple_keys:
            bucket = sink.get(key)
            if not isinstance(bucket, list):
                bucket = []
            bucket.append(text)
            sink[key] = bucket
            return {"ok": True, "key": key, "chars": len(text), "count": len(bucket)}
        sink[key] = text
        return {"ok": True, "key": key, "chars": len(text)}

    tools.register(spec, _emit_output)
