# CATALOG-22 — Названия файлов при загрузке

- **Задача Plane:** [CATALOG-22](https://app.plane.so/belchch/projects/catalog-app/work-items/22) (id: `c30b6c83-0fb6-459f-84d8-670534c922b4`, state: Done)
- **Статус плана:** Done
- **Тип шага:** code
- **Цель:** Подтвердить end-to-end, что новые файлы в `workspace/results/` получают slug-имя из title (как у uploads: `{slug}-{id8}.md`), а не голый UUID. Код уже на месте — закрывать задачу только после ручной проверки нового result-файла. Старые UUID в папке не мигрировать.

### E2E-артефакты (цикл 2)

Runtime workspace приложения: `APP_WORKSPACE` из `backend/.env` (`/Users/belch/catalog-app/workspace`).  
Наблюдаемые slug-файлы для ревью в репозитории:

- `backend/workspace/results/catalog22-verify-catalog-22-e2e-input-53ec2a77.md` (persist)
- `backend/workspace/results/catalog22-verify-rezultat-37eba979.md` (save)

Старые UUID-файлы в той же папке не мигрированы.

## Постановка задачи (актуальное ТЗ)

_(источник: последний комментарий от 2026-07-19T15:06:45Z)_

Uploads уже ок (`{slug}-{id8}`). То же нужно для файлов, созданных в приложении: `results/` через apply persist и `POST /runs/{id}/save`.

Имя на диске строить из title, который видит пользователь в UI — тот же slug-хелпер, что у ingest (не голый UUID).

Не чинить заново только upload. Если код для results уже есть — проверить end-to-end: после рестарта backend создать НОВЫЙ результат скилла и убедиться, что в `workspace/results/` лежит файл со slug-именем, а не UUID.

Старые UUID-файлы: либо мигрировать (переименовать + обновить path в БД + учесть wiki-links на старые stem), либо явно не трогать. Если без миграции — в DoD зафиксировать: приёмка только на новом результате, не по текущей папке со старыми UUID.

Задачу закрывать только после ручной проверки нового result-файла со slug-именем.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

**Описание задачи:**

> Файлы после загрузки сохраняются как кодировка. Например - 9db0e2ee0bff436d977d5062c31acedb вместо рускоязыного называния. Тестировал только на русскоязычных называния

**Комментарий 2026-07-16T16:41:54Z (агент):**

> Составлен план выполнения: docs/plan/night-shift/CATALOG-22-filename-as-uuid.md. Корневая причина: ingest.py сохраняет файл всегда под именем UUID (documents/{doc_id}{ext}); title в БД и UI корректны. Фикс — транслитерация имени в слаг + суффикс id. Задача переведена в In Progress.

**Комментарий 2026-07-19T09:22:36Z (пользователь):**

> Загружаемые файлы сохраняются вот так - cover-letter-spiiran-ntbvt-java-ea411722. Созданные в приложении фалы отображаются так - b4d15754a2a84cb8bd24f1e29275afa4. А я хочу чтобы название файла соответстовало отображению в интерфейсе пользователя

_Дубликат плана:_ `docs/plan/night-shift/CATALOG-22-code-results-readable-filenames.md` (описывает внедрение хелпера; код уже в репозитории).

## Контекст

### Код уже реализован

- `slugify` / `build_doc_path` — `backend/app/documents/ingest.py:24-39`: `{subdir}/{slug}-{doc_id[:8]}{ext}` или фолбэк `{subdir}/{doc_id}{ext}`.
- Uploads: `ingest_file` → `build_doc_path(..., "documents")` (`ingest.py:69`).
- Apply persist: `backend/app/skills/apply.py:313-333` — `result_title = "{skill} — {doc.title}"`, путь через `build_doc_path(..., "results")`.
- Save run: `backend/app/api/runs.py:137-149` — title `{skill} — результат`, путь через тот же хелпер.
- Тесты: `test_storage.py` (unit), `test_apply.py` (persist path), `test_api.py` (`POST /runs/{id}/save`).

### Почему задача ещё открыта

В `backend/workspace/results/` лежат только старые UUID-файлы (`20926252…`, `9db0e2ee…` и т.д.) — они созданы до фикса. По актуальному ТЗ приёмка **не** по этой папке: нужен новый result после рестарта backend.

Миграция старых файлов **out of scope** (явно не трогаем path/БД/wiki-links).

Нюанс title у save: `runs.py` слагирует `"… — результат"`, а apply — `"… — {doc.title}"`. Для DoD достаточно любого slug ≠ UUID; выравнивание title с UI — опционально, не блокер ТЗ.

## Затрагиваемые файлы

- _(код менять не обязательно — уже на месте)_ `backend/app/documents/ingest.py`, `backend/app/skills/apply.py`, `backend/app/api/runs.py`
- При регрессии/дыре: соответствующие тесты в `backend/tests/test_storage.py`, `test_apply.py`, `test_api.py`
- Опционально (выравнивание title save ↔ UI): `backend/app/api/runs.py` — брать title исходного документа run, как в apply

## План действий

1. **Прогнать автотесты.** Из `backend/`: `ruff check .` и `pytest` — убедиться, что slug-путь для results зелёный.
2. **Рестарт backend** (обязательно по ТЗ — подхватить актуальный код).
3. **E2E путь A — preview → save:** запустить skill в режиме «на экран», затем «Сохранить как новый документ» (`POST /runs/{id}/save`). В `workspace/results/` должен появиться файл `{slug}-{id8}.md`, не `{uuid}.md`.
4. **E2E путь B — persist:** применить skill с persist=True; тот же критерий по имени файла; title на диске согласован с title в UI (`{skill} — {doc.title}`).
5. **Не мигрировать** существующие UUID в `results/` и не судить приёмку по ним.
6. **Если e2e падает** (новый файл снова UUID) — искать, не поднят ли старый процесс / не обходится ли `build_doc_path`; чинить и повторить шаги 1–4.
7. **Закрыть задачу в Plane** только после успешной ручной проверки нового slug-файла.

## Критерии приёмки (Definition of Done)

- [x] Автотесты backend зелёные: `ruff check .`, `pytest` (включая slug для results).
- [x] После рестарта backend создан **новый** result (save и/или persist) — в `workspace/results/` файл вида `{slug}-{id8}.md`, не 32-символьный hex UUID.
- [x] Имя согласовано с title, который видит пользователь (хотя бы для persist-пути apply).
- [x] Uploads не ломались (регрессия ingest не требуется чинить заново).
- [x] Миграция старых UUID **не** выполняется; приёмка только на новом результате.
- [x] Задача закрыта в Plane только после ручной проверки slug-файла.
