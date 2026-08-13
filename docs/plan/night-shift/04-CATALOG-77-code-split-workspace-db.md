# CATALOG-77 — Расщепление хранилища: глобальная БД + `.catalog/index.db`, менеджер воркспейсов

- **Задача Plane:** [CATALOG-77](https://app.plane.so/belchch/projects/catalog-app/work-items/77) (id: `2ee5e86e-61de-4dbd-b73e-19ff3364e06e`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Разрезать одну `catalog.db` на глобальную БД (настройки + реестр воркспейсов в `APP_DATA_DIR`) и БД воркспейса (`.catalog/index.db`). Приложение стартует без открытой папки; бизнес-эндпоинты отвечают 409, пока воркспейс не открыт.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — комментариев не было)_

Сейчас одна глобальная SQLite (`catalog.db`) создаётся в lifespan (`backend/app/main.py`) и раздаётся через `get_db` (`backend/app/api/deps.py`, ~32 вызова в 5 роутерах). Нужно две базы без перекрёстных ссылок.

Скоуп:

- `storage/schema.py`: `APP_SCHEMA` и `WORKSPACE_SCHEMA`; версия через `PRAGMA user_version`.
- Менеджер воркспейсов: open/close/validate/backup; валидация в три уровня (маркер `.catalog/index.db` + `user_version` → `PRAGMA quick_check` → ре-скан подключается в задаче сканера); ротация копий `index.db` в `.catalog/backups/` при открытии.
- `main.py`: lifespan создаёт глобальную базу и менеджер; убрать `ensure_repo(documents/skills)` и стартовый `reconcile_orphans`.
- `deps.py`: `get_db` → `get_app_db` + `get_workspace_db` (409, если воркспейс не открыт); разнести вызовы по роутерам.
- `app.state.tools` / `app.state.workspace` — производные от активного воркспейса, пересборка при переключении.
- Тесты хранилища и API обновить под две базы.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

Связанный план: `docs/plan/night-shift/CATALOG-76-code-adr-workspace-as-folder.md` (ADR модели). Этот шаг — реализация хранилища; UI открытия папки — не здесь.

## Контекст

Lifespan (`backend/app/main.py:51–88`): mkdir data-root → `ensure_repo` documents/skills (ADR-0012) → `Database(settings.db_path)` → `init_schema` → `app.state.db` / `workspace` / `tools` → `reconcile_orphans`. Старт всегда с открытым «воркспейсом» = `settings.workspace_dir`.

`Database` (`backend/app/storage/db.py`): on-disk — новое соединение на операцию (уже укладывается в инвариант «не держать соединение между запросами»). `init_schema` гоняет единый `SCHEMA_SQL` + `ADDITIVE_MIGRATIONS`.

Текущая схема (`schema.py`) целиком — workspace-таблицы: `document`, `session`, `session_document`, `message`, `skill`, `skill_run`, `session_artifact`. Глобальных таблиц нет. Runtime-настройки провайдера/модели живут в `app.state` (`models.py:86–115`), не в SQLite.

`get_db` (`deps.py:32–33`) отдаёт `request.app.state.db`. `Depends(get_db)`: sessions 11, skills 9, documents 4, runs 3. WS читают `websocket.app.state.db` / `.workspace` / `.tools` на старте соединения (`sessions.py:621+`, `runs.py:172+`) — при переключении папки эти ссылки устареют, если не перечитывать из менеджера на каждый кадр / не блокировать switch при живом WS.

`GET/POST /settings`, `/providers`, `/models` — не зависят от `get_db`; после расщепления остаются на глобальном состоянии (+ запись в app-БД, если настройки туда переезжают).

Тесты: `conftest.py` гоняет реальный lifespan на `tmp_path` и отдаёт `Database(settings.db_path)`. Куча юнитов вызывает `Database(":memory:").init_schema()` — после сплита им нужна workspace-схема (или явный параметр).

Ре-скан (уровень 3 валидации) в этом шаге **не реализуется** — хук/TODO под задачу сканера. `reconcile_orphans` убрать со старта; вызовы из `documents.py` / tools оставить, они имеют смысл только при открытом воркспейсе.

## Затрагиваемые файлы

- `backend/app/storage/schema.py` — `APP_SCHEMA` + `WORKSPACE_SCHEMA`, `user_version`, разнести `ADDITIVE_MIGRATIONS`.
- `backend/app/storage/db.py` — `init_schema` принимает, какую схему накатывать; выставлять `PRAGMA user_version`.
- `backend/app/storage/workspace.py` (новый) — менеджер: open/close/validate/backup, текущий `Database` + path.
- `backend/app/main.py` — lifespan: только app-db + менеджер (пустой); без `ensure_repo` и стартового `reconcile_orphans`.
- `backend/app/api/deps.py` — `get_app_db`, `get_workspace_db` (HTTP 409), `get_workspace`/`get_tools` из менеджера.
- `backend/app/api/sessions.py`, `documents.py`, `skills.py`, `runs.py` — заменить `get_db`; WS не кэшировать db на всё соединение дольше запроса/сообщения.
- HTTP open/close/browse — **не этот шаг**, это CATALOG-79 (`CATALOG-79-code-workspaces-api.md`). Здесь менеджер + deps; в тестах 77 открывать папку вызовом менеджера, не HTTP.
- `backend/app/config.py` — `APP_DB_PATH` указывает на глобальную БД в `APP_DATA_DIR` (не `catalog.db` как workspace). Имя файла глобальной БД зафиксировать в ADR/коде (например `app.db` или оставить `catalog.db` только для app-слоя).
- `backend/tests/conftest.py` + `test_storage.py` / `test_api.py` / остальные `init_schema` — две базы; фикстура «открыть tmp-папку».
- `backend/app/storage/git.py` — не вызывать `ensure_repo` из lifespan (файл можно оставить для других шагов).

Frontend вне скоупа.

## План действий

1. **Схемы.** Вынести текущий `SCHEMA_SQL` в `WORKSPACE_SCHEMA`. `APP_SCHEMA`: реестр воркспейсов (`id`, `path`, `opened_at` / `display_name`) и настройки (`provider`, `model` — то, что сейчас в `app.state` и должно переживать рестарт). Константы `APP_USER_VERSION` / `WORKSPACE_USER_VERSION`. `Database.init_schema(schema, user_version)`.
2. **Менеджер.** Класс с состоянием `current: Database | None`, `root: Path | None`. `validate`: (1) есть `.catalog/index.db` и `user_version` совместим; (2) `PRAGMA quick_check`; (3) ре-скан — no-op/хук. `open(path)`: при отсутствии `.catalog` — создать (явное подтверждение UI — не этот шаг; API может принять `confirm_init=true`). Backup: скопировать существующий `index.db` в `.catalog/backups/<timestamp>.db`, ротация (лимит N, например 5). `close()`: сбросить current, tools, workspace path. Переключение: если есть `skill_run.status = running` — отказ (409/409-like). После open: пересобрать `app.state.workspace` и `app.state.tools`.
3. **Lifespan.** Создать app-db в `APP_DATA_DIR`, `init_schema(APP_SCHEMA)`, положить менеджер с `current=None`. Не создавать documents/skills git-репо. Не звать `reconcile_orphans`. `app.state.workspace`/`tools` — `None` или пустой registry до open.
4. **Deps.** `get_app_db` — всегда. `get_workspace_db` / `get_workspace` / `get_tools` — если нет current, `HTTPException(409)`. Удалить `get_db`. Разнести роутеры: бизнес (sessions/documents/skills/runs) → workspace db; settings/providers — app db + `app.state`.
5. **Открытие в тестах 77.** Через менеджер напрямую (фикстура), без HTTP. Роутер — CATALOG-79.
6. **Инвариант соединений.** Роутеры берут `Database` через Depends на запрос. WS: на каждый цикл сообщения читать db/tools из менеджера; не захватывать `websocket.app.state.db` на всё соединение. `Database.connect` по-прежнему закрывает conn в `finally`.
7. **Настройки.** `GET/POST /settings` читают/пишут app-db (и зеркалят `app.state`), чтобы переживать рестарт без открытого воркспейса.
8. **Тесты.** `conftest`: lifespan без воркспейса + хелпер `open_workspace(tmp_path)`. API-тесты бизнес-логики сначала open. Юниты storage: `init_schema` с workspace schema. Новые тесты: старт → 409 на `/sessions`; open → схема и backup-файл; close → снова 409; `ruff` + `pytest`.
9. Старый `catalog.db` не мигрировать (CATALOG-76).

## Критерии приёмки (Definition of Done)

- [ ] Приложение стартует без открытого воркспейса; эндпоинты бизнес-логики отвечают 409 до открытия.
- [ ] `/settings`, `/providers`, `/models` доступны без открытого воркспейса.
- [ ] Открытие папки создаёт/открывает `.catalog/index.db` с полной workspace-схемой и кладёт бэкап предыдущей версии в `.catalog/backups/` (если файл уже был).
- [ ] `PRAGMA user_version` выставлен на обеих базах; несовместимая версия не открывается молча.
- [ ] Lifespan не вызывает `ensure_repo` и стартовый `reconcile_orphans`.
- [ ] Ни один роутер не держит `Database` дольше одного запроса; WS не кэширует db на жизнь сокета.
- [ ] `get_db` удалён; вызовы разнесены на `get_app_db` / `get_workspace_db`.
- [ ] Из `backend/`: `ruff check .`, `pytest` зелёные.
