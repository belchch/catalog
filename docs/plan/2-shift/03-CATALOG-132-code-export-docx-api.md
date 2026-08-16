# CATALOG-132 — code: тул export_docx + POST /export/docx + игнор export/ в скане

- **Задача Plane:** [CATALOG-132](https://app.plane.so/belchch/projects/catalog-app/work-items/132) (id: `50cb6f77-7343-446a-92a8-29993a5fd976`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 03 · blocked_by CATALOG-131 · blocking CATALOG-133
- **Цель:** Одна реализация экспорта: тул `export_docx` и `POST /export/docx`; файлы в `export/` не индексируются сканом; самопроверка через `extract_text`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

- Тул в `build_document_tools`: `export_docx(doc_ids, title="", template="") -> {ok, path, headings, tables}`.
- Изоляция сессии: документ не из `session_documents` → `document_not_available_in_session`.
- Запись: `safe_filename` + `allocate_rel_path(..., subdir="export")`.
- `_EXPORT_DIR = "export"` в игнор `_walk_workspace` рядом с `_CATALOG_DIR`.
- REST `POST /export/docx` `{doc_ids, title?, template?}` на `get_workspace_db` + `get_workspace`.
- После записи перечитать `extract_text(..., "docx")` и сверить число заголовков и строк таблиц; не сошлось → `ok: false`.
- Шаг экспорта в конце `scripts/golden_run.py`.
- Зафиксировать: первый write-тул в реестре (задел read/write, механику разрешений не делать).

Открытые решения (зафиксировать в начале шага): несколько документов → один docx с разрывами (дефолт); шаблон — параметр + дефолт из настроек.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/2-shift/02-CATALOG-131-code-render-docx.md` (`render_docx`).

- `backend/catalog/documents/tools.py:15-76` — только `list_documents` / `read_document`; изоляция сессии в `read_document` (`tools.py:36-38`).
- `backend/catalog/documents/ingest.py:125,136` — `safe_filename`, `allocate_rel_path`.
- `backend/catalog/api/runs.py:157` — запись результата в `results/`.
- `backend/catalog/documents/scan.py:71-92` — `_walk_workspace` игнорит `_CATALOG_DIR` и скрытые, не `export/`.
- `backend/catalog/api/deps.py:41,52` — `get_workspace_db` / `get_workspace` (409 без воркспейса).
- `backend/catalog/skills/verify.py` — `CheckFn` видит только текст, не ФС; самопроверка остаётся внутри тула.
- `backend/scripts/golden_run.py` — сквозной прогон без шага экспорта.

UI-кнопка — `docs/plan/2-shift/04-CATALOG-133-ui-export-docx-button.md`.

## Затрагиваемые файлы
- `backend/catalog/documents/tools.py` — тул `export_docx`, общая функция записи.
- `backend/catalog/documents/scan.py` — игнор `export/`.
- `backend/catalog/api/` (новый роут или существующий router) — `POST /export/docx`.
- `backend/scripts/golden_run.py` — шаг экспорта в конце.
- `docs/verification-checks.md` — раздел «проверки экспорта» (не text-чек реестра).
- `backend/tests/test_api.py` / scan-тесты — 200/404/409, файл в `export/`, повторный скан не индексирует.

## План действий
1. Вынести запись (render + allocate + самопроверка) в одну функцию; тул и REST — тонкие обёртки.
2. Несколько `doc_ids` — один docx с разрывами разделов; шаблон из параметра, иначе настройки, иначе дефолт.
3. Игнор `_EXPORT_DIR` в `_walk_workspace`.
4. REST + тесты 200/404/409 и регрессия скана.
5. Скилл с `allowed_tools=["export_docx"]` проходит валидацию (`registry.filter` fail-closed).
6. Golden run: экспорт в конце петли.

## Критерии приёмки (Definition of Done)
- [ ] Тул и REST пишут один и тот же файл в `export/`.
- [ ] Документ вне сессии → `document_not_available_in_session`.
- [ ] Повторный скан не подхватывает `export/*.docx`.
- [ ] Самопроверка через `extract_text` валит `ok`, если заголовки/таблицы не сошлись.
- [ ] `ruff check .`, `pytest` из `backend/`.
