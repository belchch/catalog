# CATALOG-112 — Блокировка воркспейса по идущему turn

- **Задача Plane:** [CATALOG-112](https://app.plane.so/belchch/projects/catalog-app/work-items/112) (id: `442b7390-d66e-429a-a749-a3e1eb139d67`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 04 · независимый
- **Цель:** Считать session-busy по числу идущих planner turn'ов, не по открытому WebSocket. Простаивающий чат не блокирует смену воркспейса.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Переключить воркспейс нельзя, пока открыт чат: `active_ws_sessions` растёт на `websocket.accept()` и падает только при разрыве. Probe в `main.py` — `active_ws_sessions > 0`. Фронт держит сокет всё время открытой сессии.

Реально уязвим только `_run_planner_turn` (локальный захват `db`). Простаивающее соединение смену переживает.

Что сделать (backend-часть):

- Busy = число идущих turn'ов: +1 перед `_run_planner_turn`, −1 в `finally`.
- То же для run-стрима, если он сидит на том же счётчике.
- Текст `WorkspaceBusyError` для session: «идёт ответ агента», не «planner session is active».
- Обновить `match=` в `test_workspace.py`.

Баннер на фронте — в парном ui-плане.

Вне скоупа: залипание `reason=run` по TTL skill_run.

## Предыстория
_нет — комментариев к задаче не было_

## Контекст
Парный UI-план: `docs/plan/night-shift/05-CATALOG-112-ui-busy-banner.md` (после этого code).

- `backend/catalog/api/sessions.py:754-761` — `_inc/_dec_active_ws_sessions`.
- Там же `:771` — инкремент сразу после `accept()`; `:889` — декремент в `finally` сокета.
- Там же `:848-858` — вызов `_run_planner_turn` без отдельного счётчика.
- `backend/catalog/main.py:91-94` — `active_ws_sessions = 0`, probe `> 0`.
- `backend/catalog/storage/workspace.py:202-218` — `has_running()` / `_assert_no_running()`: `"cannot switch workspace while a planner session is active"`.
- `backend/catalog/api/workspaces.py:48` — `GET /workspaces/busy` читает `has_running()`.
- `backend/tests/test_workspace.py:198-214, 233+` — `match="planner session"`.
- Run-стрим: `has_running_runs` в БД, не `active_ws_sessions`. Тот же счётчик не использует — трогать не нужно, только проверить.

## Затрагиваемые файлы
- `backend/catalog/api/sessions.py` — счётчик turn'ов вокруг `_run_planner_turn`; убрать inc/dec с accept/close.
- `backend/catalog/main.py` — probe на новый счётчик (или то же имя с новой семантикой).
- `backend/catalog/storage/workspace.py` — текст ошибки session-busy.
- `backend/tests/test_workspace.py` — `match` и смысл «busy = turn».
- `backend/tests/test_api.py` — если есть тесты `/workspaces/busy` на открытый WS.

## План действий
1. Завести `active_planner_turns` (или переопределить семантику `active_ws_sessions`): +1 перед `_run_planner_turn`, −1 в `finally` этого вызова. Accept/close сокета счётчик не трогают.
2. Probe в lifespan: `> 0` по turn-счётчику.
3. Текст `_assert_no_running` для session: про идущий ответ агента.
4. Тесты: открытый сокет без turn → `has_running()` не `session`, switch/close проходят; во время turn → `session`, 409. Счётчик не залипает на cancel/exception.
5. `ruff check .`, `pytest` из `backend/`.

## Критерии приёмки (Definition of Done)
- [ ] Чат открыт, генерации нет → `GET /workspaces/busy` даёт `busy=false`, воркспейс переключается.
- [ ] Во время ответа агента → `busy=true`, `reason="session"`, switch/close = 409.
- [ ] После finish / cancel / ошибки turn счётчик = 0.
- [ ] Несколько открытых вкладок без генерации не блокируют switch.
- [ ] Текст ошибки не ссылается на «planner session is active» как на статус `planning`.
- [ ] Тесты на новое поведение; `ruff check .` и `pytest` зелёные.
- [ ] Run-busy по БД не менять (вне скоупа).
