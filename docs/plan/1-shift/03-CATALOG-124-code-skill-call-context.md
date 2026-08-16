# CATALOG-124 — Контекст вложенного вызова скилла: глубина и цепочка

- **Задача Plane:** [CATALOG-124](https://app.plane.so/belchch/projects/catalog-app/work-items/124) (id: `98b86313-7620-421e-802f-e73d83f1a7cc`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 03 · blocked_by CATALOG-123 · blocking CATALOG-125 · blocking CATALOG-129
- **Цель:** Явный `SkillCallContext` (depth + chain) вместо невидимого инварианта «во вложенный запуск не передали skill-тулы». На глубине ≥ 2 реестр пуст; скилл из текущей цепочки не регистрируется.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. После ADR (CATALOG-123), до снятия фильтра script-only.

Сейчас глубина 1 — совпадение: в `skill_tools.py:148` во вложенный запуск уходит `base_tools` без skill-тулов. Сентинел `SESSION_TOOL_PARENT_RUN_ID = "session"` не несёт глубину.

1. `SkillCallContext` (frozen): `depth: int = 0`, `chain: tuple[str, ...] = ()`.
2. Прокинуть через `build_session_skill_tools` → `_run` → `apply_skill_collect` → `_apply_core`, рядом с `parent_run_id`.
3. Не регистрировать ничего при `depth >= MAX_SKILL_DEPTH` (= 2); не регистрировать скилл при `skill.id in chain`.
4. Вложенный запуск: `depth + 1`, `chain + (skill_id,)`.
5. Писать `depth` в трейс вложенного запуска и в ответ тула.

`MAX_SKILL_DEPTH` — в настройки приложения, не константа модуля.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Опирается на ADR-0021 из `docs/plan/1-shift/02-CATALOG-123-code-adr-skill-tool-budget.md`. Фильтр script-only пока не снимать (это CATALOG-127).

- `backend/catalog/skills/skill_tools.py:22` — сентинел `"session"`.
- `backend/catalog/skills/skill_tools.py:81-200` — сборка реестра; вложенный `apply_skill_collect` получает `base_tools`.
- `backend/catalog/skills/apply.py:172-191` — `_apply_core` уже принимает `parent_run_id`, контекста нет.
- `backend/catalog/config.py:36-49` — `Settings` без `max_skill_depth`.
- Тесты: `backend/tests/test_session_skill_tools.py`.

## Затрагиваемые файлы
- `backend/catalog/skills/skill_tools.py` — `SkillCallContext`, фильтры depth/chain, `depth` в tool result.
- `backend/catalog/skills/apply.py` — параметр контекста в `apply_skill_collect` / `_apply_core`; `depth` в трейс.
- `backend/catalog/config.py` — `max_skill_depth` (дефолт 2, env).
- `backend/catalog/api/sessions.py` — передать корневой контекст `depth=0` при сборке WS-тулов.
- `backend/tests/test_session_skill_tools.py` — глубина 2, chain, самовызов A→A.

## План действий
1. Добавить frozen `SkillCallContext` и поле `max_skill_depth` в `Settings`.
2. Прокинуть контекст по цепочке вызова; при вложении увеличивать depth и chain.
3. В `build_session_skill_tools`: пустой реестр skill-тулов при `depth >= max`; skip `id in chain`.
4. Писать `depth` в трейс run и в ответ тула.
5. Тесты из DoD; script-тулы на глубине 1 без регрессии.

## Критерии приёмки (Definition of Done)
- [ ] На глубине 2 вложенный реестр без skill-тулов.
- [ ] Скилл из chain не регистрируется, сосед на том же уровне — да.
- [ ] Самовызов A → A невозможен.
- [ ] Script-тулы на глубине 1 ведут себя как сейчас.
- [ ] `ruff check .`, `pytest` из `backend/`.
