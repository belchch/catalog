# CATALOG-143 — ADR-0024: именованные выходы скилла — primary + companions

- **Задача Plane:** [CATALOG-143](https://app.plane.so/belchch/projects/catalog-app/work-items/143) (id: `95bd2da0-506a-451f-ac06-98c9889ae5f2`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 00 · blocking CATALOG-144 · blocking CATALOG-145 · blocking CATALOG-147 · blocking CATALOG-146
- **Цель:** Принять ADR-0024: скилл объявляет именованные выходы (primary + companions), общий контракт для `agent` / `script` / `pipeline`. Только документ.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code (только документ). Первый шаг, блокирует остальные — политика, на которую они опираются. Охват — все три `kind` сразу.

Сегодня один прогон = один `result_text` = один `output_doc_id` = один `result_md`. Хвост персиста (`apply.py:999-1039`) пишет ровно один файл и одну строку `Document`; `save_run_result_endpoint` (`runs.py:133-187`) материализует ровно один. Входы уже множественные (`input_doc_ids`), выходы — нет.

Контракт значения pipeline несёт `str | list[str]` (ADR-0018), но `_value_as_text` (`apply.py:104-109`) склеивает список в один текст через `---`. Это заготовка под будущий `map`, а не под N документов: позиция в списке не несёт роли.

Пример из CATALOG-142 — псевдонимизация: псевдонимизированный текст и таблица перекодировки. Это два документа с разными ролями, а не «глава 1 / глава 2».

Зафиксировать в ADR:

1. Декларация выходов в замороженном конфиге. `SkillConfig.outputs` — список `{key, description}`, общий для всех трёх `kind`. Прецедент: `input_arity` (`runs.py:80-88`). Пустой `outputs` = сегодняшнее поведение; старые `config_json` без миграции.
2. Primary = `outputs[0]`. Порядок заморожен вместе со скиллом. Primary идёт в `result_text`, verify, значение следующего шага и ответ skill-as-tool; `output_doc_id` указывает на него.
3. Companions — остальные ключи. Персистятся как отдельные `Document(kind="result_md")` в `results/`. Новый `result_*` kind не вводится.
4. Набор именованных значений — только на финале top-level прогона (или последнем шаге pipeline). Между шагами значение остаётся `str | list[str]`; `dict` в середине — ошибка, fail-closed. `list[str]` — одно значение, не N документов.
5. Как рождается набор — зависит от `kind`, контракт один. `script` — sandbox возвращает `dict[str, str]`. `pipeline` — финальный шаг по своему типу. `agent` — тул `emit_output(key, text)`. Разбор простыни по разделителям отклонён.
6. Неполный набор у `agent` — через существующий retry (ADR-0007). У `script` сразу ошибка.
7. Вложенный apply не меняется (ADR-0019 / ADR-0022): `persist=False`, companions не документы и не значение шага. В ответ session-тула допустимо поле `outputs` рядом с `text`.
8. Verify на primary. ADR-0007 не трогаем. Адресация verify на конкретный артефакт — отложена.
9. Fail-closed по форме: лимит 8; ключ `^[a-z][a-z0-9_]{0,31}$`; пустое значение, незнакомый ключ, пропущенный ключ, превышение лимита — ошибка прогона.
10. Описания: для `script` — артефакт сборки (в рантайме сверяются только ключи); для `agent` и llm-шага — ещё в промпт и схему тула.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

Один выход зашит в персист и контракт:

- `backend/catalog/skills/apply.py:104-109` — `_value_as_text` склеивает `list[str]` через `---`.
- `backend/catalog/skills/apply.py:999-1039` — хвост пишет один файл и один `Document(kind="result_md")`.
- `backend/catalog/api/runs.py:80-88` — `input_arity` уже объявляет ожидание по входам (прецедент для `outputs`).
- `backend/catalog/api/runs.py:133-187` — `POST /runs/{id}/save` материализует один `result_text`.
- `backend/catalog/skills/config.py:147-217` — `SkillConfig` без поля `outputs`; `to_json` / `from_json` уже умеют дефолтить отсутствующие ключи (`kind`, `input_arity`).
- `backend/catalog/storage/schema.py:97-107` — на `skill_run` есть `output_doc_id` и `result_text`, места под набор нет.
- `docs/adr/0006-results-are-documents.md` — результат = `Document`; `docs/adr/0014-script-skills.md` — sandbox без LLM; `docs/adr/0018-pipeline-skills.md` — контракт `str | list[str]`; `docs/adr/0019-skill-as-session-tool.md` и `docs/adr/0022-pipeline-skill-step.md` — вложенный apply с `persist=False`; `docs/adr/0007-verify-deterministic-registry.md` — verify на одном тексте.
- `docs/adr/README.md` — индекс до 0023.

Следующие шаги: `CATALOG-144` (декларация), `CATALOG-145` (рантайм script/pipeline), `CATALOG-147` (agent `emit_output`), `CATALOG-146` (UI).

## Затрагиваемые файлы
- `docs/adr/0024-named-skill-outputs.md` — новый ADR, статус Accepted, Extends ADR-0006 / ADR-0014 / ADR-0018; явно: ADR-0019 / ADR-0022 не меняются.
- `docs/adr/README.md` — строка в индексе.

## План действий
1. Написать ADR по шаблону существующих (Context → Decision → Consequences → Alternatives considered).
2. Decision закрывает десять пунктов ТЗ: декларация, primary, companions, граница финала, рождение набора по `kind`, retry для agent, вложенный apply, verify на primary, fail-closed по форме, где живут описания.
3. Alternatives considered — пять отклонённых вариантов из ТЗ: persist `list[str]` как N документов; скилл сам пишет файлы тулом; конвенция ключей без декларации; разбор ответа модели по разделителям; требование JSON в финальном сообщении.
4. Consequences честно фиксирует минусы: companions вложенного вызова не всплывают; у `agent` многовыходной прогон дороже по итерациям и может упереться в `max_iterations`.
5. Обновить индекс.

## Критерии приёмки (Definition of Done)
- [ ] `docs/adr/0024-named-skill-outputs.md` создан, статус Accepted, заголовок ссылается на Extends ADR-0006 / ADR-0014 / ADR-0018 и явно отмечает, что ADR-0019 / ADR-0022 не меняются.
- [ ] Alternatives considered содержит пять отклонённых вариантов из ТЗ.
- [ ] Consequences честно перечисляет минусы: companions вложенного вызова не всплывают; у `agent` многовыходной прогон дороже и может упереться в `max_iterations`.
- [ ] `docs/adr/README.md` обновлён.
