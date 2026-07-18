# CATALOG-2 — История сессий (UI)

- **Задача Plane:** [CATALOG-2](https://app.plane.so/belchch/projects/catalog-app/work-items/2) (id: `6d72b6dd-cc19-4cc9-a374-8c072b4cf403`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Предпосылки:** `CATALOG-2-code-session-history-api.md` (list/get/delete API готовы)
- **Цель:** UI истории сессий: список прошлых чатов, открытие с гидрацией ленты, удаление сессии. После refresh пользователь может вернуться к диалогу.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Сейчас сессии чата теряются после закрытия или обновления. Нужно хранить и визуализировать историю, чтобы пользователь мог вернуться. Также нужна функция удаления сессии, чтобы пользователь мог удалять мусор или нерелевантные сессии.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- `App.tsx:28` — `sessionId` только в `useState`, не в URL/localStorage; после F5 — новая сессия.
- `usePlannerSession.ts` — WS + in-memory messages; при смене id чистит state, **не** подгружает историю из API.
- `api.ts` — `createSession` / `buildSkill` / `startEditSession`; нет list/get/delete sessions.
- `Chat.tsx` — только текущая лента.
- Backend API для этого UI — в `CATALOG-2-code-session-history-api.md`.

## Затрагиваемые файлы

- `frontend/src/api.ts` — типы `SessionOut`, `listSessions`, `listSessionMessages`, `deleteSession`.
- `frontend/src/hooks/usePlannerSession.ts` — hydrate messages при выборе сессии (до/вместо пустого WS start).
- `frontend/src/components/` — новый компонент списка истории (сайдбар/панель), кнопка удаления.
- `frontend/src/App.tsx` — wire: выбор сессии → setSessionId + hydrate; «Новая сессия»; удаление.
- Стили существующего layout (без карточного dashboard-шума; одна панель списка).

## План действий

1. Добавить клиентские вызовы к API из code-плана.
2. Компонент списка сессий: превью (title/дата/status), клик открывает сессию, кнопка удалить с подтверждением.
3. Гидрация: при выборе id загрузить messages в state хука; затем при необходимости reconnect WS для продолжения planning-сессии.
4. В `App`: кнопка «Новый чат» (сброс sessionId / create), сохранение текущего id опционально в localStorage для restore после refresh.
5. Ручная проверка: диалог → F5 → сессия в списке → открыть → лента на месте; удалить → исчезла из списка.

## Критерии приёмки (Definition of Done)

- [ ] В UI виден список прошлых сессий с превью.
- [ ] Клик по сессии восстанавливает ленту сообщений.
- [ ] Удаление сессии убирает её из списка и с сервера.
- [ ] После обновления страницы история доступна (не «с нуля» без возможности вернуться).
- [ ] `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` в `frontend/` зелёные.
