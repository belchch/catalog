# CATALOG-121 — Verify: показывать список всех проверок, включая пройденные

- **Задача Plane:** [CATALOG-121](https://app.plane.so/belchch/projects/catalog-app/work-items/121) (id: `04f9fdde-9114-4b0b-b6fe-08ff6e91ffb5`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 00 · независимый
- **Цель:** `VerifyResult` несёт полный список исходов проверок (`checks`), а не только сводку `passed`/`failures`. Живой WS-стрим и сохранённый трейс получают это поле; ранние выходы помечаются как `skipped`, а не теряются.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Сейчас verify отдаёт только сводку: `VerifyResult(passed: bool, failures: list[str])`. Пройденные проверки не видны ни в стриме, ни в трейсе.

Backend-часть:

- `verify.py`: расширить `VerifyResult` полем `checks: list[CheckOutcome]`, где `CheckOutcome = {check, params, passed, reason, source: builtin|custom, skipped}`. Поля `passed`/`failures` сохранить.
- `run_verify`: unknown check и custom-check сейчас делают ранний `return` — остальные проверки не выполняются. Отразить это как `skipped=True`.
- `run_verify_async`: custom-judge не запускаются, если детерминированные упали — пометить `skipped=True`. При успехе judge тоже писать в `checks`.
- `deps.py` (~114): добавить `checks` в WS-payload `VerifyEvent`.
- `apply.py`: во всех трёх `TraceEntry(kind="verify")` класть `checks` рядом с `passed`/`failures`.

Связано с CATALOG-115 (там сохранялась только сводка). UI-часть — парный план `01-CATALOG-121-ui-verify-checks-list.md`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Сводка без списка исходов:

- `backend/catalog/skills/verify.py:22-26` — `VerifyResult` только `passed` + `failures`.
- `backend/catalog/skills/verify.py:139-153` — `run_verify` при custom/unknown сразу `return`, хвост списка не прогоняется и не помечается.
- `backend/catalog/skills/verify.py:236-258` — `run_verify_async` при провале детерминированных не запускает judge и не пишет успешные custom в `checks`.
- `backend/catalog/api/deps.py:114-122` — WS `VerifyEvent` отдаёт только `passed`/`failures`.
- `backend/catalog/skills/apply.py:391-398`, `526-533`, `618-626` — в трейс кладётся та же сводка.
- `backend/catalog/agent/logging.py` — сериализация `VerifyEvent` тоже без `checks`.

Парный UI-план ждёт это поле: `docs/plan/1-shift/01-CATALOG-121-ui-verify-checks-list.md`.

## Затрагиваемые файлы
- `backend/catalog/skills/verify.py` — `CheckOutcome`, поле `checks`, прогон без молчаливой потери хвоста.
- `backend/catalog/api/deps.py` — `checks` в WS-payload.
- `backend/catalog/agent/logging.py` — то же в лог-сериализации, если зеркалит payload.
- `backend/catalog/skills/apply.py` — `checks` в трёх `TraceEntry(kind="verify")`.
- `backend/tests/test_verify.py` / `backend/tests/test_apply.py` — исходы, skipped, обратная совместимость `passed`/`failures`.

## План действий
1. Добавить `CheckOutcome` и поле `checks` в `VerifyResult`; `passed`/`failures` оставить источником истины для ретрая.
2. В `run_verify` не терять хвост: unknown/custom — запись с `skipped=True` (и `passed=False` у unknown), остальные checks всё равно отразить. Сводка `failures` как сейчас.
3. В `run_verify_async` при провале детерминированных пометить не запущенные custom как `skipped=True`; при успехе judge писать запись в `checks` и при PASS, и при FAIL.
4. Прокинуть `checks` в WS (`deps.py`) и в три `TraceEntry` в `apply.py`.
5. Тесты: полный список при смеси pass/fail; unknown → skipped хвост; custom не запущен при fail детерминированных; успешный judge виден в `checks`.

## Критерии приёмки (Definition of Done)
- [ ] `VerifyResult.checks` содержит исход каждой проверки (`builtin`/`custom`, `skipped` при раннем выходе).
- [ ] `passed`/`failures` не ломают ретрай и существующие тесты.
- [ ] WS `VerifyEvent` и три `TraceEntry(kind="verify")` несут `checks`.
- [ ] Тесты на skipped/полный список зелёные.
- [ ] `ruff check .`, `pytest` из `backend/`.
