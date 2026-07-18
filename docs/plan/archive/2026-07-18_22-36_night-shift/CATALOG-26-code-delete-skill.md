# CATALOG-26 — Удаление скила (API)

- **Задача Plane:** [CATALOG-26](https://app.plane.so/belchch/projects/catalog-app/work-items/26) (id: `b3916b33-ba95-4b77-a929-4559e6de6d9e`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Backend API удаления скила (draft и committed). UI — в `CATALOG-26-ui-delete-skill.md`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Сделать функцию удаления скила.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- Skills API: build/configure/commit/list/edit — `skills.py`; **нет DELETE**.
- Repo: `create`/`update`/`update_status` — `repo_skill.py`; **нет delete**.
- `skill_run.skill_id` без cascade — решить: удалять runs / запретить delete при runs / cascade.

## Затрагиваемые файлы

- `backend/app/skills/repo_skill.py` — `delete_skill`.
- `backend/app/api/skills.py` — `DELETE /skills/{id}`.
- `backend/app/skills/repo_run.py` — cascade или orphan policy.
- `backend/tests/test_api.py` — delete draft/committed, 404.

## План действий

1. Политика: hard-delete skill; runs — cascade delete или nullify `skill_id` (предпочтительно cascade delete runs скила).
2. `DELETE /skills/{id}` → 204/200; 404 если нет.
3. Тесты на оба статуса.

## Критерии приёмки (Definition of Done)

- [ ] `DELETE /skills/{id}` удаляет скил; `GET /skills` его не показывает.
- [ ] Связанные runs обработаны по выбранной политике.
- [ ] `ruff` / `pytest` зелёные.
