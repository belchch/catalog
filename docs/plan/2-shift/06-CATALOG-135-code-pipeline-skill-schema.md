# CATALOG-135 — code: шаг pipeline типа skill — схема, валидация, снапшот при сборке

- **Задача Plane:** [CATALOG-135](https://app.plane.so/belchch/projects/catalog-app/work-items/135) (id: `8872857a-eaee-4d6b-b725-f0d5c49741dc`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 06 · blocked_by CATALOG-134 · blocking CATALOG-136
- **Цель:** Черновик и сборка принимают шаг `skill`: ссылка в артефакте, снапшот в `config_json`, честная валидация, рекурсивная оценка цены. Рантайм — следующая задача.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

После ADR-0022. Только черновик и сборка — рантайм в CATALOG-136.

1. `PIPELINE_STEP_TYPES` += `"skill"`.
2. `PipelineStep`: `skill_id`, `skill_name`, `config_hash`, вложенный снапшот; через `to_dict`/`from_dict`; старые шаги без миграции.
3. `save_skill_steps`: enum + `skill_id`; модель пишет ссылку, снапшот делает сборка.
4. Планировщик должен знать id прикреплённых скиллов: тул `list_session_skills` или таблица в системном промпте. Имя не из `_RESERVED`.
5. `validate_pipeline_steps`: черновик — непустой `skill_id`; сборка — снапшот; скилл `committed` и прикреплён к сессии.
6. Разворачивание ссылки в `_build_skill_from_artifacts` (pipeline-ветка).
7. `estimate_skill_llm_calls`: для `skill`-шага рекурсивно по вложенному конфигу.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/2-shift/05-CATALOG-134-code-adr-pipeline-skill-step.md`.

- `backend/catalog/skills/config.py:15,31-93` — типы и сериализация шага без skill-полей.
- `backend/catalog/skills/artifact_tools.py:79-114` — валидация script/llm; `354-400` — схема `save_skill_steps`.
- `backend/catalog/api/skills.py:494-548` — сборка заливает пустые script/llm из артефактов.
- `backend/catalog/skills/budget.py:95-111` — pipeline = `len(steps) * max_iterations`.
- `backend/catalog/skills/skill_tools.py:49-59` — `_RESERVED`; `config_hash` уже есть.
- `backend/catalog/api/sessions.py:103` — системный промпт планировщика.

Рантайм: `docs/plan/2-shift/07-CATALOG-136-code-pipeline-skill-runtime.md`.

## Затрагиваемые файлы
- `backend/catalog/skills/config.py` — тип, поля, сериализация.
- `backend/catalog/skills/artifact_tools.py` — схема тула, валидация.
- `backend/catalog/api/skills.py` — снапшот при сборке.
- `backend/catalog/skills/budget.py` — рекурсивная оценка.
- `backend/catalog/skills/artifact_tools.py` или `skill_tools.py` / `sessions.py` — `list_session_skills` либо таблица в промпте.
- Тесты сборки, 422, изоляция снапшота, оценка цены.

## План действий
1. Расширить `PipelineStep` и сериализацию; неизвестные старые поля не ломать.
2. Валидация: draft vs build; 422 на draft/чужой/неприкреплённый id.
3. Сборка: достать committed скилл, вкопировать конфиг, посчитать `config_hash`.
4. Дать планировщику id прикреплённых скиллов.
5. Рекурсивный `estimate_skill_llm_calls`.
6. Тест: правка источника после сборки не меняет родителя.

## Критерии приёмки (Definition of Done)
- [ ] `save_skill_steps` принимает `{type:"skill", skill_id}`.
- [ ] Сборка кладёт полный вложенный конфиг и `config_hash` в родителя.
- [ ] Правка вызываемого скилла после сборки не меняет `config_json` родителя.
- [ ] draft / несуществующий / не прикреплённый id → 422.
- [ ] Планировщик может поставить шаг `skill` без помощи пользователя.
- [ ] Старые конфиги читаются без изменений.
- [ ] Оценка цены учитывает вложенную стоимость.
- [ ] `ruff check .`, `pytest` из `backend/`.
