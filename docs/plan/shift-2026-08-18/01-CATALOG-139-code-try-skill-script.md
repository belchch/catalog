# CATALOG-139 — тул try_skill_script + эндпоинт dry-run черновика скрипта

- **Задача Plane:** [CATALOG-139](https://app.plane.so/belchch/projects/catalog-app/work-items/139) (id: `28b83b5b-6952-49e8-941c-21057988dc3c`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 01 · blocked_by CATALOG-138 · blocking CATALOG-140
- **Цель:** Планировщик и HTTP могут прогнать черновик script в той же песочнице, что apply, без сохранения документов и `skill_run`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

ADR-0023, п.2, п.3, п.5, п.6, п.7. Прогон черновика script в той же песочнице до сборки скилла. Зависит от общего хелпера из предыдущей задачи.

Тул. `try_skill_script` регистрируется в `build_artifact_tools` (`backend/catalog/skills/artifact_tools.py`) — только планировщик, не попадает в `allowed_tools` скилла и не доступен на apply. Имя вносится в список зарезервированных имён для session skill tools.

Аргументы (все опциональные): `code` — по умолчанию артефакт `script` сессии; `doc_ids` — по умолчанию документы, прикреплённые к сессии (та же session-scope проверка, что у `read_document`); `step_index` — код script-шага из артефакта `steps` вместо артефакта `script`.

Результат тула (JSON): `ok`; `stage` — `validate` | `run` | `verify`; `error` с номером строки и самой строкой; `input_preview` и `input_len` — что скрипт реально видит на входе после `extract_text`; `output_preview`, `output_len`, `output_kind` (`str` | `list`); `duration_ms`; `verify` — исходы `verify_checks` из draft-`meta` по результату (провал verify не делает прогон невалидным, но виден модели). Preview-поля усечены с явной меткой усечения.

Семантика.

- Прогон идёт только через общий хелпер (CATALOG-138): своего исполнителя и своей сборки namespace у dry-run нет. Таймаут тот же (5с).
- Сначала `validate_script`, потом запуск: при провале статики `stage="validate"` и прогона нет.
- Dry-run ничего не сохраняет: ни `Document`, ни `skill_run`, ни trace, ни файлов в воркспейсе.
- Без прикреплённых документов прогон идёт на пустом входе и явно помечается в ответе (`input_len = 0`).
- Лимит прогонов на ход в духе ADR-0021: исчерпание → `ok: false` с причиной в tool result, не исключение.

HTTP. Эндпоинт dry-run артефакта `script` сессии (рядом с существующими `GET/PATCH /sessions/{id}/artifacts`), та же семантика и тот же payload ответа, что у тула — для ручной отладки из UI.

Приёмка.

- Тест: рабочий скрипт по прикреплённому документу → `ok: true`, непустое `output_preview`.
- Тест: падающий скрипт → `ok: false`, `stage: "run"`, номер строки в `error`.
- Тест: запретный `import` → `stage: "validate"`, скрипт не исполнялся.
- Тест: бесконечный цикл → отказ по таймауту, без зависания запроса.
- Тест: документ не из сессии в `doc_ids` → отказ.
- Тест: после dry-run нет новых строк `skill_run` и новых документов.
- Тест: исчерпание лимита прогонов на ход даёт `ok: false`, а не 500.
- `ruff check .`, `pytest` зелёные.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `00-CATALOG-138-code-script-run-parity.md` (хелпер + номер строки). Следующий шаг — `02-CATALOG-140-code-script-build-gate.md` (хранение статуса и гейт сборки). Этот план **не** пишет гейт и **не** трогает UI.

`build_artifact_tools` (`artifact_tools.py:224`) уже отдаёт `save_skill_script` / `read_skill_draft` / `set_skill_meta`. Reserved-имена — `_RESERVED` в `skill_tools.py:36-47`; `try_skill_script` туда же, иначе session skill tools могут занять имя.

Документы сессии: `list_session_documents` (`repo_session_document.py:51`). Session-scope как у `read_document` (`documents/tools.py:36-39`): id не из сессии → отказ, не глобальное чтение. `extract_text` — `documents/extract.py`.

HTTP артефактов: `GET/PATCH /sessions/{id}/artifacts` в `sessions.py:507-523`. Новый POST рядом, тот же payload, что у тула. `SessionArtifactOut` (`schemas.py:323`) не менять под этот ответ — отдельная схема.

Бюджет хода: `SkillBudget` (`budget.py:60`) считает `llm_calls_left` / `nested_runs_left`. Для dry-run — отдельный счётчик на ход (константа в духе ADR-0021), исчерпание → `ok: false` в JSON, не HTTP 500 и не exception из тула.

Verify: `run_verify_async` уже зовётся из apply после скрипта (`apply.py:470`). Dry-run берёт `verify_checks` из draft-`meta`; провал verify не ставит `ok: false`.

## Затрагиваемые файлы
- `backend/catalog/skills/artifact_tools.py` — тул `try_skill_script`; общий runner dry-run (validate → хелпер 138 → optional verify).
- `backend/catalog/skills/skill_tools.py` — `try_skill_script` в `_RESERVED`.
- `backend/catalog/skills/budget.py` (или рядом) — счётчик dry-run на ход.
- `backend/catalog/api/sessions.py` — POST dry-run; `PLANNER_SYSTEM_PROMPT` можно не трогать (это CATALOG-140).
- `backend/catalog/api/schemas.py` — схема ответа dry-run.
- `backend/catalog/documents/extract.py` / `repo_session_document.py` — только вызовы.
- `backend/tests/test_session_artifacts.py` — тул и HTTP: ok, run-error, validate, timeout, чужой doc_id, нет persist, лимит хода.

## План действий
1. Вынести функцию dry-run (не тул): резолв кода (`code` | артефакт `script` | `steps[step_index].code`), резолв документов (`doc_ids` | все прикреплённые), `extract_text`, `validate_script`, хелпер CATALOG-138, optional verify из meta. Никаких insert в `document` / `skill_run`.
2. Зарегистрировать `try_skill_script` в `build_artifact_tools`. Все аргументы optional. Чужой `doc_id` → `ok: false` с явной причиной. Нет кода → `ok: false`. Preview усечь с меткой.
3. Счётчик dry-run на ход: при нуле вернуть `ok: false`, `error` про лимит. HTTP-эндпоинт либо шарит счётчик сессии/хода, либо имеет свой разумный лимит; исчерпание — 200/422 с тем же JSON, не 500.
4. POST `/sessions/{session_id}/artifacts/script/try` (или эквивалент рядом с artifacts) — тот же payload. Не создавать `Document` / `skill_run`.
5. Тесты по DoD. Гейт сборки и запись статуса по хешу — не здесь (CATALOG-140).

## Критерии приёмки (Definition of Done)
- [ ] Рабочий скрипт по прикреплённому документу → `ok: true`, непустое `output_preview`.
- [ ] Падающий скрипт → `ok: false`, `stage: "run"`, номер строки в `error`.
- [ ] Запретный `import` → `stage: "validate"`, скрипт не исполнялся.
- [ ] Бесконечный цикл → отказ по таймауту, запрос не висит.
- [ ] `doc_ids` не из сессии → отказ.
- [ ] После dry-run нет новых `skill_run` и документов.
- [ ] Исчерпание лимита хода → `ok: false`, не 500.
- [ ] Тул есть в planner-реестре и в `_RESERVED`; в `allowed_tools` apply его нет.
- [ ] Зелёные: `ruff check .`, `pytest` из `backend/`.
