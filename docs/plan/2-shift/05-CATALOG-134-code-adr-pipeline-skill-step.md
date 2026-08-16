# CATALOG-134 — ADR-0022: шаг pipeline типа skill — вызов замороженного скилла как шага

- **Задача Plane:** [CATALOG-134](https://app.plane.so/belchch/projects/catalog-app/work-items/134) (id: `ccb80b55-1bfd-4036-9dd9-42c94703b06a`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 05 · blocking CATALOG-135
- **Цель:** Принять ADR-0022: третий тип шага `skill` — ссылка в черновике, снапшот на сборке, вложенный apply в рантайме. Только документ.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code (только документ). Первый шаг, блокирует остальные — политика, на которую они опираются.

Зафиксировать в ADR:

1. Третий тип шага — `skill`, рядом с `script` и `llm`.
2. Ссылка только в черновике (`skill_id`); сборка разворачивает полный снапшот + `skill_id` / `skill_name` / `config_hash`. ADR-0002: собранный конфиг самодостаточен.
3. Не живая ссылка: нет версионной таблицы; ADR-0019 п.5 уже отклонил пин по `updated_at`.
4. Рантайм: вложенный `skill_run` с `parent_run_id`, `persist=False`; вход — значение шага (ADR-0018); выход — `result_text`. Механика в `skill_tools.py:290-337`.
5. verify вложенного — постусловие шага; провал останавливает пайплайн (нет модели, которая могла бы отреагировать).
6. Потолок и бюджет ADR-0021; `estimate_skill_llm_calls` для `skill`-шага рекурсивно.
7. Цикл невозможен by construction: снапшот развёрнут и наружу не ссылается.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Композиция скиллов есть в сессии и теряется при сборке:

- `backend/catalog/skills/config.py:15` — `PIPELINE_STEP_TYPES = ("script", "llm")`.
- `backend/catalog/api/skills.py:447-548` — `_build_skill_from_artifacts` заливает только `prompt`/`script` в пустые шаги.
- `backend/catalog/api/sessions.py` / `skills.py:405` — `allowed_tools` по базовому реестру; top-level run — только документные тулы (`runs.py:233-235`); filter fail-closed.
- `docs/adr/0002-skill-as-frozen-config.md`, `0018-pipeline-skills.md`, `0019-skill-as-session-tool.md`, `0021-skill-tool-budget.md`.
- `docs/adr/README.md` — индекс до 0021.

Следующие шаги: `CATALOG-135` (схема/сборка), `CATALOG-136` (рантайм), `CATALOG-137` (UI).

## Затрагиваемые файлы
- `docs/adr/0022-pipeline-skill-step.md` — новый ADR, статус Accepted, Extends 0002/0018/0019/0021.
- `docs/adr/README.md` — строка в индексе.

## План действий
1. Написать ADR по шаблону существующих (Context → Decision → Consequences → Alternatives considered).
2. Alternatives: живая ссылка + версионная таблица (отложено); `skill_*` в `allowed_tools` (ломает воспроизводимость); копипаст чужого скилла руками (как сейчас).
3. Consequences: снапшот не обновляется вслед за источником.
4. Обновить индекс.

## Критерии приёмки (Definition of Done)
- [ ] `docs/adr/0022-pipeline-skill-step.md` создан, Accepted, Extends ADR-0002/0018/0019/0021.
- [ ] Alternatives considered содержит три отклонённых варианта из ТЗ.
- [ ] Consequences честно фиксирует минус снапшота.
- [ ] `docs/adr/README.md` обновлён.
