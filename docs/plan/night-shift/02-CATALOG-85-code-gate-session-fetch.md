# CATALOG-85 — GET /sessions/{id} отдаёт 409, если воркспейс не открыт

- **Задача Plane:** [CATALOG-85](https://app.plane.so/belchch/projects/catalog-app/work-items/85) (id: `f0e08c8d-2a41-4519-8d20-4aaef7da39ba`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 02 · независимый
- **Цель:** Не дёргать `GET /sessions/{id}`, пока воркспейс не открыт. Эффект чтения таймаута сессии в `App.tsx` должен гейтиться по `hasWorkspace` так же, как это уже сделано для планировщика. Бэкенд не меняется: 409 — корректный ответ.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи от 2026-08-14 16:40 UTC; комментариев нет)_

**Симптом.** При загрузке UI без открытого воркспейса в консоли браузера и в uvicorn: `GET /sessions/{id} → 409 Conflict` (`workspace not open`). Пример из лога: `GET /sessions/96e19670245044ba8dc2abff8cb7687e` после `GET /workspaces/current → 204`.

**Причина.** `sessionId` восстанавливается из `localStorage` (`catalog.sessionId`) при монте `App`. Эффект таймаута сессии вызывает `getSession(sessionId)` без проверки `hasWorkspace`. Планер уже гейтится: `usePlannerSession(hasWorkspace ? sessionId : null)`. Эффект с `getSession` — нет.

**Где смотреть.**

- `frontend/src/App.tsx` — `readStoredSessionId`, эффект с `getSession` (таймаут сессии)
- `backend/catalog/api/deps.py` — 409 `workspace not open`

**Ожидаемое.** Не вызывать `GET /sessions/{id}`, пока воркспейс не открыт. После открытия папки сессию из localStorage можно подтягивать как сейчас.

## Предыстория
_нет — комментариев к задаче не было._

## Контекст
- `sessionId` инициализируется из localStorage при монте: `frontend/src/App.tsx:102` (`useState(() => readStoredSessionId())`), сам ридер — `App.tsx:52-58`, ключ `catalog.sessionId` — `App.tsx:47`.
- `hasWorkspace` считается из `workspace.current`: `App.tsx:95`. На старте `useWorkspace` грузит `GET /workspaces/current` (`frontend/src/hooks/useWorkspace.ts:54-73`), и до ответа `current === null`, то есть `hasWorkspace === false`.
- Проблемный эффект — `App.tsx:233-254`: при непустом `sessionId` и отсутствии записи в `sessions.sessions` он безусловно вызывает `getSession(sessionId)` (`:244`) для чтения `llm_timeout_seconds`. Проверки `hasWorkspace` нет; ошибка глотается в `.catch` (`:248-250`), поэтому наружу баг виден только как 409 в консоли и в логе uvicorn.
- Как выглядит корректный гейт рядом: `usePlannerSession(hasWorkspace ? sessionId : null, …)` — `App.tsx:136`. Другие хуки тоже получают флаг: `useDocuments(hasWorkspace)` (`:96`), `useSkills(hasWorkspace)` (`:97`), `useSessions(hasWorkspace)` (`:99`).
- Источник 409 на бэкенде — зависимость `get_workspace_db`: `backend/catalog/api/deps.py:41-45` (`manager.current is None` → `HTTPException(409, "workspace not open")`). Это осознанное поведение, менять его не нужно.
- После открытия папки `hasWorkspace` становится `true` и эффект отработает штатно: обработчик `handleWorkspaceOpened` (`App.tsx:172-179`) обновляет `workspace.current` и списки, при смене пути сессия сбрасывается (`App.tsx:152-165`).

## Затрагиваемые файлы
- `frontend/src/App.tsx` — эффект чтения таймаута сессии (`:233-254`): добавить условие на `hasWorkspace` и корректно вести себя при закрытом воркспейсе.

## План действий
1. В эффекте `App.tsx:233-254` добавить ранний выход, когда воркспейса нет: условие становится «нет `sessionId` **или** `!hasWorkspace`» → сбросить `sessionTimeoutSeconds` в `DEFAULT_SESSION_TIMEOUT` (`App.tsx:67`) и выйти, не вызывая `getSession`.
2. Добавить `hasWorkspace` в массив зависимостей эффекта, чтобы после открытия папки таймаут подтянулся без перезагрузки страницы.
3. Проверить, что путь «сессия есть в списке» (`App.tsx:238-242`) по-прежнему выигрывает у HTTP-запроса и не ломается при пустом списке сессий.
4. Ручная проверка: открыть UI без воркспейса при непустом `catalog.sessionId` в localStorage — в Network нет запроса `GET /sessions/{id}`, в логе uvicorn нет 409; затем открыть папку — запрос уходит один раз и таймаут подставляется.
5. Прогнать из `frontend/`: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck`.

## Критерии приёмки (Definition of Done)
- [ ] При загрузке UI без открытого воркспейса и непустом `catalog.sessionId` запрос `GET /sessions/{id}` не отправляется.
- [ ] В логе uvicorn при таком старте нет `409 Conflict` от `/sessions/{id}`.
- [ ] После открытия папки таймаут сессии подтягивается как раньше (значение из `GET /sessions/{id}` или из списка сессий).
- [ ] При закрытом воркспейсе `sessionTimeoutSeconds` равен `DEFAULT_SESSION_TIMEOUT`.
- [ ] Бэкенд не изменён: `deps.py` по-прежнему отдаёт 409 при закрытом воркспейсе.
- [ ] Из `frontend/`: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` зелёные.
