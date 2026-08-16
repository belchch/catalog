# CATALOG-126 — Дедлайн хода сессии для вложенных вызовов

- **Задача Plane:** [CATALOG-126](https://app.plane.so/belchch/projects/catalog-app/work-items/126) (id: `b256a99b-d0e9-4e8d-b95b-c4efbef47248`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 05 · blocked_by CATALOG-125 · blocking CATALOG-127 · blocking CATALOG-129
- **Цель:** Стабильный дедлайн хода `max(600, llm_timeout_seconds × 15)` в том же `SkillBudget`. Истечение — отказ в tool result с отдельным кодом, не раньше бюджета при штатных 60 вызовах.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. После бюджета (CATALOG-125), до снятия фильтра script-only.

Дедлайн — детектор зависания, не лимит стоимости. Не должен срабатывать раньше бюджета.

1. `max(600, llm_timeout_seconds × 15)` — на дефолтных 60 с это 15 минут.
2. Таймаут посессионный: `session_row.llm_timeout_seconds` (30–300).
3. `deadline = monotonic() + секунды` на старте хода, дальше не менять. Поле в `SkillBudget`.
4. Проверка перед каждым вложенным запуском и между итерациями агентного цикла.
5. Истечение — tool result с отдельным кодом причины, не исключение.

Отдельный дедлайн на один вложенный запуск не делать.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `SkillBudget` из `docs/plan/1-shift/04-CATALOG-125-code-skill-budget.md`.

- `backend/catalog/api/sessions.py` ~851–856 — `session_row.llm_timeout_seconds` и `llm_timeout_context`.
- `backend/catalog/api/schemas.py:168` — диапазон 30–300.
- `backend/catalog/agent/timeout.py` — повызовный таймаут провайдера (не путать с дедлайном хода).
- Формат отказа — как `budget exhausted` в skill_tools, другой `error` (например `deadline exceeded`).

## Затрагиваемые файлы
- `backend/catalog/skills/skill_tools.py` — `deadline` в `SkillBudget`, проверка до вложенного запуска.
- `backend/catalog/api/sessions.py` — зафиксировать deadline от таймаута сессии.
- `backend/catalog/agent/runner.py` — проверка между итерациями вложенного цикла.
- `backend/tests/test_session_skill_tools.py` — истечение, формула от сессии, пол 600 с, бюджет раньше дедлайна.

## План действий
1. Добавить в `SkillBudget` поле `deadline_monotonic`.
2. Считать секунды от `session_row.llm_timeout_seconds`, пол 600.
3. Перед `apply_skill_collect` и между итерациями вложенного runner — если `monotonic() >= deadline`, tool result / останов цикла без исключения хода.
4. Не заводить второй таймер на один вложенный запуск.
5. Тесты из DoD (дедлайн в тестах подменять, не ждать 10 минут).

## Критерии приёмки (Definition of Done)
- [ ] Истёкший дедлайн → новый вложенный запуск не стартует.
- [ ] Формула от `llm_timeout_seconds` сессии, не глобальный дефолт.
- [ ] При таймауте 30 с дедлайн ≥ 600 с.
- [ ] При штатном бюджете 60 вызовов дедлайн не срабатывает первым.
- [ ] `ruff check .`, `pytest` из `backend/`.
