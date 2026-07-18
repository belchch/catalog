# CATALOG-28 — Документы в контексте чата (UI)

- **Задача Plane:** [CATALOG-28](https://app.plane.so/belchch/projects/catalog-app/work-items/28) (id: `bc1816bc-2837-426d-85fc-9cb70fe241bc`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Предпосылки:** `CATALOG-28-code-session-documents.md`
- **Цель:** Пикер/чипы документов в composer; блок «Документы в сессии»; передача `doc_ids` по WS; синхронизация от сервера.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Пользователь указывает документы для работы в чате → они детерминированно привязываются и отображаются как состав сессии. Минимум: кнопка «+ документ» → выбор → чипы над полем ввода. Не смешивать с `currentDocId` (apply).

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- `Chat.tsx` / `usePlannerSession.send` — только текст.
- `App.tsx` `currentDocId` — для apply, не для planner.
- Backend контракт — в code-плане.

## Затрагиваемые файлы

- `frontend/src/api.ts` — `getSessionDocuments`.
- `frontend/src/ws.ts` / `usePlannerSession.ts` — `send(text, docIds?)`, обработка `session_docs`.
- `frontend/src/components/Chat.tsx` — пикер + чипы composer + блок состава сессии.
- `frontend/src/App.tsx` — проброс документов списка в Chat.

## План действий

1. Расширить send/WS типы.
2. Composer: «+ документ», чипы выбранных, submit с `doc_ids`, очистка выбора.
3. Блок «Документы в сессии» из серверного состояния.
4. Reload: `GET /sessions/{id}/documents` при наличии sessionId (если session ещё жива).

## Критерии приёмки (Definition of Done)

- [ ] Выбор доков в composer → после отправки видны в составе сессии.
- [ ] UI обновляется от серверного списка (не только локальный state).
- [ ] Не путается с `currentDocId` apply.
- [ ] `pnpm run build/lint/typecheck` зелёные.
