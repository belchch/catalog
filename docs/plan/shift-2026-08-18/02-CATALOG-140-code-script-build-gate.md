# CATALOG-140 — гейт сборки script-скилла — зелёный dry-run по хешу кода

- **Задача Plane:** [CATALOG-140](https://app.plane.so/belchch/projects/catalog-app/work-items/140) (id: `dcedb491-e981-44c2-bf84-9c1d07b7f27e`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 02 · blocked_by CATALOG-139 · blocking CATALOG-141
- **Цель:** Сборка `kind=script` и script-шагов pipeline проходит только при успешном dry-run того же `sha256` кода; статус виден в артефакте и `read_skill_draft`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

ADR-0023, п.4 и п.7. Без гейта тул dry-run остаётся советом, который модель пропускает. Зависит от тула `try_skill_script`.

Хранение статуса прогона. Результат dry-run хранится рядом с артефактом `script` сессии (ADR-0015) и привязан к `sha256` прогнанного кода: хеш, `ok`, `stage`, короткая ошибка, время. Любая правка кода меняет хеш и обнуляет зелёный статус. Статус выдаётся в payload артефакта и в `read_skill_draft`, чтобы планировщик видел, нужен ли прогон.

Гейт сборки. В `_validate_config` / `_build_skill_from_artifacts` (`backend/catalog/api/skills.py`): для `kind="script"` и для каждого script-шага pipeline требуется успешный dry-run для того же хеша кода. Нет — 422 с понятным сообщением (какого именно прогона не хватает) в том же формате ошибок валидации, что и `ScriptValidationError`. Скиллы `kind="agent"` и llm/skill-шаги гейт не затрагивает — для них ADR-0004 без изменений.

Промпты. В `SCRIPT_CODE_CONTRACT_EN` и в `PLANNER_SYSTEM_PROMPT` закрепить порядок: `save_skill_script` → `try_skill_script` → правка до `ok`, и только потом сборка. Указать, что `input_preview` — фактический вход (markdown-таблицы из docx/xlsx), по нему и надо подгонять парсинг, а не по догадкам.

Приёмка.

- Тест: сборка `kind="script"` без dry-run → 422.
- Тест: зелёный dry-run → сборка проходит.
- Тест: зелёный dry-run, затем правка кода → сборка снова 422 (статус привязан к хешу, а не к факту прогона).
- Тест: pipeline с двумя script-шагами, прогнан только один → 422 с указанием шага.
- Тест: сборка `kind="agent"` и pipeline без script-шагов не требует прогона.
- Тест: статус прогона виден в `read_skill_draft` и в payload артефакта.
- Тест на контрактные строки промпта (как существующие проверки `SCRIPT_CODE_CONTRACT_EN`).
- `ruff check .`, `pytest` зелёные.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `01-CATALOG-139-code-try-skill-script.md` (тул + HTTP). UI — `03-CATALOG-141-ui-script-dry-run.md`.

`session_artifact` сейчас: `content`, `is_valid`, `error`, `source`, `updated_at` (`repo_session_artifact.py:14-21`). Колонки под dry-run нет. Не класть статус в `content` скрипта. Варианты: отдельная таблица `session_script_dry_run` (session_id + slot: `script` | `steps:<index>`, sha256, ok, stage, error, time) или JSON-колонка рядом с артефактом. Для pipeline нужны слоты на каждый script-шаг.

`_artifact_payload` (`artifact_tools.py:41`) и `SessionArtifactOut` (`schemas.py:323`) должны начать отдавать статус (поле вроде `dry_run`), чтобы WS `session_artifacts` и HTTP list/patch несли его без отдельного запроса.

`_build_skill_from_artifacts` (`skills.py:449`) и `_validate_config` (`skills.py:383`) — точка гейта. Сейчас script проверяется только `validate_script` (`skills.py:399-403`). 422 уже в том же стиле (`skills.py:462-493`). Agent / pipeline без script-шагов не трогать.

Промпты: `SCRIPT_CODE_CONTRACT_EN` / `_RU` — `script_runner.py:135-147`; `PLANNER_SYSTEM_PROMPT` — `sessions.py:97-116`. Контрактные тесты — `test_script_runner.py:203-210`.

`save_skill_script` / PATCH скрипта меняют `content` → хеш расходится со статусом → зелёный гаснет сам, отдельный reset не обязателен, если сравнение всегда `sha256(current) == stored_hash and ok`.

## Затрагиваемые файлы
- `backend/catalog/storage/repo_session_artifact.py` (+ миграция схемы, если новая таблица/колонка) — хранение статуса по слоту и хешу.
- `backend/catalog/skills/artifact_tools.py` — запись статуса после `try_skill_script`; `_artifact_payload` и `read_skill_draft` отдают статус.
- `backend/catalog/api/schemas.py` — `dry_run` в `SessionArtifactOut` (и в ответе dry-run, если ещё нет).
- `backend/catalog/api/skills.py` — гейт в `_validate_config` / `_build_skill_from_artifacts`.
- `backend/catalog/api/sessions.py` — `PLANNER_SYSTEM_PROMPT`; HTTP dry-run пишет тот же статус.
- `backend/catalog/skills/script_runner.py` — строки контракта.
- `backend/tests/test_session_artifacts.py` / `test_api.py` / `test_script_runner.py` — гейт, хеш, pipeline-шаг, agent без гейта, промпт.

## План действий
1. Хранилище статуса: слот (`script` или `steps:<index>`), `sha256`, `ok`, `stage`, короткая ошибка, время. После успешного/неуспешного dry-run из тула и HTTP — upsert. Чтение в payload артефакта `script` (и steps — список статусов шагов) и в `read_skill_draft`.
2. Зелёный = `ok` и хеш совпадает с текущим кодом слота. Иначе UI/планировщик видят «нет / устарел / ошибка».
3. Гейт: `kind=script` — обязателен зелёный слот `script`. Pipeline — каждый `step.type=="script"` со своим кодом. Нет — 422, какое место не прогнано. `kind=agent` и шаги llm/skill — без гейта.
4. Промпты: порядок `save_skill_script` → `try_skill_script` → правка до `ok` → сборка; `input_preview` = фактический вход. Тест на строки, как у текущего контракта.
5. Тесты по DoD.

## Критерии приёмки (Definition of Done)
- [ ] Сборка `kind="script"` без dry-run → 422.
- [ ] Зелёный dry-run → сборка проходит.
- [ ] Зелёный dry-run, затем правка кода → снова 422.
- [ ] Pipeline с двумя script-шагами, прогнан один → 422 с указанием шага.
- [ ] `kind="agent"` и pipeline без script-шагов не требуют прогона.
- [ ] Статус виден в `read_skill_draft` и в payload артефакта.
- [ ] Контрактные строки промпта покрыты тестом.
- [ ] Зелёные: `ruff check .`, `pytest` из `backend/`.
