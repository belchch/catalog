# CATALOG-153 — code: коллекционные выходы — декларация, рантайм, персист

- **Задача Plane:** [CATALOG-153](https://app.plane.so/belchch/projects/84997489-c485-4448-9ebe-0a06c4fa3cbc/issues/0875da57-8fdf-45d4-bef2-77164d7c4f6a) (id: `0875da57-8fdf-45d4-bef2-77164d7c4f6a`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 01 · предусловие: 00 (ADR-0025, CATALOG-152) · блокирует 02 (ui, CATALOG-154)
- **Цель:** Провести флаг `multiple` через декларацию, рантайм и персист: `artifacts` становится `dict[str, str | list[str]]`, коллекционный ключ разворачивается в N документов, сверка с декларацией проверяет тип, число документов за прогон ограничено отдельным лимитом.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. Порядок: после ADR-0025, до UI.

**Контекст.** После CATALOG-145 хвост персиста уже умеет писать N документов за прогон: `_persist_outputs` (`skills/apply.py:231-307`) работает со списком `items: list[tuple[key, title, text]]`, разводит имена через `allocate_rel_path`, проставляет взаимные wiki-links через `sibling_stems` и катит всё одной транзакцией с откатом файлов. **Это не надо переписывать** — туда просто приходит больше `items`.

Узкое место выше: `artifacts` везде типизован как `dict[str, str]`, а `_value_as_text` (`apply.py:102-109`) склеивает `list[str]` в один текст до того, как список дойдёт до персиста.

**Что сделать:**

1. **Декларация.** `SkillOutput` (`skills/config.py:22-26`) получает `multiple: bool = False`; `skill_output_to_dict` (`:28-30`) и `parse_skill_outputs` (`:32-77`) его сериализуют и валидируют (только bool; отсутствие = `false`). Round-trip `to_json`/`from_json` (`:283-284`, `:319`).
2. **Тип значения.** `artifacts` становится `dict[str, str | list[str]]` по всей цепочке. `_coerce_script_value` / `_extract_result` (`skills/script_runner.py:346-386`) принимают словарь со смешанными значениями.
3. **Сверка с декларацией поключевая.** `_match_named_outputs` (`apply.py:120-144`) теперь сверяет не только набор ключей, но и тип: `multiple` требует непустой `list[str]` без пустых элементов, обычный — непустой `str`. Сообщения в том же стиле, что сейчас (`unknown / missing / empty output key(s)`), плюс новое про тип.
4. **Лимит документов.** Новая константа рядом с `MAX_SKILL_OUTPUTS` (`config.py:19`). Проверяется по сумме элементов всех выходов **до** записи файлов — чтобы не откатывать половину записанного. Превышение — `failed` с причиной в трейсе, не усечение.
5. **Persist.** `_persist_outputs`: коллекционный ключ разворачивается в N `items`. Заголовок элемента — по правилу из ADR-0025 (первый markdown-заголовок, иначе позиция). Взаимные wiki-links и атомарность — как есть.
6. **Хранение.** `skill_run.result_artifacts` (`storage/schema.py:105`) — уже TEXT с JSON, миграция **не нужна**: меняется только форма значения (строка или массив). Обновить комментарий в схеме. `output_doc_ids` — без изменений.
7. **`emit_output` для agent** (`skills/emit_output.py`). `uses_emit_output` (`:10`) сейчас `len(outputs) > 1` — становится «> 1 **или** есть коллекционный»: скилл с одним коллекционным выходом тоже обязан звать тул. `register_emit_output` (`:81-92`): для `multiple`-ключа **append** вместо `sink[key] = text`; в ответе тула возвращать текущее число элементов, чтобы модель видела прогресс. `named_output_failures` (`:25-40`): коллекционный ключ с нулём элементов = missing. `named_outputs_prompt` (`:14-22`) и `emit_output_spec` (`:53-78`) объясняют, что коллекционный ключ зовётся много раз. `enum` по-прежнему из декларации.
8. **Бюджет agent.** 30 глав = 30 вызовов тула = 30 итераций. Проверить, что упор в `max_iterations` даёт внятный `capped` с числом уже набранных элементов, а не молчаливую потерю. Это главная практическая причина делать такие скиллы `script`, а не `agent` — отразить в промпте планировщика.
9. **Контракты наружу.** `RunOut` (`api/schemas.py`) и WS-кадр `finish` отдают артефакты в новой форме. `POST /runs/{id}/save` пишет всю пачку, как и сейчас. Skill-as-tool: в поле `outputs` коллекция едет массивом; `text` (primary) — по правилу из ADR-0025.
10. **Dry-run.** `_try_payload` (`skills/artifact_tools.py:252-266`) честно показывает коллекцию в `output_kind` и число элементов — иначе планировщик не увидит разбивку до сборки.
11. **Промпт планировщика.** Когда выход коллекционный («число зависит от входа»), а когда это разные роли («текст + таблица»). Для `script` — возвращать список по коллекционному ключу.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

**Предусловие.** Политика этого шага целиком задана ADR-0025 (план `00-CATALOG-152-…`). Три места читают ADR как источник правды и **не решают заново**: правило заголовка элемента (п. 5), допустимость `multiple` на `outputs[0]` (влияет на `result_text`), решение по wiki-links между элементами коллекции.

**Фактическое состояние кода на ветке прогона** (проверено, номера строк актуальны):

- `MAX_SKILL_OUTPUTS = 8` — [config.py:19](backend/catalog/skills/config.py:19); `SkillOutput` (`key`, `description`) — [config.py:23](backend/catalog/skills/config.py:23); `skill_output_to_dict` — [config.py:28](backend/catalog/skills/config.py:28); `parse_skill_outputs` — [config.py:32](backend/catalog/skills/config.py:32); `skill_outputs_from_value` — [config.py:79](backend/catalog/skills/config.py:79); `to_json` — [config.py:259](backend/catalog/skills/config.py:259); `from_json` — [config.py:288](backend/catalog/skills/config.py:288).
- `_value_as_text` — [apply.py:102](backend/catalog/skills/apply.py:102): на `list[str]` длины 1 возвращает элемент, иначе join через `\n\n---\n\n`. Рядом уже есть `_value_as_documents` — [apply.py:112](backend/catalog/skills/apply.py:112), которая разворачивает список в `list[str]`; она пригодится как готовый кирпич.
- `_match_named_outputs` — [apply.py:120](backend/catalog/skills/apply.py:120): сигнатура `(skill, value: dict[str, str]) -> dict[str, str]`, проверяет `unknown` / `missing` / `empty` только по строкам (`(value.get(key) or "").strip()`), лимит сверяет с `MAX_SKILL_OUTPUTS`.
- `_finalize_script_result` — [apply.py:147](backend/catalog/skills/apply.py:147): возвращает `(primary_text, artifacts)`, primary берётся как `artifacts[skill.outputs[0].key]` — на коллекции это станет списком, здесь и нужен `_value_as_text`.
- `_output_persist_keys` — [apply.py:188](backend/catalog/skills/apply.py:188) и `_ordered_artifacts` — [apply.py:202](backend/catalog/skills/apply.py:202): обе сравнивают значения со строкой (`artifacts[key] == primary_text`) — на списках это сломается молча, надо пройти обе.
- `persist_run_outputs` — [apply.py:226](backend/catalog/skills/apply.py:226) (в ТЗ названа `_persist_outputs`; фактическое имя — публичное `persist_run_outputs`). Строит `items`, затем `allocated` → `stems` → взаимные `sibling_stems` → одна транзакция, `except` удаляет уже созданные файлы. **Точка расширения — только формирование `items`**; ниже по коду ничего менять не нужно.
- `ScriptResult = str | list[str] | dict[str, str]` — [script_runner.py:340](backend/catalog/skills/script_runner.py:340); `_as_str_dict` — [script_runner.py:349](backend/catalog/skills/script_runner.py:349) сейчас **бросает** `ScriptRuntimeError`, если значение словаря не `str` — это ровно то место, где список сегодня отвергается.
- `emit_output.py`: `uses_emit_output` — [emit_output.py:10](backend/catalog/skills/emit_output.py:10) (`len(outputs) > 1`); `named_outputs_prompt` — [:14](backend/catalog/skills/emit_output.py:14); `named_output_failures` — [:25](backend/catalog/skills/emit_output.py:25); `primary_output_text` — [:42](backend/catalog/skills/emit_output.py:42); `emit_output_spec` — [:53](backend/catalog/skills/emit_output.py:53); `register_emit_output` — [:81](backend/catalog/skills/emit_output.py:81), внутри `sink[key] = text`.
- `_named_outputs_required` — [apply.py:171](backend/catalog/skills/apply.py:171): для `agent` и для llm/skill-шага pipeline опирается на `uses_emit_output`, поэтому правка п. 7 автоматически меняет и это.
- Схема: `result_artifacts TEXT, -- JSON object key→text (CATALOG-145)` — [storage/schema.py:105](backend/catalog/storage/schema.py:105); `output_doc_ids` — [schema.py:106](backend/catalog/storage/schema.py:106).
- Dry-run: `_try_payload` — [artifact_tools.py:252](backend/catalog/skills/artifact_tools.py:252), поле `output_kind` уже есть.
- Промпты планировщика: [api/skills.py:1035](backend/catalog/api/skills.py:1035) («Именованные выходы — set_skill_outputs.»), [api/sessions.py:126](backend/catalog/api/sessions.py:126) (описание `set_skill_outputs`); сам тул — [artifact_tools.py:786](backend/catalog/skills/artifact_tools.py:786), спека — [artifact_tools.py:990](backend/catalog/skills/artifact_tools.py:990).

**Главный риск шага — молчаливая деградация на `list`.** Несколько мест сравнивают значение артефакта со строкой или зовут `.strip()`. Если пропустить хоть одно, коллекция не упадёт с ошибкой, а тихо уедет не туда (например, primary не найдётся в `_output_persist_keys` и порядок документов поедет). Поэтому проверка типов и тесты на регресс важнее, чем сама фича.

**Регресс — жёсткое требование.** Скиллы без `multiple` должны работать бит-в-бит как до. Отдельно: скилл с **пустым** `outputs`, вернувший `list[str]`, по-прежнему даёт **один склеенный** документ — поведение меняется только при явной декларации `multiple`.

## Затрагиваемые файлы

| Файл | Что делаем |
| --- | --- |
| [backend/catalog/skills/config.py](backend/catalog/skills/config.py) | `SkillOutput.multiple`; сериализация и валидация; новая константа лимита документов |
| [backend/catalog/skills/apply.py](backend/catalog/skills/apply.py) | типы `artifacts`; `_match_named_outputs` с проверкой типа; `_finalize_script_result`; `_output_persist_keys`; `_ordered_artifacts`; разворот коллекции в `items` в `persist_run_outputs`; проверка лимита документов до записи файлов; заголовок элемента |
| [backend/catalog/skills/script_runner.py](backend/catalog/skills/script_runner.py) | `ScriptResult`; `_as_str_dict` → допускает `str \| list[str]`; `_coerce_script_value` / `_extract_result` |
| [backend/catalog/skills/emit_output.py](backend/catalog/skills/emit_output.py) | `uses_emit_output`; накопление в `register_emit_output`; `named_output_failures`; `named_outputs_prompt`; `emit_output_spec`; `primary_output_text` |
| [backend/catalog/storage/schema.py](backend/catalog/storage/schema.py) | комментарий у `result_artifacts` (миграции нет) |
| [backend/catalog/api/schemas.py](backend/catalog/api/schemas.py) | форма артефактов в `RunOut` |
| [backend/catalog/api/runs.py](backend/catalog/api/runs.py) | WS-кадр `finish`; `POST /runs/{id}/save` на пачке |
| [backend/catalog/skills/artifact_tools.py](backend/catalog/skills/artifact_tools.py) | `_try_payload`: `output_kind` + число элементов; спека и обработчик `set_skill_outputs` принимают `multiple` |
| [backend/catalog/api/skills.py](backend/catalog/api/skills.py), [backend/catalog/api/sessions.py](backend/catalog/api/sessions.py) | промпт планировщика: когда коллекция, когда роли |
| [backend/tests/test_apply.py](backend/tests/test_apply.py), [backend/tests/test_script_runner.py](backend/tests/test_script_runner.py) | новые тесты + защита регресса |

## План действий

1. **Прочитать ADR-0025** и выписать три решения, которые он фиксирует: правило заголовка элемента, допустимость `multiple` на `outputs[0]`, политика wiki-links между элементами. Дальше следовать им буквально.
2. **Декларация.** В [config.py](backend/catalog/skills/config.py): `SkillOutput.multiple: bool = False`; `skill_output_to_dict` пишет ключ **только когда `True`** (чтобы `to_json` старых конфигов не менялся и `config_hash` не поехал на ровном месте); `parse_skill_outputs` принимает `multiple`, требует именно `bool` (не «truthy»), отсутствие = `False`, чужой тип — ошибка в том же стиле, что соседние. Проверить round-trip `to_json`/`from_json`.
3. **Константа лимита документов** рядом с `MAX_SKILL_OUTPUTS` — [config.py:19](backend/catalog/skills/config.py:19); значение из ADR-0025 (предложение — 50).
4. **Типы значения.** Ввести общий алиас (например `ArtifactValue = str | list[str]`) и провести `artifacts: dict[str, ArtifactValue]` по всей цепочке в [apply.py](backend/catalog/skills/apply.py): сигнатуры `_match_named_outputs`, `_finalize_script_result`, `_output_persist_keys`, `_ordered_artifacts`, `persist_run_outputs`, поля `Outcome`/результата и всё, что их зовёт. Опираться на mypy/typecheck-прогон, а не на глаз.
5. **`_match_named_outputs`** — [apply.py:120](backend/catalog/skills/apply.py:120): к текущим `unknown` / `missing` / `empty` добавить поключевую проверку типа по декларации:
   - `multiple=True` → значение обязано быть `list[str]`, непустым, без пустых/пробельных элементов;
   - `multiple=False` → значение обязано быть непустой `str`;
   - несовпадение — новая внятная формулировка в том же стиле («expected list for output key(s): …» / «expected text for output key(s): …»), отдельно от `empty`, чтобы `[]` и «строка вместо списка» давали **разные** причины.
6. **`_finalize_script_result`** — [apply.py:147](backend/catalog/skills/apply.py:147): primary для коллекционного `outputs[0]` считать через `_value_as_text` (склейка), сами `artifacts` оставить в исходной форме со списком.
7. **`_output_persist_keys`** — [apply.py:188](backend/catalog/skills/apply.py:188) и **`_ordered_artifacts`** — [apply.py:202](backend/catalog/skills/apply.py:202): убрать сравнение значения со строкой (`artifacts[key] == primary_text`) — на списке оно всегда ложно. Порядок вести по декларации; fallback для недекларированных ключей сохранить, но сравнивать через `_value_as_text` либо только по ключам.
8. **Лимит документов** — считать сумму: по каждому ключу `len(value)` для коллекции и `1` для строки. Проверять **до** первого `allocate_rel_path` / `dest.touch()` в [persist_run_outputs](backend/catalog/skills/apply.py:226). Превышение → та же ветка отказа, что у прочих ошибок выходов (`_record_outputs_error` — [apply.py:162](backend/catalog/skills/apply.py:162)), прогон `failed`, файлов на диске не остаётся.
9. **Разворот коллекции в `items`** — в [persist_run_outputs](backend/catalog/skills/apply.py:226), только в блоке формирования `items`: коллекционный ключ даёт N кортежей. Заголовок элемента — по ADR-0025: первый markdown-заголовок текста элемента, иначе по позиции. Первый элемент коллекции, если ключ идёт первым в `persist_keys`, наследует `title` прогона (сегодняшняя семантика `index == 0`) — сверить с ADR. Всё, что ниже (`allocated` / `stems` / транзакция / откат), **не трогать**.
10. **wiki-links** — если ADR-0025 решил связывать элементы коллекции только через primary, а не попарно, изменить формирование `sibling_stems` соответствующим образом; если попарно — не трогать вовсе.
11. **script_runner** — [script_runner.py:340](backend/catalog/skills/script_runner.py:340): расширить `ScriptResult` до `str | list[str] | dict[str, str | list[str]]`; в `_as_str_dict` разрешить значение-список из строк (и оставить ошибку для прочих типов, сохранив текст сообщения понятным); `_coerce_script_value` / `_extract_result` — пропускать смешанный словарь.
12. **emit_output** — [emit_output.py](backend/catalog/skills/emit_output.py): `uses_emit_output` = `len(outputs) > 1 or any(o.multiple ...)`; в `register_emit_output` для `multiple`-ключа делать `append` в список (инициализируя его), для обычного — как сейчас, и возвращать в ответе тула текущее число элементов; `named_output_failures` — коллекция с нулём элементов = `missing`, с пустой строкой внутри = `empty`; `primary_output_text` — учесть, что значение может быть списком; тексты `named_outputs_prompt` и `emit_output_spec` объясняют, что коллекционный ключ зовётся многократно (`enum` по-прежнему из декларации).
13. **Бюджет agent** — проверить путь `max_iterations` в apply-цикле: при упоре трейс должен дать `capped` с числом уже набранных элементов коллекции, без молчаливой потери. Если сейчас это не так — поправить сообщение.
14. **Контракты наружу** — `RunOut` в [api/schemas.py](backend/catalog/api/schemas.py) и WS-кадр `finish` в [api/runs.py](backend/catalog/api/runs.py) отдают артефакты в новой форме; `POST /runs/{id}/save` создаёт всю пачку атомарно (сегодняшний код уже идёт через `persist_run_outputs` — убедиться, что так и осталось). Skill-as-tool: `outputs` — массивом, `text` — по правилу ADR-0025.
15. **Схема** — обновить комментарий у `result_artifacts` в [storage/schema.py:105](backend/catalog/storage/schema.py:105): значение — строка **или массив строк**. Миграцию не добавлять.
16. **Dry-run** — [artifact_tools.py:252](backend/catalog/skills/artifact_tools.py:252): `output_kind` различает коллекцию и показывает число элементов.
17. **`set_skill_outputs`** — [artifact_tools.py:786](backend/catalog/skills/artifact_tools.py:786) и его спека [:990](backend/catalog/skills/artifact_tools.py:990): принимать и валидировать `multiple` через тот же `parse_skill_outputs`.
18. **Промпт планировщика** — [api/skills.py:1035](backend/catalog/api/skills.py:1035) и [api/sessions.py:126](backend/catalog/api/sessions.py:126): когда выход коллекционный («число зависит от входа»), когда это разные роли («текст + таблица»); для `script` — возвращать список по коллекционному ключу; отметить, что коллекции дешевле делать `script`, а не `agent` (бюджет итераций).
19. **Тесты** — в [backend/tests/test_apply.py](backend/tests/test_apply.py) и [backend/tests/test_script_runner.py](backend/tests/test_script_runner.py): по одному на каждый пункт приёмки ниже, включая четыре **разных** сообщения об ошибке (`[]`, пустая строка в списке, строка вместо списка, список вместо строки) и явный тест регресса на пустой `outputs` + `list[str]` → один склеенный документ.
20. Прогнать все шесть команд из [CLAUDE.md](CLAUDE.md). `scripts/golden_run.py` **не прогонять** — он требует живой `OPENROUTER_API_KEY`, а боевые ключи в автоматическом прогоне не используются (решение от 2026-08-20).

## Критерии приёмки (Definition of Done)

- [ ] Script-скилл с `[{index}, {chapters, multiple}]` на документе из 7 глав в режиме «в док» создаёт 8 документов; `output_doc_ids` содержит все 8, primary первый.
- [ ] Тот же скилл в режиме «на экран» документов не создаёт, а `POST /runs/{id}/save` потом создаёт все 8 атомарно.
- [ ] Заголовки глав взяты из текста глав, а не «— главы 1..7»; одинаковые заголовки не затирают друг друга на диске.
- [ ] Коллекция на промежуточном шаге pipeline не становится документами — граница из ADR-0018/0024 держится.
- [ ] `[]`, пустая строка в списке, строка вместо списка и список вместо строки дают `failed` с **четырьмя разными** внятными причинами в трейсе.
- [ ] Превышение лимита документов отказывает **до** создания файлов — на диске не остаётся мусора.
- [ ] Agent-скилл с коллекционным выходом накапливает элементы через повторные `emit_output`; пустая коллекция возвращается модели через существующий retry.
- [ ] `uses_emit_output` истинно для скилла с одним коллекционным выходом.
- [ ] Упор в `max_iterations` на коллекции даёт `capped` с числом уже набранных элементов.
- [ ] **Регресс:** скиллы без `multiple` работают бит-в-бит как до; скилл с пустым `outputs`, вернувший `list[str]`, по-прежнему даёт один склеенный документ.
- [ ] `to_json` конфига без коллекционных выходов не изменился — `config_hash` старых скиллов остался прежним.
- [ ] Старые строки `skill_run.result_artifacts` читаются без миграции.
- [ ] Dry-run показывает коллекцию в `output_kind` и число элементов.
- [ ] Промпт планировщика различает коллекцию и роли; `set_skill_outputs` принимает `multiple`.
- [ ] Backend: `ruff check .`, `pytest` — зелёные. (`golden_run.py` исключён из приёмки: требует боевой `OPENROUTER_API_KEY`.)
- [ ] Frontend: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck`, `pnpm run test` — зелёные.
