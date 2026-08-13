# CATALOG-78 — Сканер-индексатор папки воркспейса

- **Задача Plane:** [CATALOG-78](https://app.plane.so/belchch/projects/catalog-app/work-items/78) (id: `356c69f6-b2ab-482b-b684-567ebb2bab9c`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 05 · blocked_by CATALOG-77 · blocking CATALOG-79
- **Цель:** Синхронизировать таблицу `document` с файлами в папке воркспейса: скан при открытии и вручную (без watcher). Upload пишет файл под оригинальным именем; результаты скиллов — в `results/`.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — комментариев не было)_

В модели «воркспейс = папка» пользователь кладёт файлы сам. Нужен процесс синхронизации `document` с содержимым папки. Запуск: при открытии воркспейса + вручную. Watcher не делаем.

- Новый `backend/app/documents/scan.py`: обход дерева; пропуск `.catalog/`, скрытых файлов и неподдерживаемых расширений (`kind_for_filename` в режиме skip, не exception).
- Новые файлы → строки `document` (title из имени файла); инкрементальность по mtime+size (новые колонки); хеш содержимого для дедупликации и переименований (тот же хеш, другой путь → обновить path, сохранить id и связи с сессиями); исчезнувшие файлы → удаление строк (поглощает `reconcile_orphans`).
- Отчёт: added / updated / renamed / removed / skipped.
- `ingest.py`: upload под оригинальным именем (коллизии — суффиксом); `build_doc_path` уходит.
- Результаты скиллов (`apply.py`, `runs.py`) пишутся в `results/` внутри папки воркспейса.
- Схема готова к FTS5 (место под извлечённый текст), сам FTS не делаем.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

Предусловие: `CATALOG-77` (две базы + менеджер open). Сканер — уровень 3 валидации из 77. Модель path без slug — `CATALOG-76`.

## Контекст

Сейчас документы живут только если их проиндексировали через upload/apply. Путь задаёт `build_doc_path` (`ingest.py:42–45`): `{subdir}/{slug}-{doc_id[:8]}{ext}` в `documents/` или `results/`. `slugify` + кириллица → латиница (`ingest.py:30–39`). Это прямо противоречит политике «path = файл там, где его положил пользователь».

`kind_for_filename` (`ingest.py:48–53`) бросает `ValueError` на неизвестном расширении. Для сканера нужен режим skip. Поддерживаемые: `.md` `.docx` `.pdf` `.csv` `.xlsx` (`_EXT_TO_KIND`).

Таблица `document` (`schema.py:11–17`): `id, title, path, kind, created_at`. Нет mtime/size/hash. `DocumentRow` (`repo_document.py:14–19`) зеркалит это.

`reconcile_orphans` (`repo_document.py:150–158`) удаляет строки, если файла нет. Вызывается на старте (`main.py:84`), в `GET /documents` (`documents.py:39`) и в tools. Сканер должен поглотить это: removed + остальная синхронизация.

Upload: `POST /documents` → `ingest_file` пишет в `workspace/documents/{slug-id}`. Нужно: оригинал имени в корне или там, куда кладёт пользователь; при коллизии — суффикс (`file.md` → `file-1.md`).

Результаты: `apply.py:355` и `runs.py:145` через `build_doc_path(..., "results")`. Каталог `results/` оставить; имя — без slug-id (человекочитаемый title + суффикс при коллизии). `kind` по-прежнему `result_md`.

Тесты завязаны на `build_doc_path`: `test_storage.py:183+`, `test_apply.py`, `test_api.py:1678`. Их переписать.

## Затрагиваемые файлы

- `backend/app/documents/scan.py` — новый сканер + отчёт.
- `backend/app/documents/ingest.py` — убрать `build_doc_path`; upload под оригинальным именем; `kind_for_filename(..., skip=False)`.
- `backend/app/storage/schema.py` / миграции — колонки `mtime`, `size`, `content_hash`; nullable `extracted_text` (задел FTS5).
- `backend/app/storage/repo_document.py` — CRUD под новые поля; `reconcile_orphans` удалить или сделать тонкой обёрткой над scan.removed.
- `backend/app/storage/workspace.py` (из 77) — вызов scan на `open`.
- `backend/app/api/documents.py` — ручной скан (замена или рядом с `/documents/reconcile`); list без голого `reconcile_orphans`.
- `backend/app/skills/apply.py`, `backend/app/api/runs.py` — запись в `results/` без `build_doc_path`.
- `backend/app/documents/tools.py` — не звать старый reconcile; при необходимости scan.
- `backend/tests/test_storage.py`, `test_apply.py`, `test_api.py` + новый `test_scan.py`.

Frontend вне скоупа (кнопка «сканировать» — отдельный UI-шаг, если появится).

## План действий

1. **Схема.** Additive: `document.mtime`, `document.size`, `document.content_hash`; `document.extracted_text` (TEXT NULL) без FTS5 virtual table. Обновить `DocumentRow` / `_SELECT_COLS` / `create_document`.
2. **`kind_for_filename`.** Добавить безопасный режим: неизвестное расширение → `None`, не exception. Upload по-прежнему 400.
3. **Имена файлов.** Хелпер «оригинальное имя + суффикс при коллизии» в пределах директории. `build_doc_path` и зависимость path от `doc_id[:8]` удалить. `slugify` можно оставить неиспользуемым или удалить вместе с тестами slug.
4. **`ingest_file`.** Писать `content` как `{original_filename}` в корень воркспейса или в текущую политику upload-dir (ТЗ: «виден в папке под своим именем» — не прятать в `documents/slug-id`). Коллизия — `name-1.ext`. Проставить mtime/size/hash. Title = stem оригинала.
5. **Сканер.** Walk от корня воркспейса:
   - skip: `.catalog/`, имена с `.` в начале, неподдерживаемый kind;
   - relative path = ключ сравнения с `document.path`;
   - новый path → insert (title из stem);
   - path есть, mtime+size те же → no-op;
   - path есть, mtime/size другие → обновить hash/meta, при смене hash — `updated`;
   - path нет, но hash совпал с существующей строкой → `renamed` (UPDATE path, id и `session_document` не трогать);
   - строка в БД без файла → `removed` (логика `delete_document` без требования, что файл ещё есть);
   - отчёт dataclass/dict: added/updated/renamed/removed/skipped.
   Идемпотентность: второй прогон без изменений ФС — пустые списки, ноль UPDATE если значения те же.
6. **Хук открытия.** После open в менеджере (77) вызвать scan. Ручной endpoint (например `POST /documents/scan`, `/documents/reconcile` перенаправить).
7. **Результаты скиллов.** Файл в `results/{safe_title}.md` с суффиксом коллизии; `kind=result_md`; колонки mtime/size/hash заполнить. Сканер не должен дублировать их (path уже в индексе).
8. **Тесты.** Дерево с подпапками и смесью md/docx/pdf/skip; повторный скан; rename снаружи → тот же id и session attach; upload → файл с оригинальным именем; apply persist → файл в `results/`. Удалить ассерты на `build_doc_path`. `ruff` + `pytest`.

## Критерии приёмки (Definition of Done)

- [ ] Папка с вложенными подпапками и смесью форматов индексируется; неподдерживаемые и скрытые / `.catalog/` в skipped.
- [ ] Повторный скан без изменений ФС — ноль изменений в БД (пустой отчёт added/updated/renamed/removed).
- [ ] Переименование файла снаружи сохраняет `document.id` и строки `session_document`.
- [ ] Upload через API кладёт файл в папку под оригинальным именем (коллизия — суффикс, не slug-id).
- [ ] Результат скилла (persist / save) появляется в `results/` внутри воркспейса.
- [ ] `build_doc_path` удалён; тесты на slug-path переписаны.
- [ ] `reconcile_orphans` не является отдельным источником истины — исчезнувшие файлы обрабатывает скан.
- [ ] Колонка под извлечённый текст есть; FTS5 virtual table не создаётся.
- [ ] Watcher нет.
- [ ] Из `backend/`: `ruff check .`, `pytest` зелёные.
