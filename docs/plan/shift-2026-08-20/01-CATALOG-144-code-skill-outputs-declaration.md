# CATALOG-144 — code: декларация выходов — артефакт черновика outputs и поле SkillConfig

- **Задача Plane:** [CATALOG-144](https://app.plane.so/belchch/projects/catalog-app/work-items/144) (id: `f34348e2-6865-454d-8fed-c8f224a0d41c`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 01 · blocked_by CATALOG-143 · blocking CATALOG-145 · blocking CATALOG-147 · blocking CATALOG-146
- **Цель:** Завести тип артефакта `outputs`, тул `set_skill_outputs` и поле `SkillConfig.outputs`. Рантайм и UI не трогать.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. Порядок: после ADR-0024, до рантайма и персиста.

`session_artifact` держит один текущий артефакт на тип, PK `(session_id, type)`, типы `'prompt' | 'script' | 'meta' | 'steps'` (`storage/schema.py:108-118`). Тип `steps` добавили позже без миграции — тот же приём годится для выходов. Планировщик пишет артефакты тулами `save_skill_prompt` / `save_skill_script` / `save_skill_steps` / `set_skill_meta`, build = упаковка без LLM (`_build_skill_from_artifacts`) — ADR-0015.

Класть выходы внутрь `meta` не стоит: `set_skill_meta` перезаписывает JSON целиком. Отдельный тип дешевле и даёт свою карточку в UI.

Повторяемость скилла (ADR-0002) требует, чтобы контракт выходов жил в замороженном конфиге.

Что сделать:

1. Тип артефакта `outputs`, контент — JSON `[{"key": ..., "description": ...}]`. Валидация: ключи уникальны, `^[a-z][a-z0-9_]{0,31}$`, не больше 8, `description` непустое. Невалидный контент — `is_valid=0` + `error`, как у `script`.
2. Тул `set_skill_outputs`; `read_skill_draft` отдаёт выходы. После save — WS-кадр `session_artifacts`.
3. REST `GET/PATCH /sessions/{id}/artifacts` для типа `outputs` (`source=user`), та же валидация.
4. `SkillConfig.outputs` — список `SkillOutput{key, description}` в `skills/config.py:147-217`. Нет ключа = пустой список. Порядок значим: `outputs[0]` — primary.
5. Build переносит выходы в конфиг; битый артефакт — 422.
6. Edit-сессия (`POST /skills/{id}/edit`) засевает `outputs` из конфига.
7. Промпт планировщика: когда объявить несколько выходов; описания — человеку и автору кода; ключи сверяются с возвратом. Для `script` те же ключи в словаре.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

Предусловие: `CATALOG-143` (ADR-0024). Этот шаг только декларация — без персиста и UI.

- `backend/catalog/storage/repo_session_artifact.py:10` — `ARTIFACT_TYPES = ("prompt", "script", "meta", "steps")`; неизвестный тип — `ValueError`.
- `backend/catalog/storage/schema.py:108-118` — тип артефакта это TEXT, миграция не нужна.
- `backend/catalog/skills/artifact_tools.py:580+` — `build_artifact_tools`: `save_skill_prompt` / `save_skill_script` / `set_skill_meta` / `save_skill_steps` / `read_skill_draft` (`736-747`). После save шлётся `session_artifacts`.
- `backend/catalog/api/sessions.py:101-136` — `PLANNER_SYSTEM_PROMPT` перечисляет тулы материализации, `set_skill_outputs` нет.
- `backend/catalog/api/sessions.py:510-555` — `GET/PATCH /sessions/{id}/artifacts/{artifact_type}`; PATCH режет неизвестный тип 404.
- `backend/catalog/api/skills.py:489-608` — `_build_skill_from_artifacts` собирает meta/prompt/script/steps; выходов нет. Невалидный артефакт → 422.
- `backend/catalog/api/skills.py:846-925` — `seed_session_artifacts_from_skill` засевает meta/prompt/script/steps, `outputs` нет.
- `backend/catalog/skills/config.py:147-251` — `SkillConfig` без `outputs`; `from_json` уже дефолтит отсутствующие ключи.
- `backend/catalog/skills/skill_tools.py:90` / `apply.py:86-87` — `config_hash` = sha256 от `to_json`; новое поле само попадёт в хеш.
- `frontend/src/api.ts:619` — `ArtifactType` без `outputs` (карточка — `CATALOG-146`).

Тесты-якоря: `backend/tests/test_session_artifacts.py`, `backend/tests/test_apply.py` (round-trip `SkillConfig`).

## Затрагиваемые файлы
- `backend/catalog/skills/config.py` — `SkillOutput`, поле `outputs`, сериализация.
- `backend/catalog/storage/repo_session_artifact.py` — тип `outputs` в `ARTIFACT_TYPES`.
- `backend/catalog/skills/artifact_tools.py` — тул `set_skill_outputs`, отдача в `read_skill_draft`, валидация.
- `backend/catalog/api/sessions.py` — PATCH для `outputs`; строка в `PLANNER_SYSTEM_PROMPT`.
- `backend/catalog/api/skills.py` — build + seed edit-сессии.
- `backend/tests/test_session_artifacts.py` — тул/REST/валидация.
- `backend/tests/test_apply.py` — round-trip `outputs` и конфиг без ключа.

## План действий
1. Добавить `SkillOutput` и `SkillConfig.outputs` (default `[]`); `to_json` / `from_json` — отсутствие ключа = пустой список, порядок сохраняется.
2. Вынести валидатор списка выходов (уникальность, regex, лимит 8, непустое description) — общий для тула, REST и build.
3. Расширить `ARTIFACT_TYPES` типом `outputs`.
4. Зарегистрировать `set_skill_outputs` рядом с `set_skill_meta`; невалидный JSON писать с `is_valid=0` + `error` (как script), не ронять тул исключением. После save — тот же WS-кадр.
5. `read_skill_draft` отдаёт parsed `outputs` вместе с `artifacts`.
6. PATCH `/sessions/{id}/artifacts/outputs` — та же валидация, `source=user`. GET уже отдаёт все типы через `list_artifacts`.
7. `_build_skill_from_artifacts`: есть валидный `outputs` → в конфиг; нет артефакта → `[]`; битый/невалидный → 422.
8. `seed_session_artifacts_from_skill`: непустой `config.outputs` → артефакт `outputs`.
9. Дописать `PLANNER_SYSTEM_PROMPT`: когда объявлять несколько выходов; ключи сверяются с возвратом; для script — те же ключи в dict.
10. Тесты: валидный/невалидный тул и REST; round-trip; build без артефакта; edit seed; смена `outputs` меняет `config_hash`.

## Критерии приёмки (Definition of Done)
- [ ] Тул и REST создают/правят артефакт `outputs`; невалидный JSON, дубль ключа, плохой ключ, пустое описание и 9-й выход отклоняются с внятным сообщением.
- [ ] `SkillConfig` с выходами переживает round-trip `to_json` → `from_json`; конфиг без ключа `outputs` читается как пустой список.
- [ ] Build переносит декларацию в конфиг; скилл без артефакта `outputs` собирается как раньше.
- [ ] Edit-сессия показывает выходы существующего скилла.
- [ ] `config_hash` меняется при правке выходов.
- [ ] Backend: `ruff check .`, `pytest` зелёные.
