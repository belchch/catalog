# CATALOG-90 — Документ удаляется из сессии

- **Задача Plane:** [CATALOG-90](https://app.plane.so/belchch/projects/catalog-app/work-items/90) (id: `49781bcf-8b67-4d64-a7d5-e1995eabc532`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 01 · предусловие: 00 (code того же тикета)
- **Цель:** На живой прод-сборке зафиксировать, куда пропадает документ при первом сообщении нового чата, исправить выбранную ветку на клиенте и сделать список «Документы в сессии» оптимистичным. Добавить vitest и тест на `usePlannerSession`, чтобы фикс был проверяемым.

## Постановка задачи (актуальное ТЗ)
_(источник: последний комментарий от 2026-08-15)_

CATALOG-90, итерация 2. Фикс `dc8b3b0` уже в сборке `ed8dc72` (uv tool install из `pipeline/night-shift-3` = main). Воспроизведение на **production-сборке**: StrictMode эффекты не дублирует. Защиты `docsFromStreamRef` / `docsHydrateGenRef` / `skipHydrateRef` при одном проходе отбрасывают поздний пустой GET корректно. Причина, скорее всего, **не** в гонке HTTP-гидрации.

**Шаг 1 (блокирующий).** DevTools на прод-сборке, сценарий «Новый чат» → «+ документ» → текст → «Отправить». Зафиксировать: (1) исходящий WS `{"type":"user","content":"...","doc_ids":["<id>"]}`; (2) пришёл ли `session_docs`; (3) не пустой ли он; (4) сколько раз ушёл `GET /sessions/{id}/documents` и когда относительно фрейма. Плюс ручной GET после бага — документ в БД или нет. Скриншоты — обязательная часть PR.

**Шаг 2.** По фактам: ветка А — чинить путь отправки (`Chat.submit` → `pendingRef` не теряет `docIds`); ветка Б — консистентность id (backend, парный code-план); ветка В — `ensureSession` прокидывает `doc_ids` в `POST /sessions`. Независимо от ветки: `send()` сразу мержит выбранные документы в `sessionDocuments` (полные `DocumentOut` из composer). Защиты `dc8b3b0` не удалять.

**Шаг 3.** Добавить `vitest` + `jsdom` + `@testing-library/react`, скрипт `"test": "vitest run"`. Тест `usePlannerSession`: `session_docs` затем пустой GET; обратный порядок; переключение сессий гидрирует HTTP. `pnpm run test` в pipeline-checks — в code-плане.

Финальную проверку — на production-сборке. Не ссылаться на StrictMode. Не добавлять новых флагов без факта шага 1. Не коммитить `backend/catalog/static/`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

Исходное описание: в новом чате (сессии ещё нет) выбранный документ после «Отправить» исчезает из композера и не появляется в «Документы в сессии». На втором сообщении уже существующей сессии баг не воспроизводится. Гипотеза 1-й итерации — гонка `GET .../documents` (пусто) vs фрейм `session_docs`, усугублённая StrictMode; для сообщений есть `skipHydrateRef`, для документов — не было. Предлагались поколения/флаг, refresh на `finish`, либо HTTP-attach до WS.

## Контекст
Парный code-план (предусловие): `docs/plan/first-shift/00-CATALOG-90-code-session-docs-attach.md`. UI не стартует ветку В, пока `POST /sessions` не принимает `doc_ids`.

Текущий клиентский путь:

- `frontend/src/components/Chat.tsx:84-91` — `submit` передаёт `selectedDocIds`, затем сразу чистит их. Объекты документов есть в `selectedDocs` (`Chat.tsx:101-103`).
- `frontend/src/App.tsx:297-315` — `ensureSession` создаёт сессию без `doc_ids`, затем `planner.send(text, docIds)`.
- `frontend/src/hooks/usePlannerSession.ts:343-358` — `send()` ставит `skipHydrateRef`, кладёт сообщение в ленту, шлёт сразу или в `pendingRef`. **Оптимистичного merge в `sessionDocuments` нет.**
- Тот же хук, эффект `:236-341`: при смене `sessionId` гидрирует документы через `getSessionDocuments`; отбрасывает ответ, если `docsFromStreamRef` / поколение / `skipHydrateRef` / pending. `session_docs` (`:208-212`) пишет список целиком. `finish` (`:185-203`) переспрашивает GET.
- `frontend/src/ws.ts:88-94` — кадр с `doc_ids`, если массив непустой.
- `frontend/src/components/Chat.tsx:163-188` — блок «Документы в сессии» рендерится только при `sessionDocuments.length > 0`.
- `frontend/package.json:6-12` — скриптов `test` нет, vitest не подключён.

`Chat.tsx:73-75` сбрасывает `selectedDocIds` при смене `sessionId` — это ожидаемо (чип композера уходит), но без оптимистичного/серверного списка блок сессии остаётся пустым.

## Затрагиваемые файлы
- `frontend/src/hooks/usePlannerSession.ts` — оптимистичный merge выбранных документов в `send()`; при ветке А — сохранить `docIds` в `pendingRef` при `sessionId: null → id`; не удалять защиты `dc8b3b0`.
- `frontend/src/components/Chat.tsx` — прокинуть полные `DocumentOut` в `onSend` (или отдельный аргумент), чтобы `send()` мог смержить чипы в «Документы в сессии» сразу.
- `frontend/src/App.tsx` — `handleSend` / `ensureSession`: при ветке В передать `doc_ids` в create; прокинуть документы в `planner.send`.
- `frontend/src/api.ts` — `createSession(docIds?)` шлёт JSON body (ветка В).
- `frontend/src/ws.ts` — только если факт 1 покажет, что кадр собирается неверно.
- `frontend/package.json` — `vitest`, `jsdom`, `@testing-library/react`, скрипт `test`.
- `frontend/vite.config.ts` / новый `frontend/vitest.config.ts` — окружение jsdom.
- `frontend/src/hooks/usePlannerSession.test.ts` (новый) — три сценария порядка промисов из ТЗ.

## План действий
1. **Шаг 1 на прод-сборке** (`pnpm run build` или установленный tool). Network → WS + XHR. Сценарий из ТЗ. Записать четыре факта и ручной GET. Скриншоты в PR. Без этого правки не принимать.
2. Выбрать ветку А/Б/В. Ветку Б закрывает code-план; здесь только клиентский отчёт и оптимистичный UI.
3. **Оптимистичный список (всегда):** расширить `send` так, чтобы вместе с `docIds` приходили объекты `DocumentOut` из composer; сразу мержить их в `sessionDocuments` по id. Поздний авторитетный список (`session_docs`, finish-GET, гидрация при смене сессии) **заменяет** целиком. Ручное удаление (`removeDocument`, `:375+`) по-прежнему бампает поколение и не откатывается.
4. **Ветка А:** проверить, что `Chat.submit` читает `selectedDocIds` до `setSelectedDocIds([])`, и что `pendingRef` в `onOpen` (`:320-324`) шлёт те же `docIds`. Если `handleSend` вызывает `send` до того, как эффект нового `sessionId` создал соединение — это штатный pending-путь, id не должны теряться.
5. **Ветка В:** `createSession` / `ensureSession` передают выбранные id; к старту эффекта документы уже в БД. Не плодить новые флаги.
6. Подключить vitest + jsdom + testing-library. Тест хука с моками `getSessionDocuments` и WS: (а) `session_docs` с документом → пустой GET → документ остаётся; (б) обратный порядок; (в) смена `sessionId` — HTTP-гидрация применяется. Тест должен падать на коде без оптимистичного merge / без защит и проходить после.
7. Ручная приёмка на **production-сборке**, git sha в шапке UI. Dev (`pnpm run dev` + uvicorn `--reload`) — только для итерации.

## Критерии приёмки (Definition of Done)
- [ ] В PR отчёт шага 1: все четыре факта + скриншоты WS Messages и GET.
- [ ] Явно указана ветка А/Б/В и почему.
- [ ] Новый чат → документ → первое сообщение: документ сразу в «Документы в сессии» и остаётся после хода.
- [ ] Второе сообщение с документами в той же сессии не ломает список.
- [ ] F5 в середине и после хода даёт тот же список, что UI.
- [ ] Переключение сессий по-прежнему гидрирует список из HTTP.
- [ ] Ручное удаление документа из сессии не откатывается поздней гидрацией.
- [ ] Есть автотест, падающий до фикса и проходящий после.
- [ ] Зелёные: `pnpm run build`, `lint`, `typecheck`, `test` из `frontend/`.
- [ ] Проверка на production-сборке, версия подтверждена (git sha в шапке).
- [ ] Защиты `dc8b3b0` на месте; новых флагов без факта шага 1 нет.
- [ ] `backend/catalog/static/` не в коммите.
