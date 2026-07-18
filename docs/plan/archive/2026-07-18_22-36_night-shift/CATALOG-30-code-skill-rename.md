# CATALOG-30 — Редактирование имени скила (API)

- **Задача Plane:** [CATALOG-30](https://app.plane.so/belchch/projects/catalog-app/work-items/30) (id: `04bacb19-c59b-45b2-8638-991405998716`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** API для смены имени при configure (draft) и для сохранённых (committed) скилов. UI — в `CATALOG-30-ui-skill-rename.md`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Имя скила можно править при сохранении и редактировать у сохранённых скилов.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- `SkillConfigureRequest` — model/provider/reasoning only — `schemas.py:110-118`.
- `configure` только для draft (409 иначе) — `skills.py:421-449`.
- `update_skill_config` не трогает колонку `name` — `repo_skill.py:175-207`.
- Имя меняется косвенно через edit-сессию planner (`update_skill(..., name=…)`).

## Затрагиваемые файлы

- `backend/app/api/schemas.py` — `name` в configure и/или `PATCH /skills/{id}` rename.
- `backend/app/skills/repo_skill.py` — обновление `name` (+ sync `config.name` если есть).
- `backend/app/api/skills.py` — разрешить rename для committed (отдельный endpoint или расширить configure).
- `backend/tests/` — draft rename при configure; committed rename.

## План действий

1. Добавить `name` в configure для draft (модалка сохранения).
2. Endpoint rename для committed (например `PATCH /skills/{id}` с `{name}`) — configure остаётся draft-only для model settings **или** ослабить ограничение только для `name`.
3. Синхронизировать `skill.name` и поле в `config_json` при наличии.
4. Тесты.

## Критерии приёмки (Definition of Done)

- [ ] Draft: имя сохраняется через configure вместе с настройками модели.
- [ ] Committed: имя можно сменить без полной edit-сессии.
- [ ] `GET /skills` отражает новое имя.
- [ ] `ruff` / `pytest` зелёные.
