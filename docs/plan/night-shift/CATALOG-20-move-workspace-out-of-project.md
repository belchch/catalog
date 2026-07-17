# CATALOG-20 — Вынести workspace из папки проекта

- **Задача Plane:** [CATALOG-20](https://app.plane.so/belchch/projects/catalog-app/work-items/20) (id: `141f68a2-874b-4439-b570-a79fdd8325bc`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Перевести все данные приложения (документы, результаты прогонов, `catalog.db`, prompt-логи) на **абсолютный data-root вне дерева исходников** с env-override (`APP_DATA_DIR`) и OS-дефолтом, и заложить фундамент из двух app-owned git-репозиториев (`documents/`, `skills/`) через dulwich. Реализует ADR-0012 (Accepted).

## Контекст

Текущая модель (баг из ADR-0012:11) — пути относительные, резолвятся от CWD процесса, данные физически лежат в репо исходников:

- `backend/app/config.py:13-14` — `APP_WORKSPACE = os.getenv("APP_WORKSPACE", "workspace")` и `APP_DB_PATH = os.getenv("APP_DB_PATH", "catalog.db")` — **оба относительные**.
- `config.py:24-26` — `PROMPT_LOG_DIR` по умолчанию = `os.path.join(APP_WORKSPACE, "prompt_logs")` → тоже относительный.
- `config.py:37-44` — `Settings` несёт `db_path`, `workspace_dir`, `prompt_log_dir` как строки; `get_settings()` (`config.py:47-49`) просто собирает их из модульных констант (env читается на импорте).
- `main.py:38-50` lifespan: `Database(settings.db_path)`, `app.state.workspace = settings.workspace_dir`, `build_document_tools(db, settings.workspace_dir)`. Никакого `mkdir` корня здесь нет — каталоги создаются «лениво» потребителями.
- Потребители путей: `documents/ingest.py:39-41` (`workspace/documents`, `mkdir parents=True`); `skills/apply.py:193-194` (`workspace/results`, `mkdir parents=True`); `prompt_logs` — через `llm/log_context.py` (см. `prompt_log_dir`).
- `.gitignore:20-25` — `workspace/*` + `!workspace/.gitkeep`, отдельный `prompt_logs/`, `*.db`. После переезда данные больше не в дереве исходников → правило `workspace/*` теряет смысл.
- `backend/tests/conftest.py:84-91` — фикстура `settings` уже строит `Settings(db_path=tmp_path/api.db, workspace_dir=tmp_path/ws, default_model=...)`; НЕ задаёт `prompt_log_dir`/`data_dir` — нужно убедиться, что data-root не ломает tmp-изоляцию тестов. Фикстура `client` (`conftest.py:99-109`) патчит `app.main.get_settings`.
- `backend/pyproject.toml:6-15` — **dulwich нет в зависимостях** (есть fastapi, uvicorn, httpx, pydantic, python-dotenv, jsonschema, python-docx, python-multipart). dev: pytest, ruff (mypy не подключен).

ADR-0012 (`docs/adr/0012-data-root-and-git-repos.md`, Accepted) фиксирует: (1) data-root абсолютный, env `APP_DATA_DIR`, OS-дефолт; (2) два app-owned git-репо `documents/`+`skills/`, оба `git init` приложением; (3) движок — **dulwich** (чистый Python, 0 host-зависимостей); (4) внешних репо пока нет, push наружу не делаем; (5) версия документа опирается на git, SQLite — пересобираемый индекс (инвариант ADR-0005); (6) folder-picker — admin/env, не UI.

Скоуп задачи (из описания): config → data-root, резолв `workspace`/`catalog.db`/`prompt_logs` под ним, dulwich-обёртка `git init` для `documents/`+`skills/`, обновить `.gitignore`, тесты. **Вне скоупа:** миграция скиллов в git-репо + реальный коммит в `commit_skill`, модель версии документа/diff, ингест внешних репо.

## Затрагиваемые файлы

**Новые:**
- `backend/app/storage/git.py` — dulwich-обёртка: `ensure_repo(path)` — `git init` (через `dulwich.repo.Repo.init`), idempotent; опц. `Repo.init` для `documents/` и `skills/`.
- (опц.) `backend/app/storage/paths.py` — централизованный резолв `data_dir`/`db_path`/`workspace`/`prompt_logs` из data-root.

**Изменяемые:**
- `backend/app/config.py` — добавить `APP_DATA_DIR` (env, OS-дефолт через `sys.platform`/`os.path` → `~/Library/Application Support/catalog` на macOS, `~/.local/share/catalog` иначе); сделать пути **абсолютными** (`Path(...).expanduser().resolve()`); `workspace_dir`/`db_path`/`prompt_log_dir` резолвятся под data-root в `get_settings()`. Сохранить env-overrides (`APP_WORKSPACE`, `APP_DB_PATH`, `PROMPT_LOG_DIR`) для обратной совместимости/тестов, но дефолт — под data-root.
- `backend/app/main.py` — в lifespan (`main.py:38-50`) вызвать `ensure_repo(...)` для `documents/` и `skills/` (mkdir + `git init`); при необходимости создавать data-root (`mkdir parents=True, exist_ok=True`).
- `backend/pyproject.toml:6-15` — добавить `dulwich>=0.22` (или актуальный минимум) в `dependencies`.
- `.gitignore` — убрать/ослабить `workspace/*` и `!workspace/.gitkeep` (данных в репо больше нет); оставить `prompt_logs/` и `*.db` как страховку на случай переопределённых путей.
- `backend/tests/conftest.py:84-91` — при необходимости задавать `data_dir`/`prompt_log_dir` под `tmp_path`, чтобы data-root не падал на OS-дефолт в CI.

**Тесты:**
- `backend/tests/test_config.py` (новый) — дефолтный data-root абсолютный и вне CWD; env `APP_DATA_DIR` переопределяет; `workspace`/`db_path`/`prompt_logs` лежат под data-root.
- `backend/tests/test_git.py` (новый) — `ensure_repo` создаёт git-репо (`.git` существует), идемпотентен на повторный вызов.

## План действий

1. **Зависимость.** Добавить `dulwich` в `backend/pyproject.toml` (`dependencies`), установить в venv (`pip install -e backend[dev]`), зафиксировать лок.
2. **Config — data-root.** В `config.py` ввести `APP_DATA_DIR = os.getenv("APP_DATA_DIR") or os-data-default` (OS-дефолт по `sys.platform`: macOS → `~/Library/Application Support/catalog`, иначе `~/.local/share/catalog`). Все производные пути (`workspace_dir`=`data_dir/workspace` если не задан `APP_WORKSPACE`, `db_path`=`data_dir/catalog.db` если не задан `APP_DB_PATH`, `prompt_log_dir`=`workspace/prompt_logs`) сделать абсолютными через `Path(...).expanduser()`. Резолв один раз в `get_settings()`.
3. **Git-обёртка.** В `app/storage/git.py` реализовать `ensure_repo(target: Path) -> Repo`: `target.mkdir(parents=True, exist_ok=True)`; если `.git` нет — `Repo.init(str(target))`; вернуть репо. Чистый dulwich, без subprocess, без требования `user.name/email` на хосте.
4. **Lifespan.** В `main.py` lifespan после построения `settings` вызвать `ensure_repo(Path(settings.workspace_dir) / "documents")` и `ensure_repo(... / "skills")` (или под data-root напрямую, если `workspace` = data-root — уточнить по решению п.2). Создать data-root, если отсутствует.
5. **.gitignore.** Удалить `workspace/*` + `!workspace/.gitkeep`; оставить `prompt_logs/`, `*.db` (страховка). Убедиться, что `workspace/` как директория-артефакт больше не нужна в репо исходников.
6. **Тесты.** `test_config.py`: data-root абсолютный; переопределение через `APP_DATA_DIR` (monkeypatch env + пересборка `get_settings()`); `workspace`/`db_path`/`prompt_logs` под data-root. `test_git.py`: `ensure_repo` создаёт `.git`, повторный вызов не падает. Проверить `conftest.py` — фикстура `settings` должна явно указывать `data_dir`/пути под `tmp_path`, чтобы тесты не трогали OS-дефолт.
7. **Регресс.** Прогнать `pytest backend/tests` (особенно apply/ingest/documents, которые mkdir под workspace) — убедиться, что абсолютные пути и `git init` не ломают существующие кейсы.
8. **Ручная проверка.** Без env: данные создаются под OS data-root (macOS `~/Library/Application Support/catalog/...`), в дереве исходников ничего не появляется. С `APP_DATA_DIR=/tmp/x` — данные идут туда.

## Критерии приёмки (Definition of Done)

- [ ] `config.py`: при отсутствии env все пути (`workspace`, `catalog.db`, `prompt_logs`) **абсолютные** и лежат под OS data-root, а не в CWD/дереве исходников.
- [ ] `APP_DATA_DIR` переопределяет корень; `APP_WORKSPACE`/`APP_DB_PATH`/`PROMPT_LOG_DIR` по-прежнему работают как точечные override.
- [ ] На старте приложения автоматически создаются два git-репозитория (`documents/`, `skills/`) через dulwich (`.git` существует), идемпотентно при повторном запуске.
- [ ] dulwich добавлен в `pyproject.toml` и установлен; никакой зависимости от системного `git`/его конфигурации (`user.name/email`) нет.
- [ ] `.gitignore` больше не игнорирует `workspace/*` внутри репо исходников (данных там нет); `*.db`/`prompt_logs/` оставлены как страховка.
- [ ] Данные приложения больше не появляются в дереве исходников (проверка: после прогона `git status` чист в части `workspace/`, `catalog.db`).
- [ ] `conftest.py`: тесты изолированы в `tmp_path` (data-root не ломает tmp-изоляцию).
- [ ] `pytest backend/tests` зелёные; добавлены `test_config.py` и `test_git.py`.
- [ ] `ruff check backend` проходит без ошибок.
