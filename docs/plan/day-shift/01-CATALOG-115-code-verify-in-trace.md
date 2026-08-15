# CATALOG-115 — Результаты verify в сохранённом трейсе прогона

- **Задача Plane:** [CATALOG-115](https://app.plane.so/belchch/projects/catalog-app/work-items/115) (id: `8c608179-0751-4f4a-ad3a-aed0f3db8aa5`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 01 · независимый
- **Цель:** Каждый вызов `run_verify` пишет `TraceEntry(kind="verify")` в `skill_run.trace_json`, чтобы при открытии старого прогона были видны passed/failures, а не только `status='failed'`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. Шаг 2 из 7. Независим на старте.

`VerifyEvent` уходит в WS, но `TraceEntry` не создаётся. Рядом с тремя `run_verify` (script, pipeline, agent-retry) добавить `trace.entries.append(TraceEntry(kind="verify", iteration=..., data={"passed": ..., "failures": [...]}))`.

Фронт не трогать: `TraceSteps.tsx` уже умеет `kind='verify'`.

Референс: тег `backup-pre-revert-0234`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Три живых вызова без записи в trace:

- `backend/catalog/skills/apply.py:341` — script.
- `backend/catalog/skills/apply.py:460` — pipeline (после последнего шага).
- `backend/catalog/skills/apply.py:536` — agent-retry (внутри цикла, `iteration=r+1`).

Рядом уже пишутся `TraceEntry` других kind (`script`, `error`). `TraceEntry.kind` в `backend/catalog/agent/trace.py:8-10` в комментарии не упоминает `verify` — расширить фактическим использованием, комментарий в код не добавлять (правило репо).

Маппинг сохранённого трейса в `RunStep` — `backend/catalog/api/runs.py` / схемы. Рендер: `frontend/src/components/TraceSteps.tsx`.

## Затрагиваемые файлы
- `backend/catalog/skills/apply.py` — три `TraceEntry(kind="verify")`.
- `backend/tests/test_apply.py` — сохранённый трейс содержит verify с failures.
- При необходимости `backend/catalog/api/runs.py` — только если маппинг `kind=verify` отсутствует (проверить, не чинить фронт).

## План действий
1. После каждого `run_verify` + `VerifyEvent` дописать `TraceEntry` с `passed` и `failures` из `VerifyResult`.
2. Для agent-retry писать на каждой итерации (`iteration=r+1`), не только на последней.
3. Тест: прогон с падающей проверкой → в `trace_json` есть `kind=verify` и список failures; успешный прогон — `passed: true`.
4. Убедиться, что API отдаёт эти записи как `RunStep kind=verify`. Фронт не менять.

## Критерии приёмки (Definition of Done)
- [ ] Все три пути `run_verify` пишут `TraceEntry(kind="verify")`.
- [ ] Сохранённый прогон показывает причины провала verify.
- [ ] Frontend не изменён.
- [ ] `ruff check .`, `pytest` из `backend/`.
