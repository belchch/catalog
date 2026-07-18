# CATALOG-11 — Отмена обработки сообщения в чате

- **Задача Plane:** [CATALOG-11](https://app.plane.so/belchch/projects/catalog-app/work-items/11) (id: `5956b93b-4910-43a8-9f51-c03731e07f7d`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Предпосылки:** нет
- **Цель:** Дать пользователю **отменить** идущую обработку сообщения в чате: на месте кнопки «Отправить» во время обработки показывается **кнопка «Стоп»**; отмена стандартно прокидывается через весь стек вызовов до LLM-вызова (asyncio task cancellation → `CancelledError`), агент-луп корректно прерывается, стрим завершается кадром `cancelled`, сессия остаётся живой для следующего сообщения. Применить тот же механизм к apply-стриму (`/runs/{id}/stream`), где run помечается `cancelled`.

## Контекст

Сейчас **отмены нет**, а архитектура стримов этому препятствует — WS-обработчик блокирован внутри агент-лупа и не может прочитать кадр отмены:

- **Планировщик (чат):** `session_ws` (`backend/app/api/sessions.py:68-145`) — `while True: raw = await websocket.receive_text()` (блокирует до сообщения), затем `async for event in run_agent(...)` (`sessions.py:98-121`) стримит события. **Пока идёт `run_agent`, обработчик не вызывает `receive_text()`** → кадр отмены от клиента физически не может быть прочитан. `run_agent` (`backend/app/agent/runner.py:176-200`) → `_run_agent_core` (`runner.py:74-173`) крутит итерации, внутри `await provider.complete(...)` (`runner.py:120`) — блокирующий LLM-вызов httpx. Никакого токена отмены/`CancelledError` не проверяется.
- **Apply (применение скила):** `run_stream_ws` (`backend/app/api/runs.py:67-139`) — тот же паттерн: `async for event in apply_skill(...)` (`runs.py:107-119`) блокирует обработчик; `apply_skill` → `_apply_core` (`apply.py:59-115`) → `_run_agent_core`. Есть `try/except/finally` (`apply.py:232-...`) с `finish_run` (гарантия, что `skill_run` не останется `running`), но `CancelledError` там не выделен → отменённый run пометится `failed`, а не `cancelled`.
- **Фронтенд:** `Chat.tsx:56-74` — инпут + кнопка «Отправить» (`onSend`), `disabled={streaming}`. Во время обработки **кнопки стоп нет**. `usePlannerSession` (`frontend/src/hooks/usePlannerSession.ts:121-133`) шлёт текст через `conn.send(text)`; `connectPlanner` (`frontend/src/ws.ts:50-66`) отдаёт `{send, close}`. Серверный `_parse_user_payload` (`sessions.py:41-51`) принимает plain text или `{"type":"user","content":"..."}` JSON, но **кадра `cancel` нет ни в протоколе, ни в `PlannerConnection`/`ServerEvent`** (`ws.ts:9-31`).

Ключевой вывод: нужно (1) реструктурировать WS-обработчики, чтобы concurrently слушать кадр `cancel` во время агент-лупа; (2) запускать луп как `asyncio.Task` и отменять его стандартным `task.cancel()`; (3) `CancelledError` сам прокидывается «через весь стек» до `provider.complete`/`stream_complete` (httpx) — это и есть «сделать стандартно».

## Затрагиваемые файлы

**Backend — протокол/проброс отмены:**
- `backend/app/api/sessions.py:68-145` — реструктурировать `session_ws`: запускать агент-луп в `asyncio.Task` и параллельно `await websocket.receive_text()` для детекта `{"type":"cancel"}`; по cancel → `task.cancel()`; ловить `CancelledError` → досылать `finish{status:"cancelled"}` (сохранять частичный `final_text`, если есть) и **продолжать `while True`** (сессия жива). Не терять кадры событий, уже отправленные до отмены.
- `backend/app/api/runs.py:67-139` — то же для apply: оборачивать `apply_skill`-стрим в задачу, слушать `cancel`, по cancel → `task.cancel()`; `finish_run(status="cancelled")` (отличать от `failed`). Авторский `finish`-кадр (`runs.py:122-129`) нести `status:"cancelled"`.
- `backend/app/agent/runner.py:74-173` — `_run_agent_core`/`run_agent` корректно пробрасывают `CancelledError` (не глотать); опционально — cooperative-флаг `cancel_event: asyncio.Event` с проверкой на каждой итерации (`runner.py:94`) как страховка, если провайдер перехватывает cancel.
- `backend/app/skills/apply.py:232-...` — в `try/except/finally` различать `CancelledError`: статус `"cancelled"` вместо `"failed"` (trace частично сохранён); гарантия `finish_run` ровно один раз сохраняется.
- `backend/app/llm/base.py:50-65` + `backend/app/llm/openrouter.py` — `complete`/`stream_complete` должны корректно реагировать на отмену задачи (httpx прерывает запрос по `CancelledError`); убедиться, что таймауты/ретраи OpenRouter (`openrouter.py:196-...`) не маскируют cancel.

**Backend — тесты:**
- `backend/tests/test_agent.py` / `backend/tests/test_api.py` — отмена агент-задачи: `task.cancel()` → `CancelledError` поднимается из `run_agent`; WS `/sessions/{id}` получает `finish{status:"cancelled"}` и продолжает принимать сообщения.
- `backend/tests/test_apply.py` — отменённый apply → `skill_run.status=="cancelled"`, не `running`/`failed`.

**Frontend:**
- `frontend/src/ws.ts:28-31,50-66` — добавить в `PlannerConnection` метод `cancel()` (шлёт `JSON.stringify({type:'cancel'})`); то же для `RunConnection`; добавить `cancel` в `ServerEvent`-дискриминатор (`ws.ts:9-26`), если нужно.
- `frontend/src/hooks/usePlannerSession.ts:121-135` — метод `cancel()`, флаг `cancelling`; по `finish{status:"cancelled"}` сбрасывать `streaming`.
- `frontend/src/components/Chat.tsx:56-74` — во время `streaming` рендерить кнопку **«Стоп»** (вместо/рядом с «Отправить»), вызывает `cancel`; инпут блокируется на время отмены.
- `frontend/src/App.tsx` / `frontend/src/hooks/useSkills.ts:38-47` — для apply-стрима аналогичный `cancel` (если apply идёт через WS-стрим в UI).

## План действий

1. **Протокол отмены.** Зафиксировать кадр `{"type":"cancel"}` от клиента; серверный респонс — `finish` с `status:"cancelled"`. Обновить `_parse_user_payload`/обработку, чтобы `cancel`-кадр не записывался как user-сообщение.
2. **Реструктуризация WS planner.** В `session_ws` обернуть `async for event in run_agent(...)` в `asyncio.Task`, параллельно слушать входящие кадры; на `cancel` → `task.cancel()`, дождаться с перехватом `CancelledError`, дослать `finish{status:"cancelled"}`, продолжить цикл. Сохранять уже отправленные события.
3. **Apply-стрим.** В `run_stream_ws` аналогично; в `apply.py` различать `CancelledError` → `finish_run(status="cancelled")`; `finish`-кадр несёт `cancelled`.
4. **Проброс по стеку.** Убедиться, что `run_agent`/`_run_agent_core`/`apply_skill` пробрасывают `CancelledError` (не `except Exception` его глотает); OpenRouter-провайдер прерывает httpx-запрос. Добавить cooperative-флаг проверки в цикле `_run_agent_core` (`runner.py:94`) как страховку.
5. **Frontend ws.ts.** `PlannerConnection.cancel()` / `RunConnection.cancel()` шлют `{"type":"cancel"}`.
6. **Frontend хук.** `usePlannerSession.cancel()` + состояние `cancelling`; реакция на `finish{status:"cancelled"}`.
7. **Frontend UI.** В `Chat` кнопка «Стоп» во время `streaming` (`Chat.tsx:56-74`); для apply — аналогичная остановка.
8. **Тесты.** Backend: cancel задачи поднимает `CancelledError` из `run_agent`; WS шлёт `finish{status:"cancelled"}` и принимает следующее сообщение; apply → `skill_run.status=="cancelled"`. Frontend: typecheck/lint.
9. **Ручная проверка.** Послать сообщение → во время ответа нажать «Стоп» → стрим прекращается, появляется возможность писать снова; применить скил → «Стоп» → run = `cancelled`.

## Критерии приёмки (Definition of Done)

- [ ] Во время обработки сообщения в чате на месте кнопки отправки отображается **кнопка «Стоп»**.
- [ ] Нажатие «Стоп» отменяет идущий агент-запрос: стрим прекращается, приходит `finish{status:"cancelled"}`, пользователь может сразу отправить новое сообщение (сессия жива).
- [ ] Отмена прокидывается **через весь стек** до LLM-вызова стандартным asyncio-механизмом (`task.cancel()` → `CancelledError`); `run_agent`/`apply_skill` не маскируют отмену.
- [ ] Для apply: отменённый run помечается `cancelled` (не `running`/`failed`); `skill_run` не остаётся зависшим.
- [ ] Частично сгенерированный ответ/trace по возможности сохраняются (не теряются молча).
- [ ] `backend`: `pytest backend/tests` зелёные, добавлены кейсы отмены planner + apply.
- [ ] `backend`: `ruff check backend` без ошибок.
- [ ] `frontend`: `npm run typecheck`/`npm run lint` проходят.
