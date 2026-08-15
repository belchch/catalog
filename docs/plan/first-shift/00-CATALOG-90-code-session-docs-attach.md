# CATALOG-90 — Документ удаляется из сессии

- **Задача Plane:** [CATALOG-90](https://app.plane.so/belchch/projects/catalog-app/work-items/90) (id: `49781bcf-8b67-4d64-a7d5-e1995eabc532`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 00 · независимый
- **Цель:** Сделать привязку документов к сессии наблюдаемой и, при выборе ветки В, атомарной: `attach_documents` сообщает о пропущенных id, `POST /sessions` умеет принять `doc_ids` и привязать их до ответа. Покрыть выбранную ветку backend-тестом.

## Постановка задачи (актуальное ТЗ)
_(источник: последний комментарий от 2026-08-15)_

CATALOG-90, итерация 2. Предыдущий фикс (`dc8b3b0`) уже в прод-сборке (`ed8dc72`); гонка HTTP-гидрации и StrictMode как причина сняты. Искать, доходит ли фрейм `session_docs` и что в нём.

Backend-часть шага 2 — по результату диагностики (шаг 1 живёт в парном UI-плане):

- **Ветка Б** — `session_docs` пришёл с `"documents": []`: чинить консистентность id между `GET /documents` и workspace-БД сессии. `attach_documents` не должен молчать: при непривязанных id backend обязан вернуть кадр `error` или явно сообщить о пропущенных id.
- **Ветка В** — `session_docs` пришёл с документом, но UI обнулился: `POST /sessions` принимает опциональное `{"doc_ids": [...]}` и привязывает документы **до** возврата ответа, чтобы первый `GET /sessions/{id}/documents` уже видел их.

Шаг 3: backend-тест на выбранную ветку в `backend/tests/test_api.py`. Добавить `pnpm run test` в `.cursor/rules/catalog-pipeline-checks.mdc`.

Не коммитить `backend/catalog/static/`. Не закрывать без живой диагностики (отчёт — в UI-плане / PR).

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

Исходное описание задачи (без комментариев): баг «в новом чате первый выбранный документ пропадает из „Документы в сессии“». Гипотеза первой итерации — гонка: `GET /sessions/{id}/documents` для пустой сессии приходит после WS-фрейма `session_docs` и затирает список. Предлагались флаги/поколения, `refreshSessionDocuments` на `finish`, либо `attach` по HTTP до WS. Критерии первой итерации: документ остаётся в блоке, повторная отправка не ломает список, F5 совпадает с UI, тест на гонку пустой GET после `session_docs`.

## Контекст
Парный UI-план: `docs/plan/first-shift/01-CATALOG-90-ui-session-docs-disappear.md`. Этот `code`-план — предусловие для UI (особенно ветка В и наблюдаемость `attach`).

Сейчас `POST /sessions` тела не принимает и только создаёт пустую сессию:

- `backend/catalog/api/sessions.py:229-231` — `create_session_endpoint` без body.
- `backend/catalog/api/schemas.py:130-131` — `SessionCreated` только с `id`.
- `frontend/src/api.ts:300-302` — `createSession()` шлёт пустой POST (клиент меняется в UI-плане).

Привязка идёт позже, по первому WS-кадру пользователя:

- `backend/catalog/api/sessions.py:708-711` — `_parse_user_payload` → `attach_documents` → `_session_docs_frame`.
- `backend/catalog/storage/repo_session_document.py:13-29` — несуществующие id **молча пропускаются** (`continue`). Это подтверждено тестом `backend/tests/test_storage.py:122-133`.

Если диагностика (шаг 1 UI-плана) покажет ветку Б, молчаливый skip — дефект: UI получает пустой `session_docs` и не знает, что id не нашлись. Если ветку В — гонку убираем тем, что документы уже в БД к моменту старта эффекта гидрации.

Защиты `dc8b3b0` (`docsFromStreamRef`, `docsHydrateGenRef`, `skipHydrateRef`) не трогать с backend-стороны.

## Затрагиваемые файлы
- `backend/catalog/storage/repo_session_document.py` — `attach_documents` возвращает пропущенные / непривязанные id (не `None`).
- `backend/catalog/api/sessions.py` — WS: кадр `error` (или явное поле skipped) при пропуске id; при ветке В — body `doc_ids` на `POST /sessions` и attach до ответа.
- `backend/catalog/api/schemas.py` — схема create-session request с опциональным `doc_ids` (ветка В).
- `backend/tests/test_storage.py` — обновить `test_attach_documents_idempotent` под новый контракт возврата.
- `backend/tests/test_api.py` — тест выбранной ветки (пустой attach → error **или** POST с `doc_ids` → GET documents непустой).
- `.cursor/rules/catalog-pipeline-checks.mdc` — добавить `pnpm run test` в список frontend-проверок.

## План действий
1. Дождаться четырёх фактов шага 1 из UI-плана (исходящий `user`/`doc_ids`, факт `session_docs`, содержимое, порядок GET). Без них не выбирать ветку.
2. Изменить `attach_documents`: вернуть список id, которые не нашлись в `document` (и при необходимости — которые не вставились). Существующая идемпотентность `INSERT OR IGNORE` для уже привязанных id сохраняется — это не «пропуск».
3. Ветка Б (если `session_docs.documents == []` при ненулевых `doc_ids`): после `attach_documents` в WS-цикле (`sessions.py:708-711`) отправить кадр `error` (или расширить `session_docs` полем skipped). Не глотать расхождение id.
4. Ветка В (если фрейм с документом есть, но UI обнуляется): добавить опциональный JSON-body `{"doc_ids": [...]}` в `POST /sessions`, вызвать `attach_documents` **до** `return SessionCreated`. Несуществующие id — тот же контракт, что в п. 2–3 (4xx или список skipped в ответе — выбрать один и зафиксировать в тесте).
5. Если диагностика укажет ветку А (id не уходят с клиента) — backend не менять, кроме п. 2 как страховки наблюдаемости. Это допустимо: тогда этот план закрывается минимальным контрактом `attach_documents` + тестом на skipped.
6. Тесты: storage — skipped id возвращаются, существующие по-прежнему привязываются; API — выбранная ветка. Не коммитить `backend/catalog/static/`.
7. В `catalog-pipeline-checks.mdc` добавить `pnpm run test` рядом с `build` / `lint` / `typecheck`.

## Критерии приёмки (Definition of Done)
- [ ] В PR / отчёте указана выбранная ветка (А/Б/В) и почему; backend-изменения соответствуют только ей (+ наблюдаемый attach).
- [ ] `attach_documents` больше не молчит о неизвестных id: вызывающий код может отличить «привязано» от «пропущено».
- [ ] Если выбрана ветка Б: непривязанные id дают кадр `error` или явное поле в `session_docs`; тест в `test_api.py` это фиксирует.
- [ ] Если выбрана ветка В: `POST /sessions` с `doc_ids` привязывает документы до ответа; `GET /sessions/{id}/documents` сразу их возвращает; тест в `test_api.py`.
- [ ] `test_attach_documents_idempotent` обновлён и зелёный; повторный attach существующих id по-прежнему no-op.
- [ ] `.cursor/rules/catalog-pipeline-checks.mdc` содержит `pnpm run test`.
- [ ] Зелёные: `ruff check .`, `pytest` из `backend/`.
- [ ] `backend/catalog/static/` не в коммите.
