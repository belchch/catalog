# CATALOG-83 — uv-упаковка: entry point, пакет `catalog`, статика, настройки без `.env`

- **Задача Plane:** [CATALOG-83](https://app.plane.so/belchch/projects/catalog-app/work-items/83) (id: `39b2d419-0f04-4579-a708-5648cd33ecf7`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 09 · независимый в Plane · code раньше ui
- **Цель:** Упаковать backend как устанавливаемое приложение: `uv tool install` → команда `catalog` поднимает uvicorn на 127.0.0.1, отдаёт собранный фронт, читает ключи не из `.env` в CWD. UI экрана ключа — парный план `10-CATALOG-83-ui-first-run-api-key.md`.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — комментариев не было)_

Целевая доставка: `uv tool install` (uv сам приносит Python). Сейчас: запуск только uvicorn, пакет `app`, статика вне пакета, конфиг из `.env` CWD.

Скоуп (code-часть):

- Console script (например `catalog`): uvicorn на 127.0.0.1 и открытие браузера.
- Переименование топ-левел пакета `app` → `catalog` (все импорты).
- Собранный фронтенд внутрь пакета (`main.py` ищет `app/../static`); сборка wheel запускает `pnpm build`.
- Настройки вместо `.env` из CWD: конфиг/ключи в глобальной базе или `~/.config/catalog/`.
- Публикация: PyPI или git — решить при реализации.

Экран ввода API-ключа при первом запуске — **UI-план**, не этот файл.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

Отдельный этап после воркспейсов (77–80). Парный UI: `10-CATALOG-83-ui-first-run-api-key.md` (после этого code-шага).

## Контекст

`backend/pyproject.toml`: имя проекта `catalog-backend`, пакет `app*` через setuptools, нет `[project.scripts]`. Dev-зависимости pytest/ruff. `requires-python >= 3.11`.

Импорты везде `from app.…` (~50 модулей в `backend/app/`, все тесты). Переименование — механическое, но широкое: пакет, тесты, `golden_run.py`, доки в этом шаге не обязаны все, но код и тесты — да.

Статика: `main.py:145–147` — `Path(__file__).resolve().parent.parent / "static"` = `backend/static`, не внутри пакета. Vite `outDir` по умолчанию `frontend/dist`. В packaged-режиме API и UI на одном origin: `frontend/src/api.ts:184–186` дефолтит `http://localhost:8000` (нужно для Vite :5173); для wheel сборки `VITE_API_URL=""` / relative, иначе SPA с `file`/другого origin разъедется. В dev оставить текущий дефолт.

Конфиг: `config.py:9` `load_dotenv()` из CWD; ключи `OPENROUTER_API_KEY` / `ZAI_API_KEY` только env (`config.py:11–18`). `GET/POST /settings` меняет provider/model в `app.state`, не ключи (`models.py:86–115`). После 77 ключи логично писать в **глобальную app-db** (или `~/.config/catalog/config.toml`). Env остаётся override для CI/тестов.

`uv tool install` ставит scripts в user bin. Имя на PyPI `catalog` почти наверняка занято; дистрибутив уже `catalog-backend`. Решение по умолчанию: **сначала git** (`uv tool install git+https://…#subdirectory=backend` или монорепо-корень с pyproject), PyPI — когда будет уникальное имя (`catalog-app`). Зафиксировать выбор в работе, не блокировать entry point.

## Затрагиваемые файлы

- `backend/app/` → `backend/catalog/` (или rename in place): все `from app.` → `from catalog.`.
- `backend/tests/**`, `backend/scripts/golden_run.py` — импорты.
- `backend/pyproject.toml` — `[project.scripts] catalog = "catalog.cli:main"`; package-data static; hatch/setuptools hook на `pnpm build`; возможно `packages = ["catalog"]`.
- `backend/catalog/cli.py` (новый) — uvicorn + `webbrowser.open`.
- `backend/catalog/main.py` — static из `files("catalog") / "static"` (importlib.resources), не `../static`.
- `backend/catalog/config.py` — чтение ключей: env override → app-db / config dir; `load_dotenv` не обязателен для прод-запуска.
- `backend/catalog/api/models.py` (или settings) — API сохранения ключей (без возврата секрета в GET). Флаг `needs_setup` / `keys_configured` для UI.
- `frontend/vite.config.ts` / build env — relative API base для production build.
- `frontend/src/api.ts` — same-origin, если `VITE_API_URL` пуст.
- Тесты конфига и cli (мок webbrowser).

Не этот шаг: экран ключа в React (UI-план).

## План действий

1. **Переименовать пакет** `app` → `catalog`. Массовая замена импортов. Прогнать `pytest` / `ruff` до остальных фич, чтобы не смешать диффы.
2. **CLI.** `catalog.cli:main`: host `127.0.0.1`, порт из env/флага (дефолт 8000), `uvicorn.run("catalog.main:app", …)`, затем `webbrowser.open`. Не слушать `0.0.0.0`.
3. **Статика в wheel.** Vite production build → `catalog/static/`. `pyproject` `package-data`. Lifespan/mount через `importlib.resources`. SPA fallback уже есть (`StaticFiles(..., html=True)`).
4. **Build hook.** При сборке sdist/wheel: если есть `frontend/`, запустить `pnpm install && pnpm run build` с `VITE_API_URL=""`. Документировать, что wheel из git source требует Node; заранее собранный static можно коммитить только если команда так решит (лучше hook, не коммитить dist).
5. **Ключи.** Таблица/kv в app-db (77) или файл `~/.config/catalog/config.toml`. Приоритет: env > persisted. `GET /setup` или расширение `/settings`: `{keys_configured: bool, provider}` **без** самих ключей. `PUT` ключа — пишет persist и пересобирает `app.state.providers` (сейчас провайдеры создаются в lifespan с ключом из env — нужна функция rebuild).
6. **Публикация.** Зафиксировать: `uv tool install` из git (subdirectory backend или корневой pyproject, который указывает на backend). PyPI отложить, если имя не свободно. Обновить README-RUN (81) одной командой install, если 81 уже влит — иначе абзац здесь / правка runbook.
7. Тесты: rename не сломал pytest; config без `.env`; static path внутри пакета; cli не падает на bind (мок). `ruff`, `pytest`. Frontend typecheck/build для relative API.

## Критерии приёмки (Definition of Done)

- [ ] Пакет импортируется как `catalog`, не `app`; тесты зелёные.
- [ ] `[project.scripts] catalog` поднимает сервер на 127.0.0.1 и открывает браузер.
- [ ] Wheel содержит собранный фронт; `main` отдаёт SPA из пакета, не из `backend/static` относительно CWD.
- [ ] Ключи не требуют `.env` в текущей директории; env по-прежнему перекрывает persist (для CI).
- [ ] Есть API «ключи заданы / записать ключ» без утечки секрета в GET — контракт для UI-плана.
- [ ] Способ установки без PyPI документирован (`uv tool install` из git) либо выбран и описан PyPI-пакет.
- [ ] Из `backend/`: `ruff check .`, `pytest` зелёные. Frontend production build с same-origin API собирается.

## Вне объёма

- Экран первого запуска в UI (парный ui-план).
- Удаление Docker-артефактов (81 только помечает).
- Публичный релиз на PyPI, если выбран git-install.
