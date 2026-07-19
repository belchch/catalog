# CATALOG-42 — Изоляция документов агента (backend)

- **Задача Plane:** [CATALOG-42](https://app.plane.so/belchch/projects/catalog-app/work-items/42) (id: `d8ee5f75-0aa3-4d20-8d38-dba99249bcb0`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Сделать сессию planner-агента изолированным workspace: tools `list_documents`/`read_document` видят только документы, привязанные к текущей сессии (`session_document`); появляются API для detach и автодобавления результатов skills/runs в сессию.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — комментариев нет)_

Сделать сессию агента изолированным workspace. Агент должен видеть и читать только документы, явно добавленные пользователем в текущую chat-сессию, а также документы, созданные агентом внутри этой сессии. Глобальное хранилище документов остаётся доступно пользователю через UI, но недоступно агенту напрямую.

Полный текст требований (из Tile): изоляция tools (`list_documents`/`read_document` scoped по `session_id`, ошибка `document_not_available_in_session`, передача `session_id` через runtime-контекст), управление составом (attach/detach, восстановление при переоткрытии), автодобавление созданных документов в сессию, обновлённый system prompt с сообщением об ограничении. Полные критерии приёмки — в конце плана.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

### Что уже есть

- **Таблица `session_document`** (`backend/app/storage/schema.py:24-31`) хранит связи `(session_id, document_id, attached_at)` с уникальным PK. Миграций не требует.
- **`attach_documents` + `list_session_documents`** (`backend/app/storage/repo_session_document.py:13-51`) — attach с проверкой существования документа и `INSERT OR IGNORE` (идемпотентный), list с JOIN по `document` и сортировкой по `attached_at`.
- **API сессий** (`backend/app/api/sessions.py`):
  - `GET /sessions/{id}/documents` (стр. 224-234) — отдаёт текущий состав сессии; фронт (`usePlannerSession.ts:224-230`) уже его использует для инициализации.
  - При отправке сообщения с `doc_ids` (стр. 374-377) attach идёт автоматически и шлётся кадр `session_docs`.
- **System prompt** (`_planner_system_prompt`, `sessions.py:113-120`) уже перечисляет привязанные документы (`{doc.id}: {doc.title}`).
- **`build_document_tools`** (`backend/app/documents/tools.py:14-56`) — registry с `list_documents`/`read_document`, замыкается на `(db, workspace_dir)`. **Сейчас работает глобально** — это и есть leaks.
- **Создание результатов**: `apply_skill(persist=True)` (`backend/app/skills/apply.py:296-315`) и `POST /runs/{id}/save` (`backend/app/api/runs.py:118-126`) создают `Document(kind="result_md")`, но **не attach'ат к сессии** — UI их не видит, и после изоляции tools они вообще пропадут из видимости агента.

### Что сломано / отсутствует

1. **Tools не scoped.** `tools.py:_list_documents` (стр. 22-27) вызывает `list_documents(db)` — глобальный список; `tools.py:_read_document` (стр. 29-34) — `get_document(db, doc_id)` без проверки session. Любая сессия может читать любой документ по `doc_id`.
2. **`ToolRegistry` не знает `session_id`.** Передаётся в `_run_planner_turn` (`sessions.py:248-258`), но не в tools. Нужно прокинуть через замыкание при сборке registry на каждое WS-соединение, либо сделать per-request.
3. **Нет `detach_documents`.** Удалить документ из сессии нельзя — только удалить сессию целиком.
4. **Созданные документы не attach'атся автоматически.** В `apply_skill` и `save_run_result_endpoint` нет вызова `attach_documents(...)` — нужны оба места, причём `apply_skill` должен знать свой `session_id` (он уже принимает `session_id` параметром — проверить сигнатуру).
5. **System prompt не сообщает об изоляции.** Базовый `PLANNER_SYSTEM_PROMPT` (`sessions.py:49-61`) не упоминает, что tools ограничены сессией.

### Архитектурное решение

`session_id` — это **trusted runtime context**, а не аргумент модели. Значит, tools должны получить `session_id` через замыкание при сборке registry, а не как параметр tool-call. Текущая архитектура `websocket.app.state.tools` собирает registry один раз — **нужно переделать на per-session сборку**: либо собирать registry в `session_ws` для каждого подключения, либо обернуть tools в объект с состоянием. Первый вариант проще и достаточно — registry лёгкий.

### Парный UI-план

Эта задача — комбинированная (backend + UI). Парный план: `docs/plan/night-shift/CATALOG-42-ui-session-docs-controls.md` (тип `ui`) — добавление кнопки удаления документа из сессии, отображение автодобавленных результатов, индикация scoped-режима. **Этот `code`-план — предусловие для `ui`-плана**: UI-часть зависит от API detach и от кадра `session_docs` при автодобавлении.

## Затрагиваемые файлы

- `backend/app/documents/tools.py` — `build_document_tools(db, workspace_dir, session_id)` (новая сигнатура); `_list_documents` и `_read_document` фильтруются по `list_session_documents` и `session_id`; новая ошибка `document_not_available_in_session`.
- `backend/app/api/sessions.py` — per-session сборка registry внутри `session_ws`; добавление `DELETE /sessions/{id}/documents/{doc_id}`; шлать `session_docs` после detach; обновить `PLANNER_SYSTEM_PROMPT` (сообщение об изоляции).
- `backend/app/storage/repo_session_document.py` — `detach_documents(db, session_id, doc_ids)` (`DELETE FROM session_document WHERE session_id=? AND document_id IN (...)`).
- `backend/app/skills/apply.py` — в ветке `persist=True` (`apply.py:296-315`) после `create_document(...)` вызвать `attach_documents(db, session_id, [out_id])`, если передан `session_id`. Затем прокинуть сигнал для UI (см. ниже — через WS-канал planner-сессии, либо оставить на отдельный polling-механизм, если WS недоступен из apply).
- `backend/app/api/runs.py` — в `save_run_result_endpoint` (`runs.py:118-126`) — аналогично attach к сессии run'а (`run["session_id"]`, если есть).
- `backend/app/api/deps.py` — если `tools` сейчас глобальный dep — заменить или добавить фабрику per-session.
- `backend/tests/test_storage.py` — `detach_documents` + проверка идемпотентности.
- `backend/tests/test_api.py` — `DELETE /sessions/{id}/documents/{doc_id}`; проверка, что после detach документ пропадает из `list_session_documents`.
- `backend/tests/test_agent.py` / новый `test_session_isolation.py` — главный сценарий: две сессии, attach документа в одну, agents tools одной не видят документ другой; попытка `read_document(doc_id)` с чужой сессии → `document_not_available_in_session`.
- `backend/tests/test_apply.py` — автодобавление результата в сессию.

## План действий

1. **Добавить `detach_documents`** в `repo_session_document.py`: сигнатура `detach_documents(db, session_id, doc_ids: list[str]) -> int` (возвращает число удалённых строк). Идемпотентный — отсутствие строки не ошибка. Юнит-тест в `test_storage.py`.
2. **Скоупить tools по `session_id`**:
   - Изменить сигнатуру `build_document_tools(db, workspace_dir, session_id)`.
   - `_list_documents` — `reconcile_orphans` + `list_session_documents(db, session_id)` вместо `list_documents(db)`.
   - `_read_document(doc_id)` — сначала `list_session_documents(db, session_id)`, если `doc_id` не в списке → `return {"error": "document_not_available_in_session"}`. Иначе `extract_text` как сейчас.
   - Описание tool'ов обновить: «scope: only documents attached to the current session».
3. **Per-session сборка registry в `session_ws`** (`sessions.py:341-356`):
   - Вместо `websocket.app.state.tools` вызывать `build_document_tools(db, workspace, session_id)` в начале handler'а после проверки `get_session`.
   - Удалить или оставить глобальный `app.state.tools` — на усмотрение исполнителя (если не используется иначе, убрать, чтобы не плодить мёртвый код).
   - `deps.py` при необходимости — убрать глобальную dep-функцию `get_tools`, заменить на фабрику.
4. **`DELETE /sessions/{id}/documents/{doc_id}`** в `sessions.py`:
   - Проверить существование сессии (404 если нет).
   - `detach_documents(db, session_id, [doc_id])`; если вернул 0 — 404 «document not attached».
   - Вернуть 204. Фронд получит обновлённый состав через повторный `GET /sessions/{id}/documents` либо через WS-кадр `session_docs` (решить в рамках `ui`-плана; в `code` достаточно REST-эндпоинта).
5. **Автодобавление созданных документов**:
   - `apply_skill(persist=True)` (`apply.py:296-315`): после `create_document(...)` — если `session_id is not None`, `attach_documents(db, session_id, [out_id])`. Проверить сигнатуру `apply_skill` — `session_id` уже передаётся (`apply.py` использует его в `finish_run`, см. `runs.py:127` паттерн).
   - `save_run_result_endpoint` (`runs.py:118-126`): после `create_document(...)` — `attach_documents(db, run["session_id"], [out_id])`, если `run["session_id"]` не None.
6. **Обновить system prompt** (`PLANNER_SYSTEM_PROMPT` в `sessions.py:49-61`): добавить фразу вида «Тебе доступны только документы, явно добавленные пользователем в эту сессию. Если нужного документа нет в `list_documents`, попроси пользователя добавить его — глобальное хранилище тебе недоступно.»
7. **Тесты изоляции** (новый `test_session_isolation.py` или расширение `test_agent.py`):
   - Создать две сессии, attach документ только в одну.
   - Из tools первой сессии `list_documents` видит 1 документ, из второй — 0.
   - Из второй попытка `read_document(doc_id)` документa первой → `document_not_available_in_session`.
   - Detach из первой → tools перестают видеть.
   - `apply_skill(persist=True)` в сессии → результат появляется в `list_session_documents(db, session_id)`.

## Критерии приёмки (Definition of Done)

- [ ] `build_document_tools(db, workspace, session_id)` — инструменты знают `session_id` через замыкание, не через параметры tool-call.
- [ ] `list_documents` tool возвращает только документы текущей сессии (`session_document`).
- [ ] `read_document(doc_id)` для непривязанного документа возвращает `{"error": "document_not_available_in_session"}`.
- [ ] Знание корректного `doc_id` чужого документа **не** даёт доступ — изоляция проверена тестом с двумя сессиями.
- [ ] `DELETE /sessions/{id}/documents/{doc_id}` удаляет связь; документ в глобальном хранилище остаётся.
- [ ] `detach_documents` идемпотентен — повторный вызов не падает.
- [ ] `apply_skill(persist=True)` и `POST /runs/{id}/save` автоматически attach'ят созданный документ к сессии run'а, если `session_id` задан.
- [ ] `PLANNER_SYSTEM_PROMPT` явно говорит об ограничении доступа и предлагает пользователю добавить документ, если нужного нет.
- [ ] `GET /sessions/{id}/documents` по-прежнему работает и не меняет контракт.
- [ ] Глобальный список документов в UI продолжает работать (это `GET /documents`, не меняется).
- [ ] Переоткрытие сессии восстанавливает её состав (т.к. данные в БД) — проверить тестом или вручную.
- [ ] `backend/`: `ruff check .` зелёный.
- [ ] `backend/`: `pytest` зелёный, включая новые тесты изоляции и detach.
- [ ] Парный `ui`-план выполним на основе этого API.
