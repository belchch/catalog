# CATALOG-35 — Параметры модели в скиле (API)

- **Задача Plane:** [CATALOG-35](https://app.plane.so/belchch/projects/catalog-app/work-items/35) (id: `1877d641-2893-422a-88d0-024c5895adc7`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** `GET /skills` отдаёт provider, model, reasoning для карточки. UI — в `CATALOG-35-ui-skill-model-params.md`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

У скила нужно отображать также параметры — провайдер, модель, рассуждения.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- Поля есть в `SkillConfig` / `config_json` — `config.py`.
- `SkillOut` и `list_skills_endpoint` не отдают model/provider/reasoning — `schemas.py:15-24`, `skills.py:463-478`.
- `list_skills` в repo парсит config для kind/tags, но не для model — `repo_skill.py`.

## Затрагиваемые файлы

- `backend/app/api/schemas.py` — поля в `SkillOut`.
- `backend/app/api/skills.py` / `repo_skill.py` — заполнение из config.
- `backend/tests/` — list содержит параметры.

## План действий

1. Добавить `provider`, `model`, `reasoning` (nullable) в `SkillOut`.
2. Читать из config при list.
3. Тест.

## Критерии приёмки (Definition of Done)

- [ ] `GET /skills` возвращает provider/model/reasoning для скилов, где они заданы.
- [ ] `ruff` / `pytest` зелёные.
