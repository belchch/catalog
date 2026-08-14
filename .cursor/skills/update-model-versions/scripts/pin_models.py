#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

TARGETS = [
    Path(".cursor/skills/pipeline-model-mode/SKILL.md"),
    Path(".cursor/skills/pipeline-model-mode/scripts/apply_mode.py"),
    Path(".cursor/skills/bugbot-grok-fix-loop/SKILL.md"),
    Path(".cursor/skills/catalog-pipeline/SKILL.md"),
    Path(".cursor/agents/catalog-generator.md"),
    Path(".cursor/agents/catalog-designer.md"),
    Path(".cursor/agents/catalog-reviewer.md"),
    Path(".cursor/agents/catalog-ui-reviewer.md"),
]

SLUG_RE = re.compile(
    r"(?:"
    r"cursor-grok-[\d.]+(?:-[A-Za-z0-9]+)*(?:\[[^\]]+\])?"
    r"|claude-(?:opus|sonnet)-[\d.]+(?:-[\d.]+)?(?:-[A-Za-z0-9]+)*(?:\[[^\]]+\])?"
    r"|gemini-[\d.]+-flash(?:-[A-Za-z0-9]+)*(?:\[[^\]]+\])?"
    r"|glm-[\d.]+(?:-turbo)?"
    r"|composer-[\d.]+(?:-[A-Za-z0-9]+)*"
    r"|gpt-[\d.]+(?:-[A-Za-z0-9.]+)*"
    r"|Grok [\d.]+"
    r")"
)


def scan() -> int:
    found: dict[str, list[str]] = {}
    missing = False
    for rel in TARGETS:
        path = REPO_ROOT / rel
        if not path.is_file():
            print(f"MISSING {rel}", file=sys.stderr)
            missing = True
            continue
        text = path.read_text(encoding="utf-8")
        for match in SLUG_RE.finditer(text):
            slug = match.group(0)
            found.setdefault(slug, []).append(str(rel))
    if not found:
        print("Пинов не найдено.")
        return 2 if missing else 0
    for slug in sorted(found):
        files = ", ".join(dict.fromkeys(found[slug]))
        print(f"{slug}\t{files}")
    return 2 if missing else 0


def apply(mapping: dict[str, str]) -> int:
    keys = sorted((old for old, new in mapping.items() if old != new), key=len, reverse=True)
    if not keys:
        print("Изменений нет.")
        return 0
    changed = False
    for rel in TARGETS:
        path = REPO_ROOT / rel
        if not path.is_file():
            print(f"MISSING {rel}", file=sys.stderr)
            return 2
        text = path.read_text(encoding="utf-8")
        new_text = text
        hits: list[tuple[str, str, int]] = []
        for old in keys:
            count = new_text.count(old)
            if count:
                new_text = new_text.replace(old, mapping[old])
                hits.append((old, mapping[old], count))
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            if not changed:
                print("Изменено:")
                changed = True
            print(f"  {rel}")
            for old, new, count in hits:
                print(f"    {old} -> {new} ({count})")
    if not changed:
        print("Изменений нет.")
    return 0


def load_mapping(src: str) -> dict[str, str]:
    raw = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        raise ValueError("mapping must be a JSON object of string -> string")
    return data


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in {"scan", "apply"}:
        print("usage: pin_models.py scan | apply <mapping.json|->", file=sys.stderr)
        return 2
    if argv[1] == "scan":
        return scan()
    if len(argv) < 3:
        print("ERROR: apply требует mapping.json или -", file=sys.stderr)
        return 2
    try:
        mapping = load_mapping(argv[2])
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return apply(mapping)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
