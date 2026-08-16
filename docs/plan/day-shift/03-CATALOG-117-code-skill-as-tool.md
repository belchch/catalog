# CATALOG-117 — Скилл как вызываемый тул в сессии (backend)

- **Задача Plane:** [CATALOG-117](https://app.plane.so/belchch/projects/catalog-app/work-items/117) (id: `9737ccb9-cba2-4d74-b798-05a6ec71e967`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 03 · blocking CATALOG-118 · blocking CATALOG-119
- **Цель:** Прикреплённый `kind=script` скилл регистрируется как тул сессии; вызов создаёт вложенный `skill_run` с `parent_run_id` и гоняет `verify_checks`. Первый срез: глубина 1, без рекурсии.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. Шаг 4 из 7. Блокирует CATALOG-118 и CATALOG-119.

- ADR-0019: композиция скиллов; переформулировать вывод ADR-0018 (`run_script` отклонён — про code interpreter, не про замороженный `config_json`).
- Таблица `session_skill`; `parent_run_id` на `skill_run` в `ADDITIVE_MIGRATIONS`.
- `repo_session_skill.py` по образцу `repo_session_document.py`.
- REST: не `POST /sessions/{id}/skills` (занят билдом) — например `/sessions/{id}/tools`.
- `_ws_session_tools`: по тулу на прикреплённый скилл, имя `^[a-z0-9_]+$`, без коллизий с document tools.
- Развязать `_apply_core` от обязательных `input_doc_ids` — вложенный вызов принимает текст.
- Пиннинг: id + хэш `config_json` в трейсе вызова.
- Тесты: attach/detach, вызов тула, `parent_run_id`.

Открытые решения зафиксировать в ADR (вход текст vs docs; пин версии; agent/pipeline позже; persist вложенных результатов).

Референс: `backup-pre-revert-0234` (файлы были удалены revert'ом 79f5fef).

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Сейчас тулов скиллов нет:

- `backend/catalog/api/sessions.py` — `_ws_session_tools` собирает только `build_document_tools` + `build_artifact_tools`. REST: documents attach/detach есть (`:305-318`), skills-as-tools нет. `POST /sessions` — создание сессии.
- `backend/catalog/storage/schema.py:58` — `session_document`; `skill_run` без `parent_run_id` (`ADDITIVE_MIGRATIONS` с `:102`).
- `backend/catalog/storage/repo_session_document.py` — образец attach/detach/list.
- `backend/catalog/skills/apply.py:169-222` — `_apply_core` падает, если `input_doc_ids` пуст / документ не найден.
- `docs/adr/0018-pipeline-skills.md` — `run_script` как тул отклонён.

## Затрагиваемые файлы
- `docs/adr/0019-skill-as-session-tool.md` — новый ADR.
- `docs/adr/0018-pipeline-skills.md` — уточнение про frozen script vs interpreter.
- `backend/catalog/storage/schema.py` — `session_skill`, миграция `parent_run_id`.
- `backend/catalog/storage/repo_session_skill.py` — новый.
- `backend/catalog/api/sessions.py` — REST `/tools` + регистрация в `_ws_session_tools`.
- `backend/catalog/api/schemas.py` — request/response прикрепления.
- `backend/catalog/skills/skill_tools.py` — новый: build + handler.
- `backend/catalog/skills/apply.py` — текстовый вход без обязательных docs.
- `backend/tests/test_session_skill_tools.py` — новый.

## План действий
1. ADR-0019 + правка ADR-0018. Зафиксировать открытые решения первого среза: вход — текст; пин — хэш `config_json`; только `script`; вложенный результат в модель, не как документ.
2. Схема и репозиторий `session_skill`; колонка `parent_run_id`.
3. REST list/attach/detach на `/sessions/{id}/tools`.
4. `skill_tools.py`: slug-имя, вызов `_apply_core` с текстом, `parent_run_id`, пин в trace.
5. Регистрация в `_ws_session_tools` (потребуется `provider` только если handler его использует — для script можно без LLM).
6. Тесты attach/detach, вызов, `parent_run_id`, коллизии имён.

## Критерии приёмки (Definition of Done)
- [ ] ADR-0019 есть; ADR-0018 не противоречит композиции frozen script.
- [ ] REST attach/detach/list работает; путь не пересекается с билдом скилла.
- [ ] Планировщик видит по тулу на каждый прикреплённый script-скилл.
- [ ] Вызов пишет `skill_run.parent_run_id` и пин конфига; verify_checks гоняются.
- [ ] `_apply_core` принимает текст без документов.
- [ ] `ruff check .`, `pytest` из `backend/`.
