# CATALOG-17 — Редактирование скила

- **Задача Plane:** [CATALOG-17](https://app.plane.so/belchch/projects/catalog-app/work-items/17) (id: `a94faf6e-5278-46a9-8a64-620df032bbc8`, state: In Progress)
- **Статус плана:** Analyzed
- **Цель:** Добавить функцию редактирования существующего скилла: по инициативе пользователя открывается чат планировщика, **уже предзаполненный контекстом редактируемого скилла** (текущий `SkillConfig`); дальнейший процесс повторяет создание — из истории сессии собирается обновлённый конфиг, но он **обновляет** исходный скилл, а не создаёт новый.

## Контекст

Сейчас жизненный цикл скилла — только «создать» и «выполнить»:

- Создание: `POST /sessions` → новая сессия (`create_session`, `repo_session.py:34-43`, статус `planning`); WS `/sessions/{id}` (`sessions.py:68-145`) — чат планировщика, сообщения персистятся через `add_message`. Затем `POST /sessions/{id}/skills` (`skills.py:198-215`) → `build_skill_from_session` (`skills.py:113-195`): читает `list_messages(db, session_id)`, гоняет LLM с инструментом `build_skill` (`skills.py:69-73`), валидирует конфиг (`_validate_config`, `skills.py:99-110`) и вызывает **`create_skill`** (`repo_skill.py:50-67`) — всегда **новая** строка `draft`. В конце `update_session_status(db, session_id, "done")`.
- Хранилище скилла (`repo_skill.py`): `create_skill`, `get_skill`, `list_skills`, `update_status` (`repo_skill.py:108-115` — меняет только `status`). **Функции обновления конфига нет.**
- `skill` (`schema.py:27-31`): `id, name, description, config_json, status(draft|committed), created_at, updated_at`. Версионирования нет.
- `session` (`schema.py:18-20`): `id, status(planning|done), created_at`. **Связи session↔skill нет** — непонятно, редактируется ли скилл в данной сессии.
- Фронт: `Chat.tsx` рисует кнопку «Создать скилл из сессии» (`Chat.tsx:75-81`) → `onCreateSkill` (`App.tsx:44-57` `handleCreateSkill` → `buildSkill(sessionId)` `api.ts:77-79`). `SkillsPanel.tsx` для скиллов показывает «Коммит» (draft) / «Применить» (committed), **кнопки «Редактировать» нет**.

Что нужно для редактирования (по описанию задачи — «процесс повторяет создание», но в контексте существующего скилла):

1. **Предзаполнение контекста.** При старте редактирования создать сессию и сразу положить в неё сообщение с текущим конфигом скилла, чтобы и планировщик, и `build_skill_from_session` «видели» редактируемый скилл.
2. **Связь session→skill.** Чтобы `build_skill_from_session` знал, что это редактирование, и обновлял существующий скилл, а не создавал новый. Минимально — колонка `skill_id` (nullable) в `session`.
3. **Обновление конфига.** Новый репо-метод `update_skill(db, skill_id, name, description, config)` — перезаписывает `config_json`/`name`/`description`, обновляет `updated_at` (статус можно оставить, сместить в `draft` — решение ниже).
4. **UI.** Кнопка «Редактировать» в `SkillsPanel`; открытие чата в режиме редактирования; кнопка сборки меняет смысл на «Сохранить изменения».

## Затрагиваемые файлы

**Backend:**
- `backend/app/storage/schema.py:18-20` — добавить колонку `skill_id TEXT` в `session` (nullable; `CREATE TABLE IF NOT EXISTS` + обеспечить создание через `ALTER TABLE ... ADD COLUMN` для существующих баз, т.к. миграций нет — см. `schema.py:1-8` комментарий про single source of truth).
- `backend/app/storage/repo_session.py` — `create_session(..., skill_id=None)` пишет `skill_id`; `get_session` отдаёт его в `SessionRow`.
- `backend/app/skills/repo_skill.py` — новый `update_skill(db, skill_id, *, name, description, config, status=None)`: `UPDATE skill SET name=?, description=?, config_json=?, status=COALESCE(?,status), updated_at=?`.
- `backend/app/api/skills.py`:
  - `build_skill_from_session` (`skills.py:113-195`) — принимать/читать `target_skill_id` из сессии; при наличии — `update_skill(...)` вместо `create_skill` (возвращать тот же id); в режиме редактирования не сбрасывать `committed` без необходимости (или сбрасывать в `draft` — зафиксировать в решении).
  - Новый эндпоинт `POST /skills/{skill_id}/edit` (`skills.py`): создать сессию с `skill_id=skill_id`, предзаполнить сообщение с текущим `SkillConfig` (сериализация `config.to_json()` человекочитаемо), вернуть `{session_id, skill_id}`. Либо `POST /skills/{skill_id}/sessions`.
- `backend/app/api/schemas.py` — `EditStarted { session_id, skill_id }` (или переиспользовать `SessionCreated`); при необходимости расширить `SkillBuilt`/добавить `SkillUpdated`.
- `backend/tests/test_api.py`, `backend/tests/test_build.py` (если есть) — кейсы: `POST /skills/{id}/edit` создаёт сессию с предзаполненным контекстом и `skill_id`; build из edit-сессии обновляет тот же скилл (`id` не меняется, `config_json`/`updated_at` меняются).

**Frontend:**
- `frontend/src/api.ts` — `startEditSession(skillId): Promise<{session_id, skill_id}>`; `buildSkill(sessionId)` остаётся (обновление/создание определяется сервером по `session.skill_id`).
- `frontend/src/components/SkillsPanel.tsx` — кнопка «Редактировать» для каждого скилла → `onEdit(skillId)` (рядом с «Коммит»/«Применить», `SkillsPanel.tsx:49-83`).
- `frontend/src/components/Chat.tsx` — подпись кнопки сборки зависит от режима: «Создать скилл из сессии» vs «Сохранить изменения» (`Chat.tsx:75-81`); баннер «Редактирование: {skill name}».
- `frontend/src/App.tsx` — `handleEditSkill(skillId)`: стартовать edit-сессию, выставить `sessionId`, сбросить `activeRunId`, пометить режим редактирования (для подписи кнопки и, возможно, цели сборки); переиспользовать `handleCreateSkill` (build по `sessionId`).

## План действий

1. **Схема.** В `schema.py` добавить `skill_id TEXT` в `session` (nullable). Т.к. миграций нет и `CREATE TABLE IF NOT EXISTS` не добавит колонку в существующую базу — добавить безопасный `ALTER TABLE session ADD COLUMN skill_id TEXT` (catch `duplicate column`), либо документировать, что нужен fresh `catalog.db` в dev (data-root из CATALOG-20 упрощает это).
2. **Репо сессии.** `repo_session.create_session(..., skill_id=None)` и `get_session` пробрасывают `skill_id` в `SessionRow`.
3. **Репо скилла.** Реализовать `update_skill(db, skill_id, *, name, description, config, status=None)` в `repo_skill.py` (UPDATE + `updated_at`).
4. **Эндпоинт edit.** `POST /skills/{skill_id}/edit` (`skills.py`): проверить `get_skill` (404 если нет); создать сессию `create_session(db, skill_id=skill_id)`; предзаполнить контекст — `add_message(role="assistant"|"user", content=render(skill.config))` с текущим конфигом и пометкой «редактируем этот скилл»; вернуть `{session_id, skill_id}`.
5. **Сборка → обновление.** В `build_skill_from_session` после успешной валидации: если у сессии есть `skill_id` → `update_skill(db, skill_id, ...)` (вернуть тот же id); иначе `create_skill` (как сейчас). Зафиксировать поведение статуса: редактирование committed-скилла → сброс в `draft` (требует повторного коммита) — описать в плане/комменте.
6. **Тесты.** Backend: edit стартует сессию с `skill_id` и непустой историей; build из edit-сессии не меняет `skill.id`, но обновляет `config_json`/`updated_at`; обычный build по-прежнему создаёт новый скилл.
7. **Фронт — API.** `startEditSession(skillId)` в `api.ts`.
8. **Фронт — UI.** Кнопка «Редактировать» в `SkillsPanel` → `onEdit`. В `App.handleEditSkill` стартовать edit-сессию, выставить `sessionId` (WS переподключится, предзаполненная история подгрузится), сбросить `activeRunId`. В `Chat` менять подпись кнопки и показывать баннер режима; `handleCreateSkill` остаётся единым обработчиком сборки.
9. **Ручная проверка.** Нажать «Редактировать» на committed-скилле → открывается чат с контекстом скилла; спросить правки; «Сохранить изменения» → тот же скилл обновлён (id прежний, конфиг новый, статус `draft`), появляется в списке; после коммита — применяется как обычно.

## Критерии приёмки (Definition of Done)

- [ ] В `SkillsPanel` для каждого скилла есть кнопка **«Редактировать»**.
- [ ] По нажатию открывается чат планировщика, в котором уже присутствует контекст редактируемого скилла (видимая предзаполненная история/сообщение с текущим конфигом).
- [ ] Сборка из режима редактирования **обновляет существующий скилл** (тот же `id`), а не создаёт новый: `config_json`/`name`/`description`/`updated_at` меняются.
- [ ] Обычное создание скилла (без edit-сессии) по-прежнему создаёт новый скилл — регрессии нет.
- [ ] Связь session↔skill сохранена в БД (колонка `skill_id` в `session`).
- [ ] После редактирования committed-скилл переходит в `draft` (требует повторного коммита) — либо иное явно задокументированное поведение статуса.
- [ ] `backend`: `pytest backend/tests` зелёные, добавлены кейсы для edit-сессии и update-сборки.
- [ ] `backend`: `ruff check backend` без ошибок.
- [ ] `frontend`: `npm run typecheck`/`npm run lint` (если настроены) проходят.
- [ ] Ручная проверка полного цикла edit → save → commit → apply успешна.
