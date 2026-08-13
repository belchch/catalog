# CATALOG-79 — API воркспейсов: open/rescan/browse, блокировка при активных ранах

- **Задача Plane:** [CATALOG-79](https://app.plane.so/belchch/projects/catalog-app/work-items/79) (id: `66296bc6-eb90-4e40-a083-769cab0cb81c`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** HTTP-слой над менеджером воркспейсов и сканером: реестр, open с ветками подтверждения, rescan, безопасный browse ФС, 409 при активном `skill_run`.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — комментариев не было)_

Контейнера нет — бэкенд видит ФС пользователя; обзор ограничен разрешённым корнем (`$HOME` по умолчанию).

Роутер `backend/app/api/workspaces.py`:

- `GET /workspaces` — реестр (путь, имя, last_opened); `GET /workspaces/current`.
- `POST /workspaces/open`: валидация → бэкап → ре-скан → активация. Ответы: ok / пустая папка (инициализация) / папка с файлами без `.catalog` (явное подтверждение + отчёт что найдено) / ошибка (невалидная база, чужая версия схемы, недоступный путь).
- `POST /workspaces/rescan` — ручной скан с отчётом added/updated/renamed/removed/skipped.
- `GET /fs/browse?path=` — листинг директорий строго в пределах корня (защита от path traversal).
- Блокировка open/switch при `skill_run.status = running` → 409.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

Предусловия: CATALOG-77 (менеджер, две БД, реестр в app-db), CATALOG-78 (сканер и отчёт). Этот шаг не дублирует менеджер — только HTTP + browse + статусы open. UI пикера папки — не здесь.

## Контекст

Роутеры подключаются в `main.py:108–112` (`documents`, `sessions`, `skills`, `runs`, `models`). Нового `workspaces` нет. `api/__init__.py` — пустой пакетный докстринг.

`GET /documents` и бизнес-роуты после 77 отдают 409 без открытого воркспейса. Open должен снять это.

Статусы рана: `skill_run.status` = `running|ok|failed` (`schema.py:48`). `create_run` / `get_run` в `backend/app/skills/repo_run.py`. Отдельного `list running` нет — для 409 нужен `EXISTS`/`COUNT` по `status = 'running'` на **текущей** workspace-БД до close/switch.

Browse: сейчас бэкенд не отдаёт листинг ФС. Корень обзора — `$HOME`, лучше env-override (`APP_FS_ROOT`) для тестов (`tmp_path`), иначе pytest не сможет ходить в home. Резолв: `Path(path).resolve()` обязан быть относительно `root.resolve()` (`relative_to` без `ValueError`). Симлинки за корень — отказ.

Ветки `POST /workspaces/open` (нужен флаг `confirm: bool` в теле):

| Состояние папки | Без confirm | С confirm |
|---|---|---|
| Есть валидный `.catalog/index.db` | open + backup + scan → ok | то же |
| Пустая (нет файлов и нет `.catalog`) | статус «нужна инициализация», не писать диск | создать `.catalog`, пустую схему, ok |
| Файлы есть, `.catalog` нет | статус «нужно подтверждение» + preview скана (без записи БД) | создать `.catalog`, проиндексировать, ok |
| Битая БД / чужой `user_version` / нет доступа | 4xx, не активировать | — |

Реестр: таблица app-db из 77 (`path`, `display_name`, `last_opened`). `GET /workspaces` читает её через `get_app_db`. `GET /workspaces/current` — 204/null, если ничего не открыто (не 409: это как раз способ узнать состояние).

`POST /workspaces/rescan` — 409 если воркспейс не открыт; иначе `scan()` из 78.

Схемы Pydantic — в `api/schemas.py` рядом с остальными.

## Затрагиваемые файлы

- `backend/app/api/workspaces.py` — новый роутер.
- `backend/app/api/schemas.py` — `WorkspaceOut`, `WorkspaceOpenRequest`, `WorkspaceOpenResult`, `ScanReport`, `FsEntry`.
- `backend/app/main.py` — `include_router(workspaces.router)`.
- `backend/app/config.py` — `APP_FS_ROOT` (дефолт home).
- `backend/app/storage/workspace.py` / `repo_run.py` — если 77 ещё не экспортирует «есть running» и dry-run preview скана, добавить тонкие методы. Не копировать логику open в роутер.
- `backend/app/api/documents.py` — не дублировать rescan, если 78 уже повесил `/documents/scan`: один канонический `POST /workspaces/rescan`.
- `backend/tests/test_workspaces.py` (новый) + правки `test_api.py` по необходимости.

Frontend вне скоупа.

## План действий

1. **Конфиг корня browse.** `APP_FS_ROOT`, дефолт `Path.home()`. В тестах — `tmp_path`.
2. **Схемы ответа open.** Дискриминируемый `status`: `ok` | `needs_init` | `needs_confirm` | плюс HTTP ошибки 400/403/404/409/422. Поле `scan` (preview или фактический отчёт). `confirm: bool` в POST body вместе с `path`.
3. **Роутер.**
   - `GET /workspaces`, `GET /workspaces/current`.
   - `POST /workspaces/open` — вызвать менеджер; 409 если на *текущем* воркспейсе есть running runs (switch). Первый open при `current is None` — running проверять не на чем.
   - `POST /workspaces/rescan`.
   - `GET /fs/browse?path=` — только директории (и опционально флаг «есть .catalog»), не содержимое файлов. Path traversal тесты: `..`, абсолютный путь вне корня, symlink.
4. **Реестр.** После успешного open — upsert в app-db (`last_opened = now`, имя = `path.name`).
5. **Сценарий приёмки в тесте.** Папка A с md → open+confirm → `GET /documents` непустой; папка B → open; обратно A → те же document id / session_document.
6. **Ран.** Создать running `skill_run` → open B → 409; пометить ok → open проходит.
7. `ruff` + `pytest`.

## Критерии приёмки (Definition of Done)

- [ ] `GET /workspaces` и `GET /workspaces/current` работают без открытой папки.
- [ ] Open папки с файлами без `.catalog` без `confirm` не создаёт индекс и возвращает preview; с `confirm` — создаёт `.catalog`, документы видны в `GET /documents`.
- [ ] Переключение A → B → A сохраняет id документов и прикрепления к сессиям (каждая папка — своя `index.db`).
- [ ] При `skill_run.status = running` `POST /workspaces/open` на другую папку → 409; после завершения — успех.
- [ ] `GET /fs/browse` не выходит за `APP_FS_ROOT` ни при `..`, ни при абсолютном пути, ни через symlink.
- [ ] `POST /workspaces/rescan` возвращает отчёт added/updated/renamed/removed/skipped.
- [ ] Из `backend/`: `ruff check .`, `pytest` зелёные.
