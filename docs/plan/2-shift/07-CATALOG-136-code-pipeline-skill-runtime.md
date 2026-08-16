# CATALOG-136 — code: рантайм шага skill в pipeline apply — вложенный запуск, verify, бюджет

- **Задача Plane:** [CATALOG-136](https://app.plane.so/belchch/projects/catalog-app/work-items/136) (id: `cceae4df-b495-416b-a26a-67dad7db447a`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 07 · blocked_by CATALOG-135 · blocking CATALOG-137
- **Цель:** Шаг `skill` в `_apply_core` запускает вложенный apply по снапшоту: verify как постусловие, бюджет/дедлайн/глубина, событие в трейсе.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

После схемы и снапшота (CATALOG-135).

1. Ветка `step.type == "skill"` в pipeline-цикле `_apply_core` (`apply.py:416-530`).
2. Переиспользовать `apply_skill_collect` из `skill_tools.py:290-337`: снапшот, `input_texts` из значения шага, `persist=False`, `parent_run_id` текущего прогона (не `"session"`). Без циклического импорта apply ↔ skill_tools.
3. Трейс: `step_id`, `run_id` вложенного, `skill_name`, `config_hash`, `depth` — как CATALOG-119/129.
4. `verify_checks` вложенного — постусловие; провал останавливает пайплайн (как `ScriptRuntimeError`).
5. Бюджет ADR-0021: резерв, `finally` возврат, `nested_skill_hold`, дедлайн; ветки top-level (`budget=None`) и вложенная.
6. `call_context` + `max_skill_depth`; потолок — внятная ошибка.
7. Базовый реестр вложенного — документные тулы текущего прогона (`runs.py:233-235`).

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/2-shift/06-CATALOG-135-code-pipeline-skill-schema.md`.

- `backend/catalog/skills/apply.py:416-537` — pipeline: `script` / `llm` / `else: ValueError(unknown type)`.
- `backend/catalog/skills/skill_tools.py:290-337` — вложенный apply с резервом бюджета, `parent_run_id=SESSION_TOOL_PARENT_RUN_ID`.
- `backend/catalog/skills/budget.py` — `estimate_skill_budget`, `nested_skill_hold`.
- UI трейса ждёт это событие: `docs/plan/2-shift/08-CATALOG-137-ui-pipeline-skill-step.md`.

## Затрагиваемые файлы
- `backend/catalog/skills/apply.py` — ветка `skill`, трейс, verify, бюджет.
- Общая функция вложенного запуска (вынести из `skill_tools.py`, если иначе цикл импорта).
- `backend/tests/test_apply.py` / `test_session_skill_tools.py` — вложенный run, verify-fail, budget, depth, top-level vs nested.

## План действий
1. Вынести общую часть вложенного apply так, чтобы `apply` и `skill_tools` не импортировали друг друга по кругу.
2. Ветка `skill`: вход через `_pipeline_step_input` / `_value_as_text` / `_value_as_documents`; выход — `result_text` как значение шага.
3. `parent_run_id` = id текущего прогона; `persist=False`.
4. Провал verify → стоп пайплайна + `failures` в трейсе.
5. Резерв/возврат бюджета в `finally`; `budget=None` на top-level не падает.
6. Потолок глубины — ошибка шага, не silent skip.
7. Тесты по критериям ТЗ.

## Критерии приёмки (Definition of Done)
- [ ] Прогон создаёт вложенный `skill_run` с `parent_run_id` родителя.
- [ ] Результат вложенного — вход следующего шага (строка или список строк).
- [ ] Провал verify останавливает пайплайн и виден в трейсе.
- [ ] Работает top-level WS и вложенный тул сессии.
- [ ] Бюджет/дедлайн — запись в трейсе, не сырое исключение; резерв возвращается при падении.
- [ ] `max_skill_depth` даёт внятную ошибку шага.
- [ ] `ruff check .`, `pytest` из `backend/`.
