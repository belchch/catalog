# CATALOG-2 — История сессий

- **Задача Plane:** [CATALOG-2](https://app.plane.so/belchch/projects/catalog-app/work-items/2) (id: `6d72b6dd-cc19-4cc9-a374-8c072b4cf403`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Персистентная история сессий на backend: список сессий с превью, получение сообщений, удаление сессии. UI гидрации и сайдбара — в парном плане `CATALOG-2-ui-session-history.md` (выполнять после этого).

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Сейчас сессии чата теряются после закрытия или обновления. Нужно хранить и визуализировать историю, чтобы пользователь мог вернуться. Также нужна функция удаления сессии, чтобы пользователь мог удалять мусор или нерелевантные сессии.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

Сообщения уже пишутся в SQLite при работе planner WS, но HTTP API для истории отсутствует.

- Таблица: `session` (`id, status, created_at, skill_id`), `message` — `backend/app/storage/schema.py:18-27`. Нет `title`/`updated_at`.
- Repo: `create_session` / `get_session` / `update_session_status` — `backend/app/storage/repo_session.py:40-72`. **Нет** `list_sessions` / `delete_session`.
- Сообщения: `list_messages` — `backend/app/storage/repo_message.py:38`.
- API: `POST /sessions`, `WS /sessions/{id}` — `backend/app/api/sessions.py`. На connect история клиенту не отдаётся.
- Схемы: `SessionCreated { id }` — `backend/app/api/schemas.py`.
- Парный UI-план: `CATALOG-2-ui-session-history.md` (зависит от этого code-плана).

## Затрагиваемые файлы

- `backend/app/storage/schema.py` — при необходимости `updated_at` / `title` на `session` + additive migration.
- `backend/app/storage/repo_session.py` — `list_sessions`, `delete_session` (cascade messages), опционально обновление `updated_at`/`title`.
- `backend/app/storage/repo_message.py` — при delete: удаление сообщений сессии (или FK CASCADE).
- `backend/app/api/schemas.py` — `SessionOut` (id, status, created_at, updated_at?, title/preview?, skill_id?), список сообщений.
- `backend/app/api/sessions.py` — `GET /sessions`, `GET /sessions/{id}` (или `/messages`), `DELETE /sessions/{id}`; при WS connect — отдать историю или оставить hydrate на HTTP.
- `backend/tests/` — тесты list/get/delete и изоляции сообщений.

## План действий

1. Решить минимальную модель превью: `title` (из первого user-сообщения или явного поля) и/или `preview` + `updated_at` (touch при новом message). Добавить колонки через `ADDITIVE_MIGRATIONS`, если нужны.
2. `list_sessions(db, *, limit/offset)` — сортировка по `updated_at`/`created_at` DESC; опционально фильтр по `status`.
3. `delete_session(db, session_id)` — удалить messages, затем session; 404 если нет.
4. Эндпоинты: `GET /sessions` → список `SessionOut`; `GET /sessions/{id}/messages` → сообщения; `DELETE /sessions/{id}`.
5. При записи сообщений в WS/repo — обновлять `updated_at` (и title при первом user-сообщении, если выбран этот вариант).
6. Тесты: создать 2 сессии с сообщениями → list; get messages одной; delete → list без неё, messages пусты/404.

## Критерии приёмки (Definition of Done)

- [ ] `GET /sessions` возвращает сохранённые сессии (не пусто после диалога), с полями для UI-превью.
- [ ] `GET /sessions/{id}/messages` (или эквивалент) отдаёт полную ленту сообщений сессии.
- [ ] `DELETE /sessions/{id}` удаляет сессию и её сообщения; повторный get/list не показывает её.
- [ ] Данные переживают рестарт backend (SQLite).
- [ ] `ruff check .` и `pytest` в `backend/` зелёные.
