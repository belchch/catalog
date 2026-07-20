# CATALOG-58 — Ошибка создания скилла и таймаут сессии

- **Задача Plane:** [CATALOG-58](https://app.plane.so/belchch/projects/catalog-app/work-items/58) (id: `17d4dccd-ac7e-4a47-9078-b2f510ff47aa`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** (1) Ошибки build скилла доходят до клиента с **понятным** текстом (таймаут / retries / validation), запрос не «висит» бесконечно с точки зрения API-контракта. (2) Per-session HTTP/LLM timeout, default 60с, переопределяемый. UI модалки/кнопки — в `CATALOG-58-ui-build-error-timeout.md`.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи)_

Кнопка «Создать скилл»: сейчас висит в load state, пользователь не видит ошибку.

Дополнительно: модалка увеличить таймаут сессии — изначально 60; пользователь может переопределить в контексте сессии чата.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

Связь: CATALOG-53 убирает LLM из основного build-пути; этот план закрывает ошибки/таймаут для текущего (и fallback) пути.

## Контекст

- Build: `POST /sessions/{id}/skills` → `build_skill_from_session` (`skills.py` ~207–317) — LLM + retries; 422 `"failed to build a valid skill after retries"`.
- Глобальный `httpx.AsyncClient(timeout=60.0)` — `main.py:59`. Per-request/per-session override **нет**.
- Frontend ловит exception в `handleCreateSkill` (`App.tsx:176-188`) → `setNotice`, но при долгих retries кнопка `buildingSkill` «висит»; notice слабозаметен; chat `error` не используется для build.
- Таблица `session` — без поля timeout (`schema.py`).

Парный UI: `docs/plan/next-shift/CATALOG-58-ui-build-error-timeout.md`.

## Затрагиваемые файлы

- `backend/app/storage/schema.py` + repo session — поле `llm_timeout_seconds` (default 60) или аналог
- `backend/app/api/sessions.py` — PATCH timeout / отдача в SessionOut
- `backend/app/main.py` / LLM client — возможность timeout на вызов ≠ только глобальные 60с
- `backend/app/api/skills.py` — map timeout/LLM failures → 504/422 с clear `detail`
- `backend/tests/` — timeout field, error payload shape

## План действий

1. **Session timeout.** Колонка/поле default 60; REST read/update; валидация разумных границ (например 30–300).
2. **LLM calls.** Build (и при возможности planner) читают timeout сессии и передают в httpx/LLM слой.
3. **Ошибки build.** На timeout / exhausted retries — HTTP с явным `detail` (причина + подсказка увеличить timeout). Не глотать как «просто упало».
4. **Тесты.** Update timeout; mock timeout → ожидаемый статус/текст.

## Критерии приёмки (Definition of Done)

- [ ] У сессии есть переопределяемый timeout (default 60).
- [ ] Build при таймауте/фейле возвращает понятный error body (не «тишина»).
- [ ] Значение timeout сессии реально влияет на LLM HTTP timeout.
- [ ] `backend/`: `ruff check .`, `pytest` зелёные.
