#!/usr/bin/env python3
"""Переключатель режима моделей для catalog-pipeline.

Атомарно переписывает поле `model:` в frontmatter четырёх агентов
catalog-* между двумя пресетами: default и glm. Не трогает parent-skill
catalog-pipeline/SKILL.md — модель parent'а выбирает пользователь в UI/CLI.

Команды:
    status         показать текущий режим и результирующие модели
    list           распечатать пресеты
    set <mode>     применить режим (default | glm)

State-файл: .cursor/state/pipeline-model-mode.json (в .gitignore).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
AGENTS_DIR = REPO_ROOT / ".cursor" / "agents"
STATE_FILE = REPO_ROOT / ".cursor" / "state" / "pipeline-model-mode.json"

ROLES: list[tuple[str, str]] = [
    ("catalog-generator", str(AGENTS_DIR / "catalog-generator.md")),
    ("catalog-designer", str(AGENTS_DIR / "catalog-designer.md")),
    ("catalog-reviewer", str(AGENTS_DIR / "catalog-reviewer.md")),
    ("catalog-ui-reviewer", str(AGENTS_DIR / "catalog-ui-reviewer.md")),
]

MODES: dict[str, dict[str, str]] = {
    "default": {
        "catalog-generator": "cursor-grok-4.5[effort=high]",
        "catalog-designer": "claude-opus-4-8[effort=high]",
        "catalog-reviewer": "claude-sonnet-5[effort=high]",
        "catalog-ui-reviewer": "gemini-3.5-flash",
    },
    "glm": {
        "catalog-generator": "glm-5-turbo",
        "catalog-designer": "glm-5.2",
        "catalog-reviewer": "claude-sonnet-5[effort=high]",
        "catalog-ui-reviewer": "gemini-3.5-flash",
    },
}

FRONTMATER_RE = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)
MODEL_LINE_RE = re.compile(r"^model:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


def read_current_model(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATER_RE.match(text)
    if not m:
        return None
    fm = m.group(1)
    mm = MODEL_LINE_RE.search(fm)
    if not mm:
        return None
    return mm.group(1).strip()


def detect_mode() -> str | None:
    snapshot = {role: read_current_model(Path(p)) for role, p in ROLES}
    for mode, preset in MODES.items():
        if snapshot == preset:
            return mode
    return None


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(data: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def apply_mode(mode: str) -> int:
    preset = MODES[mode]
    snapshot = {role: read_current_model(Path(p)) for role, p in ROLES}

    missing: list[str] = []
    for role, _ in ROLES:
        if snapshot[role] is None:
            missing.append(role)
    if missing:
        print(f"ERROR: нет поля `model:` в frontmatter у: {', '.join(missing)}", file=sys.stderr)
        print("Никакие файлы не изменены.", file=sys.stderr)
        return 2

    changed: list[tuple[str, str, str]] = []
    for role, path in ROLES:
        target = preset[role]
        current = snapshot[role]
        if current == target:
            continue
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        fm_match = FRONTMATER_RE.match(text)
        if not fm_match:
            print(f"ERROR: нет frontmatter в {path}", file=sys.stderr)
            return 2
        fm = fm_match.group(1)
        if MODEL_LINE_RE.search(fm) is None:
            print(f"ERROR: нет `model:` в frontmatter {path}", file=sys.stderr)
            return 2
        new_fm = MODEL_LINE_RE.sub(f"model: {target}", fm, count=1)
        new_text = text[: fm_match.start(1)] + new_fm + text[fm_match.end(1):]
        dir_fd = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(p.parent), prefix=p.name + ".", suffix=".tmp", delete=False
        )
        dir_fd.write(new_text)
        dir_fd.flush()
        os.fsync(dir_fd.fileno())
        dir_fd.close()
        os.replace(dir_fd.name, str(p))
        changed.append((role, current or "", target))

    save_state({"mode": mode, "modes": list(MODES.keys())})
    print(f"Режим: {mode}")
    if not changed:
        print("Файлы уже соответствуют пресету — изменений нет.")
    else:
        print("Изменено:")
        for role, old, new in changed:
            print(f"  {role}: {old}  ->  {new}")
    print_snapshot()
    return 0


def print_snapshot() -> None:
    print("Текущие `model:` в агентах:")
    detected = detect_mode()
    label = detected if detected else "(не соответствует ни одному пресету)"
    print(f"  Опознанный режим: {label}")
    for role, path in ROLES:
        cur = read_current_model(Path(path)) or "<нет>"
        marks = {m: "✓" if MODES[m][role] == cur else "·" for m in MODES}
        mark_str = " ".join(f"{m}:{marks[m]}" for m in MODES)
        print(f"  {role:<24} {cur:<40} [{mark_str}]")


def cmd_status() -> int:
    st = load_state()
    print(f"State-файл: {STATE_FILE} ({'есть' if STATE_FILE.exists() else 'нет'})")
    print(f"Запомненный режим (state): {st.get('mode', '(нет)')}")
    print_snapshot()
    return 0


def cmd_list() -> int:
    print("Пресеты режимов:")
    for mode, preset in MODES.items():
        print(f"\n[{mode}]")
        for role, p in ROLES:
            print(f"  {role:<24} {preset[role]}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "status":
        return cmd_status()
    if cmd == "list":
        return cmd_list()
    if cmd == "set":
        if len(argv) < 3:
            print("ERROR: `set` требует аргумент: default | glm", file=sys.stderr)
            return 2
        mode = argv[2].strip().lower()
        if mode not in MODES:
            print(f"ERROR: неизвестный режим {mode!r}. Допустимо: {', '.join(MODES)}", file=sys.stderr)
            return 2
        return apply_mode(mode)
    print(f"ERROR: неизвестная команда {cmd!r}. Допустимо: status | list | set <mode>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
