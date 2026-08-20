# CATALOG-145 — code: рантайм и персист именованных выходов (script и pipeline)

- **Задача Plane:** [CATALOG-145](https://app.plane.so/belchch/projects/catalog-app/work-items/145) (id: `125b5baf-dce9-4382-80e4-c92d1b289d10`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 02 · blocked_by CATALOG-143 · blocked_by CATALOG-144 · blocking CATALOG-147 · blocking CATALOG-146
- **Цель:** Принять `dict[str, str]` на финале script/pipeline, сверить с `SkillConfig.outputs` и персистить primary + companions. Agent/`emit_output` и UI не трогать.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. Порядок: после декларации выходов, до UI.

`_extract_result` (`script_runner.py:346-369`) знает `str` и `list[str]`; словарь падает в `str(result)` → мусор `" {'text': ...} "`. Хвост персиста (`apply.py:999-1039`) пишет один файл и один `Document`. `save_run_result_endpoint` (`runs.py:133-187`) материализует один и отдаёт 409, если `output_doc_id` уже есть. На `skill_run` нет места под набор (`schema.py:97-107`).

Режим «на экран» (`persist=False`) держит результат в `result_text` — companions туда не помещаются.

Что сделать:

1. `_extract_result` распознаёт `dict[str, str]` (глобал `result` и `return` из `main()`). Тип `run_script` расширяется.
2. dict — только финал top-level script и последний шаг pipeline. На промежуточном шаге — `PipelineStepError`. `_value_as_text` / `_value_as_documents` dict не принимают.
3. Ключи возврата = `SkillConfig.outputs`. Незнакомый / пропущенный / пустой / сверх лимита — `failed` + трейс. Скилл без декларации, вернувший dict, — тоже ошибка.
4. Persist: primary как сейчас (`result_text`, `output_doc_id`, wiki-links на входы). Companions — отдельные `Document(kind="result_md")` в `results/`, заголовок `{скилл} — {описание выхода}`. Взаимные wiki-links между артефактами прогона. Все — к сессии, если есть.
5. Схема: `skill_run.result_artifacts` (JSON ключ→текст) и `skill_run.output_doc_ids` (JSON-массив, primary включён) через `ADDITIVE_MIGRATIONS`. `result_text` остаётся копией primary.
6. `persist=False`: артефакты в `result_artifacts`. `POST /runs/{id}/save` пишет всю пачку атомарно, ответ — primary `DocumentOut`. 409 по `output_doc_id` как есть.
7. `RunOut` и WS `finish` несут `output_doc_ids` и список артефактов. Старые поля на месте.
8. Skill-as-tool: рядом с `text` добавить `outputs`. Документов нет; в шаг pipeline идёт только primary.
9. Verify — на primary.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

Предусловия: `CATALOG-143` (политика), `CATALOG-144` (`SkillConfig.outputs`). Agent — `CATALOG-147`; UI — `CATALOG-146`.

- `backend/catalog/skills/script_runner.py:346-369` — `_extract_result`: list/str, иначе `str(result)`. `run_script` / `run_skill_script_async` (`410+`, `519+`) типизированы как `str | list[str]`.
- `backend/catalog/skills/apply.py:79` — `PipelineValue = str | list[str]`.
- `backend/catalog/skills/apply.py:104-115` — `_value_as_text` / `_value_as_documents` dict не ждут.
- `backend/catalog/skills/apply.py:415-458` — top-level script сразу склеивает list в текст (`429-431`); dict сюда не доедет осмысленно.
- `backend/catalog/skills/apply.py:483-545` — pipeline script-шаг кладёт возврат в `current`; промежуточный dict должен падать здесь, не в хвосте.
- `backend/catalog/skills/apply.py:82-83` — `PipelineStepError`.
- `backend/catalog/skills/apply.py:999-1049` — persist одного файла; `finish_run` пишет `output_doc_id` + `result_text`.
- `backend/catalog/skills/repo_run.py:42-115` — `create_run` / `finish_run` / `set_output_doc_id` без колонок набора.
- `backend/catalog/storage/schema.py:97-107, 142-171` — `ADDITIVE_MIGRATIONS` (прецедент: `input_doc_ids`).
- `backend/catalog/api/runs.py:110-187, 330-336` — `GET /runs/{id}`, `POST /runs/{id}/save`, WS `finish`.
- `backend/catalog/api/schemas.py:128-141` — `RunOut`.
- `backend/catalog/skills/skill_tools.py:343-353` — ответ тула: `text=result.result_text`.

Тесты-якоря: `backend/tests/test_apply.py` (persist/preview/save), `backend/tests/test_storage.py` (миграции).

## Затрагиваемые файлы
- `backend/catalog/skills/script_runner.py` — распознать dict, расширить тип возврата.
- `backend/catalog/skills/apply.py` — граница финала, сверка ключей, persist пачки, взаимные wiki-links.
- `backend/catalog/skills/repo_run.py` — чтение/запись `result_artifacts` и `output_doc_ids`.
- `backend/catalog/storage/schema.py` — две additive-колонки.
- `backend/catalog/api/schemas.py` / `backend/catalog/api/runs.py` — `RunOut`, save всей пачки, WS `finish`.
- `backend/catalog/skills/skill_tools.py` — поле `outputs` в ответе тула.
- `backend/tests/test_apply.py`, `backend/tests/test_storage.py` — сценарии из DoD.

## План действий
1. `_extract_result`: если значение — `dict` и все ключи/значения `str` — вернуть его; смешанный dict — ошибка, не `str(dict)`.
2. Расширить тип `run_script` / `run_skill_script_async` до `str | list[str] | dict[str, str]`.
3. В apply: на промежуточном pipeline-шаге dict → `PipelineStepError`. На финале (top-level script или последний шаг) — сверка с `skill.outputs`.
4. Сверка: точное совпадение ключей; пустое значение / лишний / пропущенный / dict без декларации → `failed` + запись в трейс. Primary = `outputs[0]`.
5. Additive-колонки `result_artifacts` и `output_doc_ids`; `finish_run` их пишет; старые строки читаются как пустые.
6. Persist-хвост: primary — как сейчас; companions — отдельные `result_md`; взаимные wiki-links + ссылки на входы; attach всех к сессии. `result_text` = primary.
7. `persist=False`: документы не создавать, пачку класть в `result_artifacts`. Save — вся пачка атомарно, 409 если `output_doc_id` уже есть.
8. `RunOut` + WS `finish` + skill-as-tool: новые поля рядом со старыми; в шаг pipeline по-прежнему только primary.
9. Verify без изменений — на primary-тексте.
10. Тесты: два выхода persist/preview/save; промежуточный dict; ошибки ключей; legacy-скилл; миграция; wiki-links; golden_run.

## Критерии приёмки (Definition of Done)
- [ ] Script-скилл с двумя объявленными выходами, возвращающий dict, в режиме «в док» даёт два документа; `output_doc_id` указывает на primary, `output_doc_ids` — на оба.
- [ ] Тот же скилл в режиме «на экран» документов не создаёт, а `POST /runs/{id}/save` потом создаёт оба.
- [ ] Pipeline, у которого dict возвращает не последний шаг, падает с понятной ошибкой, а не молча теряет артефакты.
- [ ] Незнакомый ключ, пропущенный ключ и пустое значение дают `failed` с причиной в трейсе.
- [ ] Старые скиллы (возврат строки, пустой `outputs`) работают без изменений — один документ, те же поля.
- [ ] Миграция применяется к существующей базе без потери данных; старые строки `skill_run` читаются.
- [ ] Артефакты одного прогона ссылаются друг на друга; ссылки на входные документы не потеряны.
- [ ] Backend: `ruff check .`, `pytest` зелёные; `python scripts/golden_run.py` проходит.
