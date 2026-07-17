# CATALOG-17 — Редактирование скила

- **Задача Plane:** [CATALOG-17](https://app.plane.so/belchch/projects/catalog-app/work-items/17) (id: `a94faf6e-5278-46a9-8a64-620df032bbc8`)
- **Статус плана:** Re-analyzed (против HEAD после merge PR #6 / phase 2)
- **Цель:** Добавить редактирование существующего скилла: по инициативе пользователя открывается чат планировщика, **уже предзаполненный контекстом** текущего `SkillConfig`; сборка **обновляет** исходный скилл (тот же `id`), а не создаёт новый.

## Контекст (актуально на HEAD)

Жизненный цикл скилла сейчас: создать → (опционально) настроить model/provider/reasoning → commit → apply.

- Создание: `POST /sessions` → WS planner → `POST /sessions/{id}/skills` → `build_skill_from_session` (`backend/app/api/skills.py`) → всегда `create_skill` (`repo_skill.py`) → draft. Затем UI открывает `SkillSettingsModal` (CATALOG-6).
- **Уже есть (не путать с edit):** `update_skill_config` (`repo_skill.py`) + `PATCH /skills/{id}/configure` — точечный override только `model` / `provider` / `reasoning` для draft (settings modal). Это **не** полное обновление name/description/config из сессии редактирования.
- **Нет:** endpoint старта edit-сессии, колонки `session.skill_id`, полного `update_skill`, кнопки «Редактировать», режима UI «Сохранить изменения».
- `session` (`schema.py`): `id, status, created_at` — связи session↔skill нет.
- `ADDITIVE_MIGRATIONS` (`schema.py` + `db.init_schema`) уже используется (паттерн CATALOG-4 для `skill_run.input_doc_ids`) — сюда же добавить `session.skill_id`.
- Frontend checks: **`pnpm`** (`pnpm run build` / `lint` / `typecheck`), не npm.

## Решения (зафиксировано)

1. **Один endpoint старта:** `POST /skills/{skill_id}/edit` → создать session с `skill_id`, предзаполнить сообщение с текущим конфигом, вернуть `{session_id, skill_id}`.
2. **Сборка:** `build_skill_from_session` читает `session.skill_id`; если задан → `update_skill(...)` (тот же id), иначе `create_skill` как сейчас.
3. **Статус:** редактирование **committed** → после успешного save статус **`draft`** (нужен повторный commit). Draft остаётся draft.
4. **Связь:** nullable `session.skill_id` + additive `ALTER TABLE`.
5. **Не трогать** контракт `update_skill_config` / configure modal — после edit-save UI может по-прежнему открыть settings modal на обновлённом draft (как после обычного build).

## Затрагиваемые файлы

**Backend:**
- `backend/app/storage/schema.py` — `skill_id TEXT` в `CREATE TABLE session`; запись в `ADDITIVE_MIGRATIONS`: `("session", "skill_id", "ALTER TABLE session ADD COLUMN skill_id TEXT")`.
- `backend/app/storage/repo_session.py` — `SessionRow.skill_id`; `create_session(..., skill_id=None)`; `get_session` читает колонку.
- `backend/app/skills/repo_skill.py` — новый `update_skill(db, skill_id, *, name, description, config, status=None)`: полный UPDATE name/description/config_json + optional status + `updated_at`. **Не** заменять `update_skill_config`.
- `backend/app/api/skills.py`:
  - `POST /skills/{skill_id}/edit` — 404 если скилла нет; `create_session(skill_id=...)`; `add_message` с человекочитаемым дампом текущего конфига и пометкой «редактируем этот скилл»; ответ `EditStarted` / расширенный schema.
  - `build_skill_from_session` — ветка update vs create по `session.skill_id`; при update committed → `status="draft"`.
- `backend/app/api/schemas.py` — `EditStarted { session_id, skill_id }` (или эквивалент).
- Тесты: `backend/tests/test_api.py` / build-тесты — edit создаёт сессию с `skill_id` и историей; build из edit не меняет id; обычный build по-прежнему создаёт новый.

**Frontend:**
- `frontend/src/api.ts` — `startEditSession(skillId)`.
- `frontend/src/components/SkillsPanel.tsx` — кнопка «Редактировать» → `onEdit(skillId)` (для draft и committed).
- `frontend/src/App.tsx` — `handleEditSkill`: start edit session, `setSessionId`, сбросить `activeRunId`, флаг режима редактирования; `handleCreateSkill` остаётся единым build-обработчиком.
- `frontend/src/components/Chat.tsx` — подпись кнопки: «Создать скилл из сессии» vs «Сохранить изменения»; баннер «Редактирование: {name}».

## План действий

1. Схема + additive migration для `session.skill_id`.
2. Репо сессии: проброс `skill_id`.
3. Репо скилла: `update_skill` (полный), рядом с существующим `update_skill_config`.
4. `POST /skills/{id}/edit` + предзаполнение сообщения.
5. Ветка в `build_skill_from_session`: update + draft-after-committed.
6. Backend-тесты edit/update/regression create.
7. Frontend API + SkillsPanel + App + Chat.
8. Проверки: backend `ruff`/`pytest`; frontend `pnpm run build`/`lint`/`typecheck`.

## Критерии приёмки (Definition of Done)

- [ ] В `SkillsPanel` для каждого скилла есть кнопка **«Редактировать»**.
- [ ] По нажатию открывается чат планировщика с предзаполненным контекстом редактируемого скилла.
- [ ] Сборка из edit-сессии **обновляет** существующий скилл (тот же `id`): меняются `config_json` / `name` / `description` / `updated_at`.
- [ ] Обычное создание (сессия без `skill_id`) по-прежнему создаёт новый скилл.
- [ ] `session.skill_id` есть в схеме и в additive migration.
- [ ] После save committed-скилл становится `draft`.
- [ ] `update_skill_config` / `PATCH .../configure` не сломаны (CATALOG-6).
- [ ] backend: `ruff check .`, `pytest` зелёные; есть кейсы edit + update-build.
- [ ] frontend: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` зелёные.
