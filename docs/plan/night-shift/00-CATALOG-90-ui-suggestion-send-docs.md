# CATALOG-90 — Документ удаляется из сессии

- **Задача Plane:** [CATALOG-90](https://app.plane.so/belchch/projects/catalog-app/work-items/90) (id: `49781bcf-8b67-4d64-a7d5-e1995eabc532`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 00 · независимый
- **Цель:** Клик по подсказке и повтор сообщения должны идти через ту же отправку, что и «Отправить»: с `selectedDocIds` / `selectedDocs`. Документы не теряются в новом чате.

## Постановка задачи (актуальное ТЗ)
_(источник: последний комментарий от 2026-08-15T16:03:25Z)_

CATALOG-90, итерация 3. Две предыдущие итерации чинили не тот путь. Живая диагностика на прод-сборке: баг воспроизводится через клик на подсказку («Изучи доступные документы»), а не через кнопку «Отправить».

Кнопки подсказок в `frontend/src/components/Chat.tsx` (блок `visibleSuggestions`) вызывают `onSend(s)` — только текст, без `selectedDocIds` / `selectedDocs`. Обычный `submit` передаёт документы, путь подсказки — нет. Как следствие:

1. WS-кадр `user` уходит без `doc_ids` → backend ничего не привязывает → `session_docs` пустой.
2. Создаётся новая сессия, смена `sessionId` сбрасывает выбранные чипы (`Chat.tsx` эффект на `sessionId`).
3. Планировщик вызывает `list_documents({})`, но в сессии документов нет.

Это ветка А (id не уходят с клиента), участок — suggestion chip, не `Chat.submit`. Гонка HTTP-гидрации ни при чём; защиты `dc8b3b0` не трогать.

Тот же дефект у повтора: `onRepeat={onSend}` в `ChatMessage` тоже теряет документы.

Что сделать:

1. Клик по подсказке ведёт через ту же логику отправки, что `submit`: передавать `selectedDocIds` и `selectedDocs`, затем очищать выбор. Вынести общую функцию отправки.
2. Починить путь повтора (`onRepeat`) тем же способом или явно зафиксировать, что повтор идёт без документов — решение отразить в PR.
3. Тест: выбрано N документов → клик по подсказке → в исходящем кадре есть `doc_ids`, документы появляются в «Документы в сессии» и не пропадают.

Backend-изменения не требуются. `backend/catalog/static/` не в коммите.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

**Описание задачи (итерация 1).** В новом чате первый выбранный документ пропадает из «Документы в сессии» после «Отправить». Гипотеза: гонка `GET /sessions/{id}/documents` (пустой) vs фрейм `session_docs`. Предлагались поколения/флаг, refresh на `finish`, HTTP-attach до WS.

**Комментарий 2026-08-15T11:47:52Z (итерация 2).** Фикс `dc8b3b0` уже в прод-сборке `ed8dc72`. StrictMode не виноват. Защиты гидрации работают. Искать, доходит ли `session_docs` и что в нём. Шаг 1 — диагностика WS/GET на живом приложении. Ветки А/Б/В. Добавить vitest. Не коммитить `backend/catalog/static/`.

## Контекст
`submit` уже передаёт документы:

- `frontend/src/components/Chat.tsx:145-157` — `onSend(text, selectedDocIds, selectedDocs)`, затем чистит выбор.
- `frontend/src/components/Chat.tsx:272` — подсказки: `onClick={() => onSend(s)}` без id.
- `frontend/src/components/Chat.tsx:227` — `onRepeat={onSend}`: повтор шлёт только `content` сообщения (`MessageCommands.tsx:69`).
- `frontend/src/components/Chat.tsx:100-103` — смена `sessionId` обнуляет `selectedDocIds` (чип композера уходит — ожидаемо, если документы уже ушли в сессию).
- `frontend/src/App.tsx` — `handleSend` / `ensureSession` + `planner.send(text, docIds, docs)`.
- `frontend/src/hooks/usePlannerSession.ts` — `send()` мержит composer-документы в `sessionDocuments`; защиты `dc8b3b0` на месте. Не трогать.
- Тестов на `Chat` нет (`frontend/src/components/Chat*.test.*` отсутствуют). Есть `usePlannerSession.test.ts` — его сценарии гидрации не закрывают suggestion-путь.

Парный code-план из first-shift (`00-CATALOG-90-code-session-docs-attach.md`) закрыт предыдущим прогоном; backend по актуальному ТЗ не меняем.

## Затрагиваемые файлы
- `frontend/src/components/Chat.tsx` — общая функция отправки; подсказки вызывают её; решить `onRepeat`.
- `frontend/src/components/Chat.test.tsx` (новый) — клик по подсказке с выбранными документами вызывает `onSend` с `docIds`/`docs`.
- `frontend/src/components/ChatMessage.tsx` / `MessageCommands.tsx` — только если меняется контракт `onRepeat`.
- `frontend/src/App.tsx` — только если `handleSend` нужно явно принять повтор без документов.

## План действий
1. Вынести из `submit` общую `sendCurrent(text)`: читает `selectedDocIds`/`selectedDocs` до очистки, зовёт `onSend`, чистит input и выбор.
2. `submit` и клик по chip в `visibleSuggestions` вызывают `sendCurrent`. Для подсказки текст = текст chip, input можно не подставлять.
3. Повтор: либо `onRepeat` тоже идёт через `sendCurrent` (тогда повтор привяжет текущий выбор композера — обычно пустой), либо оставить повтор без документов и написать это в PR. Не тащить старые `doc_ids` из истории сообщения — их там нет.
4. Тест: мок `onSend`, выбрать документы в combobox / через state, клик «Изучи доступные документы» → `onSend` получил text + id + docs; повторный клик после очистки — без id.
5. Не трогать `usePlannerSession` гидрацию и `dc8b3b0`. Не коммитить `backend/catalog/static/`.
6. Проверки: `pnpm run build`, `lint`, `typecheck`, `test` из `frontend/`.

## Критерии приёмки (Definition of Done)
- [ ] Новый чат → выбрать документы → клик на подсказку: кадр `user` / вызов `onSend` содержит `doc_ids`.
- [ ] Документы сразу видны в «Документы в сессии» и остаются после ответа планировщика.
- [ ] Обычная отправка через «Отправить» не сломана.
- [ ] Решение по `onRepeat` зафиксировано в PR (починен тем же путём или явно без документов).
- [ ] Автотест: падает до фикса, проходит после.
- [ ] Зелёные: `pnpm run build`, `lint`, `typecheck`, `test` из `frontend/`.
- [ ] Проверка на production-сборке (git sha в шапке).
- [ ] `backend/catalog/static/` не в коммите.
- [ ] Защиты `dc8b3b0` не удалены.
