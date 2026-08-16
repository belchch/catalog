# CATALOG-84 — Pipeline-скилы: движок + создание из чата (этап 1)

- **Задача Plane:** [CATALOG-84](https://app.plane.so/belchch/projects/catalog-app/work-items/84) (id: `b8fb8b18-86c4-4c4c-a6f8-aef9296e0ebb`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 03 · независимый
- **Цель:** Третий `kind=pipeline`: схема шагов в `SkillConfig`, линейный прогон в `_apply_core`, список строк из `_extract_result`, артефакт `steps` + тул `save_skill_steps`, `compute_tags` оба тега. Map/fan-out вне scope (CATALOG-107).

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

Этап 1 по ADR-0018: движок линейного pipeline и создание из чата-планировщика.

Критерии: `SkillConfig` принимает `kind="pipeline"` и список шагов; `to_json`/`from_json` совместимы со старыми конфигами; шаг: `id`, `type` (script|llm), источник входа; у llm — model, provider, reasoning, промпт, `allowed_tools`; `_apply_core` линейно, значение между шагами — строка или список строк; `_extract_result` допускает список строк; события трейса несут id шага; создание из чата: артефакт `steps`, `save_skill_steps`, `kind` в `set_skill_meta`, правка `PLANNER_SYSTEM_PROMPT`; `compute_tags` → `python` и `ai`; тесты: `script → llm → script`, старый конфиг, падение шага.

Вне scope: map/fan-out, витрина системных скилов, UI-переопределение модели в модалке. Verify только на финале, без retry. Промежуточные результаты только в трейсе.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Парный UI-план: `docs/plan/2-shift/04-CATALOG-84-ui-pipeline-steps.md`. Этот `code`-план — предусловие (события с `step_id`, артефакт `steps`).

Сейчас `kind` только `agent`|`script` (`backend/catalog/skills/config.py:28-69`). `_apply_core` ветвится на script vs agent (`apply.py:138-141`, `199+`). `_extract_result` принимает только скаляр/`str` (`script_runner.py:305-320`). `_validate_meta_fields` отвергает всё кроме agent/script (`artifact_tools.py:54-56`). `set_skill_meta` enum `["agent", "script"]` (`artifact_tools.py:235`). `PLANNER_SYSTEM_PROMPT` учит только два kind (`sessions.py:87-89`). `compute_tags` не знает pipeline (`config.py:139-165`).

Переиспользовать `run_script` / `_run_agent_core`, sandbox не менять (ADR-0018).

## Затрагиваемые файлы
- `backend/catalog/skills/config.py` — `PipelineStep`, поле `steps`, serialize, `compute_tags`.
- `backend/catalog/skills/apply.py` — ветка `kind == "pipeline"`: линейный цикл, verify на финале, step_id в событиях/trace.
- `backend/catalog/skills/script_runner.py` — `_extract_result` / `_call_main`: `list[str]`.
- `backend/catalog/skills/artifact_tools.py` — `save_skill_steps`, `kind=pipeline` в meta.
- `backend/catalog/api/sessions.py` — `PLANNER_SYSTEM_PROMPT`.
- `backend/catalog/api/skills.py` — сборка скила из артефактов (meta+steps+script/prompt).
- `backend/tests/test_api.py` — `test_compute_tags_*`; сквозной pipeline; старый конфиг; падение шага.
- `backend/tests/test_session_artifacts.py` / `test_apply.py` — тул и apply.

## План действий
1. Датакласс шага + `steps: list` в `SkillConfig`; отсутствие ключа = `[]`; старый JSON без `kind` остаётся agent.
2. `compute_tags`: pipeline → оба тега (или по составу шагов: есть script → python, есть llm → ai; для чистого pipeline оба).
3. `_apply_core`: для каждого шага взять вход (исходные документы / выход предыдущего), выполнить script или llm, записать trace с `step_id`. На ошибке шага — стоп, run failed. Verify один раз на финале.
4. `_extract_result`: если `result`/`main` вернул `list` и все элементы `str` — вернуть список (тип возврата расширить; apply умеет кормить следующий шаг).
5. `save_skill_steps` + валидация шагов; `set_skill_meta` принимает `pipeline`; для pipeline `allowed_tools` на шаге, не в meta (как у script — пустой верхний список).
6. Промпт планировщика: третий kind, порядок `set_skill_meta` → `save_skill_steps` (+ script/prompt по шагам).
7. Тесты как в DoD. Не коммитить `backend/catalog/static/`.

## Критерии приёмки (Definition of Done)
- [ ] Старый `config_json` без `kind`/`steps` десериализуется как agent с пустыми steps.
- [ ] Сквозной `script → llm → script` зелёный; падение среднего шага останавливает пайплайн и помечает run failed.
- [ ] `_extract_result` принимает список строк.
- [ ] События/trace содержат id шага.
- [ ] `save_skill_steps` пишет валидный артефакт; `set_skill_meta(kind=pipeline)` проходит.
- [ ] `compute_tags(pipeline)` содержит `python` и `ai`.
- [ ] Зелёные: `ruff check .`, `pytest` из `backend/`.
- [ ] `backend/catalog/static/` не в коммите.
