# CATALOG-159 — Сборка скила по треку теряет выходы из черновика — модалка настройки открывается пустой

- **Задача Plane:** [CATALOG-159](https://app.plane.so/belchch/projects/84997489-c485-4448-9ebe-0a06c4fa3cbc/issues/f75cded1-7829-4aa7-92cf-6fb3d0297ad3) (id: `f75cded1-7829-4aa7-92cf-6fb3d0297ad3`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 01 · независимый
- **Цель:** На LLM-ветке сборки скилла (`force_llm` из-за выбранного трека) переносить валидный артефакт `outputs` сессии в `config.outputs`, не теряя черновик. Модалка настройки перестанет открываться с пустым блоком «Выход».

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

**Симптом.** В черновике скилла заданы и сохранены выходы. «Собрать скил» открывает модалку «Настройка скила» с пустым блоком «Выход»: «Выходов нет — прогон даёт один документ.». Если не заметить — скилл коммитится с одним выходом.

**Воспроизведение.** Новая сессия планировщика → заполнить мета + промпт → в блоке «Выход» сохранить 1–2 выхода (`outputs` валиден) → «Собрать скил» → выбрать трек → модалка без выходов.

Проверено на бэкенде: `POST /sessions/{id}/skills` после `POST /sessions/{id}/skill-tracks/select` возвращает `config.outputs == []` при живом артефакте `outputs`. Без трека (сборка из артефактов) выходы доезжают. Баг в LLM-ветке. Фронтенд ни при чём — модалка честно рисует пустой `preview.outputs`.

**Причина** (`backend/catalog/api/skills.py`):

- `build_skill_from_session()` ставит `force_llm = _has_track_intent(...) and not _session_has_pipeline_draft(...)`. При треке и не-pipeline `_build_skill_from_artifacts` пропускается целиком — вместе с чтением `outputs`.
- `_build_skill_from_session_llm` собирает конфиг только из аргументов `build_skill`. В `_BUILD_SKILL_PARAMETERS` поля `outputs` нет → `_args_to_config` всегда видит `args.get("outputs") is None` → `outputs=[]`.

**Что сделать**

1. В LLM-ветке переносить артефакт `outputs` в конфиг так же, как `_build_skill_from_artifacts` (включая 422 на невалидный артефакт). Выходы — структура от пользователя, не доменный текст, ради которого трек отбрасывает черновик.
2. Добавить `outputs` в `_BUILD_SKILL_PARAMETERS`, чтобы модель могла предложить выходы, когда артефакта нет. При конфликте приоритет у артефакта пользователя.

**Критерии из ТЗ** — см. Definition of Done ниже.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

Сборка развилкается в [backend/catalog/api/skills.py:823](backend/catalog/api/skills.py:823):

```text
force_llm = track_intent ∧ ¬pipeline_draft
если не force_llm → _build_skill_from_artifacts (читает outputs)
иначе            → _build_skill_from_session_llm (читает только tool args)
```

`_build_skill_from_artifacts` уже умеет выходы — [skills.py:624-639](backend/catalog/api/skills.py:624): нет артефакта → `[]`; `not is_valid` → 422 `outputs are invalid: …`; ошибки `parse_skill_outputs` → 422 `outputs artifact is invalid: …`; иначе `args["outputs"] = [skill_output_to_dict(item) for item in parsed]`.

`_args_to_config` уже принимает `outputs` — [skills.py:387](backend/catalog/api/skills.py:387): `outputs=skill_outputs_from_value(args.get("outputs"))`. Схема тула `_BUILD_SKILL_PARAMETERS` ([skills.py:210-268](backend/catalog/api/skills.py:210)) поля не объявляет, поэтому LLM его не передаёт.

Регрессия, которую нельзя сломать: [backend/tests/test_skill_tracks.py:313](backend/tests/test_skill_tracks.py:313) `test_build_with_track_intent_skips_artifact_pack` — трек не тащит доменные `name` / `description` / `system_prompt` из черновика. Выходы в этот запрет не входят.

Сохранение черновика: `PATCH /sessions/{id}/artifacts/outputs` ([backend/catalog/api/sessions.py:673](backend/catalog/api/sessions.py:673), тесты в [backend/tests/test_session_artifacts.py](backend/tests/test_session_artifacts.py)). Форма элемента — `SkillOutput` (`key`, `description`, `multiple`) в [backend/catalog/skills/config.py:27](backend/catalog/skills/config.py:27).

Фронтенд и модалку не трогаем: пустой блок — следствие пустого `config.outputs`.

## Затрагиваемые файлы

| Файл | Что делаем |
| --- | --- |
| [backend/catalog/api/skills.py](backend/catalog/api/skills.py) | вынести чтение `outputs` в общую функцию; вызвать её из LLM-ветки (артефакт бьёт tool args); добавить `outputs` в `_BUILD_SKILL_PARAMETERS` |
| [backend/tests/test_skill_tracks.py](backend/tests/test_skill_tracks.py) | три теста из DoD + убедиться, что `test_build_with_track_intent_skips_artifact_pack` зелёный |

Новых файлов не нужно. Frontend не меняем.

## План действий

1. Вынести чтение артефакта `outputs` из `_build_skill_from_artifacts` (строки 624–639) в одну функцию, например `_session_outputs_args(db, session_id) -> list[dict] | None`:
   - нет артефакта → `None` (не `[]`: пустой список — валидный сохранённый черновик «выходов нет», его нельзя спутать с отсутствием);
   - невалидный / `parse_skill_outputs` с ошибками → тот же 422, те же тексты;
   - валидный → список словарей через `skill_output_to_dict` (порядок как в артефакте, первый = основной, `multiple` сохраняется).
2. В `_build_skill_from_artifacts` заменить локальный блок вызовом этой функции: `None` → `args["outputs"] = []`, иначе подставить список.
3. В `_build_skill_from_session_llm` после успешного `_args_to_config(tc.arguments, …)`:
   - если функция вернула список — подменить `config.outputs` (через повторный `_args_to_config` с подмешанным `outputs` или прямым присвоением эквивалентного `list[SkillOutput]`);
   - если `None` — оставить то, что пришло из tool args (пусто или предложение модели).
4. Добавить в `_BUILD_SKILL_PARAMETERS["properties"]` поле `outputs`: массив объектов `{key, description, multiple?}` в тех же ограничениях, что `parse_skill_outputs` (`key` / длина / `MAX_SKILL_OUTPUTS`). Не делать поле required.
5. Тесты в `test_skill_tracks.py` по сценарию «мета + промпт + `PATCH …/artifacts/outputs` + `skill-tracks/select` + мок `build_skill` без `outputs`»:
   - валидный артефакт с `multiple: true` → 200, `config.outputs` равен черновику, порядок сохранён;
   - невалидный артефакт → 422, текст как на пути артефактов;
   - артефакта нет, мок без `outputs` → `config.outputs == []`; отдельный случай: артефакта нет, мок с `outputs` → конфиг берёт предложение модели.
6. Не расширять `test_build_with_track_intent_skips_artifact_pack` доменными полями — он должен остаться зелёным без правок, кроме необходимости.
7. Прогнать шесть команд из [CLAUDE.md](CLAUDE.md).

## Критерии приёмки (Definition of Done)

- [ ] Сессия с валидным артефактом `outputs` (в т.ч. с `multiple: true`) + выбранный трек → `POST /sessions/{id}/skills` возвращает `config.outputs`, равный черновику, порядок сохранён (первый = основной).
- [ ] Тот же сценарий с невалидным артефактом `outputs` → 422 с тем же текстом, что на пути сборки из артефактов.
- [ ] Сессия без артефакта `outputs` и с треком → поведение как раньше: пусто либо то, что предложила модель.
- [ ] `tests/test_skill_tracks.py`, включая `test_build_with_track_intent_skips_artifact_pack`, зелёные: трек по-прежнему не тащит доменные `name` / `description` / `system_prompt` из черновика.
- [ ] Backend: `ruff check .`, `pytest`; Frontend: `pnpm run build`, `lint`, `typecheck`, `test` — зелёные.
