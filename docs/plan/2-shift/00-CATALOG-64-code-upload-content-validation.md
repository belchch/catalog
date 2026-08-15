# CATALOG-64 — Загрузка файлов: проверять содержимое и давать внятную ошибку формата (.xls / .ods / .tsv)

- **Задача Plane:** [CATALOG-64](https://app.plane.so/belchch/projects/catalog-app/work-items/64) (id: `25aa4eec-1564-4016-8896-e1146283941e`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 00 · независимый
- **Цель:** На `POST /documents` отвергать неподдерживаемые и битые файлы до записи в воркспейс/БД: человекочитаемый `detail` для `.xls`/`.ods`/`.tsv` и проверка содержимого (magic bytes + попытка открыть). Существующие валидные форматы не ломать.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

Остаток тикета после аудита загрузки: валидация и понятные ошибки.

1. Проверять содержимое при загрузке: magic bytes и попытку открыть файл (openpyxl для xlsx, decode для csv) в try/except. При неудаче — 4xx с человекочитаемым `detail`, файл в воркспейс не писать и запись в БД не создавать.
2. Заменить generic `unsupported format: .xls` на подсказку: «Формат .xls не поддерживается — пересохраните файл как .xlsx». То же для `.ods` и `.tsv`.
3. Frontend-часть (accept + показ `detail`) — в парном UI-плане.
4. Вне scope: лимит размера файла.

Критерии: `.xls`/`.ods`/`.tsv` → подсказка; битый `.xlsx` → ошибка при загрузке, файла нет в воркспейсе/списке; валидные `.xlsx`/`.csv`/`.md`/`.docx`/`.pdf` как раньше; тесты на битый xlsx, `.xls`, пустой csv; `ruff` + `pytest`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Парный UI-план: `docs/plan/2-shift/01-CATALOG-64-ui-upload-format-errors.md`. Этот `code`-план — предусловие для UI (контракт `detail`).

Сейчас `kind_for_filename` смотрит только расширение (`backend/catalog/documents/ingest.py:20-26`). Whitelist: `.md/.docx/.pdf/.csv/.xlsx` (`ingest.py:11-17`). `upload_document` ловит `ValueError` → 400 (`backend/catalog/api/documents.py:21-24`), затем `ingest_file` пишет байты на диск и создаёт строку в БД (`ingest.py:81-93`) без проверки содержимого.

Битый `broken.xlsx` проходит 200 и падает позже при чтении (`BadZipFile`). `test_upload_unsupported_format` (`backend/tests/test_api.py:157-162`) и `test_unsupported_format_raises` (`backend/tests/test_storage.py:187-189`) завязаны на generic `unsupported` / `ValueError` — обновить под новые тексты для `.xls/.ods/.tsv`, для прочих расширений оставить generic.

Пустой csv: решить явно — пустой, но декодируемый файл принимать (это валидный csv) либо отвергать, если нет ни одной строки; в тесте зафиксировать выбранное поведение. ТЗ просит тест «пустой csv», не обязательно 4xx.

## Затрагиваемые файлы
- `backend/catalog/documents/ingest.py` — сообщения для `.xls/.ods/.tsv`; `validate_content(kind, content)` до записи на диск; вызов из `ingest_file`.
- `backend/catalog/api/documents.py` — прокинуть `ValueError` из валидации содержимого в 400 (сейчас ловится только `kind_for_filename`; `ingest_file` может бросить позже — обернуть весь upload).
- `backend/tests/test_api.py` — `.xls` с подсказкой; битый xlsx → 400 и нет в `GET /documents`; пустой csv.
- `backend/tests/test_storage.py` — ingest битого xlsx не создаёт файл/строку; `.xls` бросает с подсказкой.

## План действий
1. В `kind_for_filename` для `.xls`, `.ods`, `.tsv` бросать `ValueError` с текстом-подсказкой (пересохранить в `.xlsx` / `.csv`). Остальные неизвестные расширения — как сейчас.
2. Добавить `validate_content`: xlsx — zip/magic + `openpyxl.load_workbook` (BytesIO); csv — decode utf-8-sig/cp1251/latin-1 как в `extract.py:34-39`; docx/pdf — минимальная попытка открыть; md — не падать на любых байтах (или utf-8/latin-1). Не вызывать полный `extract_text` (это CATALOG-67/108).
3. В `ingest_file` валидировать **до** `dest.write_bytes` и `create_document`. При ошибке не оставлять частичный файл.
4. В `upload_document` обернуть `ingest_file` в тот же `HTTPException(400, detail=str(exc))`.
5. Тесты: `.xls`/`.ods`/`.tsv` → 400 и подсказка в `detail`; битый xlsx → 400, нет файла, нет id в списке; пустой csv — зафиксировать поведение; существующие upload-тесты зелёные.
6. Не коммитить `backend/catalog/static/`.

## Критерии приёмки (Definition of Done)
- [ ] `.xls` / `.ods` / `.tsv` → 400 с подсказкой пересохранить; файл не появляется в воркспейсе и в `GET /documents`.
- [ ] Битый файл с расширением `.xlsx` → 400; файла нет на диске и в БД.
- [ ] Корректные `.xlsx` / `.csv` / `.md` / `.docx` / `.pdf` грузятся как раньше.
- [ ] Есть тесты: битый xlsx, `.xls`, пустой csv.
- [ ] `test_upload_unsupported_format` / `test_unsupported_format_raises` зелёные (generic или новые тексты — согласованы).
- [ ] Зелёные: `ruff check .`, `pytest` из `backend/`.
- [ ] `backend/catalog/static/` не в коммите.
