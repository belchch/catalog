# CATALOG-56 — Промпт параметр для скила типа AI

- **Задача Plane:** [CATALOG-56](https://app.plane.so/belchch/projects/catalog-app/work-items/56) (id: `25b3557d-4d22-4b0b-9bd7-106755a44719`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** На apply для skill `kind == "agent"` принимать необязательный runtime `prompt` и подмешивать его в стартовое user-сообщение (уточнение работы готового скилла). Для `script`/PYTHON — игнорировать/не принимать. UI textarea — в `CATALOG-56-ui-apply-prompt-field.md` (после этого шага).

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи)_

Доп. раздел — Промпт. Только для скилла типа AI. Для PYTHON не нужно. Пользователь может указать необязательный промпт и скорректировать работу готового скилла.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

- `ApplyRequest` сейчас: `doc_ids`, `persist`, `session_id` — **без** `prompt` (`backend/app/api/schemas.py:32-48`).
- Apply endpoint: `backend/app/api/runs.py` (~50–91) → `apply_skill`.
- Agent start: `backend/app/skills/apply.py` (~238–262) — `system_prompt=skill.system_prompt`, user message фиксирован (документы + инструкция). Runtime override нет.
- `kind`: `"agent" | "script"` (`config.py`); UI-теги `ai` / `python`.

Парный UI: `docs/plan/next-shift/CATALOG-56-ui-apply-prompt-field.md`.

## Затрагиваемые файлы

- `backend/app/api/schemas.py` — `ApplyRequest.prompt: str | None = None`
- `backend/app/api/runs.py` — прокинуть `prompt` в `apply_skill`
- `backend/app/skills/apply.py` — сигнатура + вставка в user start message только для agent
- `backend/tests/test_api.py` / `test_apply.py` — agent с prompt / script игнорирует

## План действий

1. **Схема.** Добавить optional `prompt` в `ApplyRequest`.
2. **Apply path.** Передать в `apply_skill(..., user_prompt: str | None = None)`.
3. **Agent.** Если `kind == "agent"` и prompt непустой — добавить блок в стартовое user-сообщение (после/рядом с документами), не заменяя `system_prompt` скилла.
4. **Script.** Не использовать поле (молча / no-op).
5. **Тесты.** Apply agent с prompt → текст уходит в LLM-сообщения (мок); script с prompt не ломается.

## Критерии приёмки (Definition of Done)

- [ ] `POST .../apply` принимает optional `prompt`.
- [ ] Для agent непустой prompt влияет на стартовый user turn.
- [ ] `system_prompt` скилла не перезаписывается.
- [ ] Для script поле безопасно игнорируется.
- [ ] `backend/`: `ruff check .`, `pytest` зелёные.
