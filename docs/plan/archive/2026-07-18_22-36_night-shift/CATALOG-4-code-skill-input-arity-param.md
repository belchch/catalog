# CATALOG-4 — Параметр входа скила (1 / 2 / список документов)

- **Задача Plane:** [CATALOG-4](https://app.plane.so/belchch/projects/catalog-app/work-items/4) (id: `d3cdce71-2b55-4276-8e77-5a949a1ba52e`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Явный параметр режима входа скила (`1 документ` / `2 документа` / `список`), задаваемый при сохранении (configure), отдаваемый в `SkillOut`, соблюдаемый при apply. UI контролов — в `CATALOG-4-ui-skill-input-controls.md`.

## Постановка задачи (актуальное ТЗ)
_(источник: последний комментарий от 2026-07-18)_

Сделано неверно. Пользователь может указать параметры. Это нужно сделать отдельным параметром при сохранении скила. Выбор в модалке сохранения: 1 документ, 2 документа, список документов. При выполнении скила контрол заполнения параметров разный в зависимости от типа: Combobox (single) / два combobox / Combobox (multi-select).

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

**Описание задачи:** Сейчас можно выбирать только один документ в параметрах скила. Скилы могут принимать один, два или список. Расширить структуру данных, при необходимости доработать UI.

## Контекст

Часть multi-doc уже в коде, но **не совпадает с актуальным ТЗ** (чек-лист без явного параметра сохранения + без разных контролов).

- `SkillConfig.input_arity: int | None` — `backend/app/skills/config.py:63` (`None` = любое число). Планировщик может выставить при build (`skills.py:91,168`), но пользователь в модалке **не выбирает**.
- `SkillConfigureRequest` — только `model/provider/reasoning` (`schemas.py:110-118`); `configure_skill_endpoint` (`skills.py:421-449`) не принимает arity.
- `SkillOut` не отдаёт `input_arity` (`skills.py:469-477`) — apply UI не знает режим.
- Apply уже валидирует arity (`runs.py:61-65`, `apply.py:115-117`).
- Парный UI-план: `CATALOG-4-ui-skill-input-controls.md`.

## Затрагиваемые файлы

- `backend/app/skills/config.py` — уточнить семантику: enum/режим `one|two|list` **или** стабилизировать `input_arity` как `1` / `2` / `null`(=list) и документировать; default при сохранении.
- `backend/app/skills/repo_skill.py` / `update_skill_config` — проброс поля при configure.
- `backend/app/api/schemas.py` — `SkillConfigureRequest.input_arity` (или `input_mode`); `SkillOut` + поле; при необходимости `SkillPreview`.
- `backend/app/api/skills.py` — configure + list_skills отдают параметр.
- `backend/tests/test_api.py` / `test_apply.py` — configure сохраняет режим; apply 422 при неверном числе; list отдаёт поле.

## План действий

1. Зафиксировать модель: три режима — `1`, `2`, `list` (для list — `input_arity is None` или явный `"list"`). Согласовать с существующей валидацией apply.
2. Расширить `SkillConfigureRequest` + `update_skill_config` — пользователь задаёт режим в draft перед commit.
3. Добавить поле в `SkillOut` (и убедиться, что `SkillPreview` уже несёт значение для модалки).
4. Default при build без выбора: разумный fallback (например `1` или значение от planner) — явно описать в коде через поведение API.
5. Тесты configure → get/list → apply с верным/неверным числом doc_ids.

## Критерии приёмки (Definition of Done)

- [ ] При configure можно сохранить режим входа: 1 / 2 / список.
- [ ] `GET /skills` отдаёт этот параметр клиенту.
- [ ] Apply с неверным числом документов для режима 1 или 2 → 422; для списка — ≥1 ок.
- [ ] `ruff check .` и `pytest` в `backend/` зелёные.
