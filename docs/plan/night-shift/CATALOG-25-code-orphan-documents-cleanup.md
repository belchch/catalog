# CATALOG-25 — Cleanup orphan documents

- **Задача Plane:** [CATALOG-25](https://app.plane.so/belchch/projects/catalog-app/work-items/25) (id: `816a0174-fb27-4abc-beec-e55921b8a3ef`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Убрать orphan-записи `document`, когда файл исчез из vault (Obsidian); дать DELETE API (файл + строка); определить поведение ссылок в `skill_run`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

При удалении `.md` из vault Obsidian строки в БД не чистятся. Нужны: sync/cleanup orphans (файл отсутствует → удалить/пометить в БД); API удаления документа; политика для `skill_run` ссылок.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- Только write-path: `POST /documents` → `ingest_file` — `documents.py:16-33`, `ingest.py:14-72`.
- `list_documents` / `GET /documents` — только SQLite, без проверки файла — `repo_document.py:73-78`.
- Нет `delete_document`, watcher, reconcile в `main.py` lifespan.
- `extract_text` / apply падают на отсутствующем файле, запись остаётся — `extract.py`, `tools.py:28-33`.

## Затрагиваемые файлы

- `backend/app/storage/repo_document.py` — `delete_document`, опционально `list` с exists-check.
- `backend/app/storage/schema.py` / skill_run — политика FK (nullify vs keep ids).
- `backend/app/api/documents.py` — `DELETE /documents/{id}`; endpoint или job `POST /documents/reconcile` / sync on list.
- `backend/app/main.py` — опционально периодический reconcile / startup scan.
- `backend/tests/` — orphan cleanup + delete.

## План действий

1. `delete_document`: удалить файл (если есть) + строку БД; для `skill_run` — nullify doc ids или оставить историю (зафиксировать одно).
2. `reconcile_orphans(workspace)`: для каждой строки проверить `Path(workspace)/path.exists()`; отсутствующие → delete.
3. Вызов: на `GET /documents` (лёгкий sync) и/или явный endpoint + startup.
4. `DELETE /documents/{id}` для явного удаления из UI (если UI позже — API готов).
5. Тесты: создать doc + удалить файл с диска → reconcile убирает строку; DELETE убирает файл и строку.

## Критерии приёмки (Definition of Done)

- [ ] Файл удалён из vault → после sync/reconcile нет orphan в `GET /documents`.
- [ ] `DELETE /documents/{id}` удаляет файл и запись (или 404).
- [ ] Поведение `skill_run` ссылок документировано в плане/коде и покрыто тестом.
- [ ] Чтение/apply не оставляют вечные призраки после cleanup.
- [ ] `ruff` / `pytest` зелёные.
