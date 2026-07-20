# CATALOG-53 — Скрипт и prompt хранить отдельным артефактом и показывать в чате

- **Задача Plane:** [CATALOG-53](https://app.plane.so/belchch/projects/catalog-app/work-items/53) (id: `cd4eaadf-fbca-47c5-a732-7748b87dcd07`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Prompt и script становятся артефактами сессии в БД; планировщик пишет/читает их инструментами; `POST /sessions/{id}/skills` упаковывает готовый артефакт в `SkillConfig` **без LLM** в основном пути (fallback LLM для старых сессий без артефактов). UI-канвас — в парном плане `CATALOG-53-ui-session-artifacts-panel.md` (после этого code-шага).

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи)_

Артефакты сессии: prompt и script как редактируемые сущности. Планировщик материализует их инструментами по ходу диалога; пользователь правит руками; build = упаковка без LLM.

**Часть Backend (этот план):**

1. Таблица `session_artifact` + repo (upsert/get/list/delete).
2. Tools планировщика: `save_skill_prompt`, `save_skill_script` (+ `validate_script`), `set_skill_meta`, `read_skill_draft`; WS-кадр `session_artifacts`.
3. REST: `GET/PATCH` артефактов и меты.
4. `build_skill_from_session` — упаковка из артефактов; fallback LLM если артефактов нет.
5. Edit-сессия (`POST /skills/{id}/edit`) — засеять артефакты из текущего конфига.

Полная спецификация потока и DDL — в описании Plane (sequenceDiagram, развилки kind/meta/allowed_tools).

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

Сейчас `system_prompt`/`code` живут только внутри `skill.config_json` после `build_skill_from_session` (`backend/app/api/skills.py` ~207+): один синхронный LLM-вызов из истории чата, таймаут 60с × retries (`main.py:59`) → «висит и отваливается».

- Конфиг: `backend/app/skills/config.py` (`SkillConfig.system_prompt` / `code` / `kind`)
- Документ-tools паттерн: `backend/app/documents/tools.py` → аналогично `build_artifact_tools`
- WS сессии: `backend/app/api/sessions.py` (~`PLANNER_SYSTEM_PROMPT:54`, регистрация tools ~370)
- `validate_script`: `backend/app/skills/script_runner.py`
- Таблицы: `backend/app/storage/schema.py` (+ ADDITIVE_MIGRATIONS)

Парный UI-план: `docs/plan/next-shift/CATALOG-53-ui-session-artifacts-panel.md` — зависит от REST/WS этого шага.

Связь с CATALOG-58: быстрый build без LLM снимает часть «висит»; отдельная задача — UX ошибок и таймаут.

## Затрагиваемые файлы

- `backend/app/storage/schema.py` — таблица `session_artifact`
- `backend/app/storage/repo_session_artifact.py` — **новый**
- `backend/app/api/sessions.py` — tools, prompt, REST artifacts, WS frame
- `backend/app/documents/tools.py` или новый `backend/app/skills/artifact_tools.py` — `build_artifact_tools`
- `backend/app/api/skills.py` — build без LLM + seed при edit
- `backend/app/api/schemas.py` — схемы артефактов / ответов
- `backend/tests/` — тесты repo, tools, build-from-artifacts, edit seed

## План действий

1. **Схема + repo.** DDL из ТЗ (`session_id`, `type` prompt|script|meta, `content`, `is_valid`, `error`, `source`, `updated_at`). Repo: upsert/get/list/delete.
2. **Artifact tools.** `save_skill_prompt`, `save_skill_script` (validate_script → is_valid/error), `set_skill_meta`, `read_skill_draft`. После save — WS `session_artifacts`.
3. **PLANNER_SYSTEM_PROMPT.** Когда задача прояснилась — материализовать артефакт инструментом; не дублировать полный prompt/script в чат.
4. **REST.** `GET /sessions/{id}/artifacts`, `PATCH .../artifacts/{type}`, правка meta; script → validate.
5. **Build.** Читать meta + артефакт по kind → `_args_to_config` / `_validate_config` → create/update skill. Нет артефактов → legacy LLM fallback. Невалидно → 422 с текстом.
6. **Edit seed.** `POST /skills/{id}/edit` заполняет `session_artifact` из конфига.
7. **Тесты.** Upsert, validate script path, build без LLM, fallback, edit seed.

## Критерии приёмки (Definition of Done)

- [ ] Таблица `session_artifact` и repo работают (upsert по `(session_id, type)`).
- [ ] Планировщик может сохранить/прочитать prompt, script, meta через tools; WS шлёт `session_artifacts`.
- [ ] REST GET/PATCH артефактов; script валидируется, `is_valid`/`error` отдаются.
- [ ] Build из валидных артефактов — без LLM, быстро; пустые/битые → понятная 422.
- [ ] Старые сессии без артефактов — legacy LLM build (fallback).
- [ ] Edit-сессия засевает артефакты из существующего skill.
- [ ] `backend/`: `ruff check .`, `pytest` зелёные.
