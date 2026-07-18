# CATALOG-28 — Документы в контексте чата (backend)

- **Задача Plane:** [CATALOG-28](https://app.plane.so/belchch/projects/catalog-app/work-items/28) (id: `bc1816bc-2837-426d-85fc-9cb70fe241bc`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Детерминированная привязка документов к сессии: таблица `session_document`, attach из WS `doc_ids`, `GET /sessions/{id}/documents`, список в system prompt планировщика. UI — в `CATALOG-28-ui-session-documents.md`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Документы и chat-сессия живут раздельно; планировщик видит доки только через недетерминированные tools. Нужна детерминированная привязка: WS-фрейм `{type:"user", content, doc_ids}`, таблица `session_document`, GET списка, перечень в system prompt. Минимум UX — пикер/чипы (UI-план).

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- Session schema без doc links — `schema.py:18-20`.
- WS user plain-text / JSON parse — `sessions.py`; tools глобальные — `documents/tools.py`.
- Полный текст ТЗ в Plane уже содержит детальный дизайн (таблица, API, WS) — следовать ему.
- Парный UI: `CATALOG-28-ui-session-documents.md`. Out of scope: @mention, полный rehydrate (CATALOG-2), строгий tool-scope.

## Затрагиваемые файлы

- `backend/app/storage/schema.py` — `session_document` + CREATE IF NOT EXISTS.
- `backend/app/storage/repo_session_document.py` (новый) — attach/list.
- `backend/app/api/sessions.py` — parse `doc_ids`, attach, frame `session_docs`, prompt injection.
- `backend/app/api/schemas.py` — при необходимости.
- `backend/tests/` — attach idempotent, GET list, prompt содержит titles.

## План действий

1. Таблица `session_document(session_id, document_id, attached_at)` PK составной.
2. `attach_documents` / `list_session_documents`.
3. `GET /sessions/{id}/documents`.
4. WS: извлечь `doc_ids` → attach → отправить `session_docs`.
5. System prompt: перечислить attached id+title перед turn.
6. Тесты.

## Критерии приёмки (Definition of Done)

- [ ] Отправка user с `doc_ids` создаёт строки `session_document` без дублей при повторе.
- [ ] `GET /sessions/{id}/documents` возвращает привязанный набор.
- [ ] Планировщик получает attached docs в system prompt.
- [ ] `ruff` / `pytest` зелёные.
