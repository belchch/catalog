# CATALOG-65 — Поддержка ingest PDF / CSV / XLSX: загрузка, извлечение текста, доступ агенту и script-скилам

- **Задача Plane:** [CATALOG-65](https://app.plane.so/belchch/projects/catalog-app/work-items/65) (id: `ac31e9bf-e44a-498d-8b7a-9d9eaed4c225`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Расширить backend-ingest и extract_text для форматов PDF, CSV, XLSX, чтобы пользователь мог загружать эти документы и модель/script-скилы получали осмысленную текстовую проекцию.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — комментариев к задаче не было)_

**Контекст**
Сейчас документы ограничены `.md` и `.docx` (ADR-0010 отложил pdf/xlsx). Ограничения стоят в трёх местах: UI (`accept`), ingest (`_EXT_TO_KIND`), `extract_text`. Модель и script-скилы видят только plain text после extract — бинарники Excel/PDF в песочницу не передаются.
Нужно закрыть ближайший шаг из ADR-0010 п.3: ingest PDF/XLSX (+ CSV) с нормальной текстовой проекцией для агента/script.

**Цель**
Пользователь загружает `.pdf`, `.csv`, `.xlsx`. Документ сохраняется в workspace как сейчас; при `read_document` / apply skill содержимое доступно как текст (для таблиц — markdown/TSV), достаточный для анализа моделью и детерминированных script-скилов.

**Backend scope (этот план):**
1. Расширить `kind_for_filename` / `_EXT_TO_KIND` в `backend/app/documents/ingest.py`: минимум `pdf`, `csv`, `xlsx`.
2. Расширить `extract_text` в `backend/app/documents/extract.py`:
   - **csv** — UTF-8 (с fallback на cp1251/latin-1 при decode error); текст как есть.
   - **xlsx** — все листы; ячейки → markdown-таблица; пустые строки/хвосты не раздувать.
   - **pdf** — текстовый слой (не OCR); страницы разделены маркером (`\n\n--- page N ---\n\n`); сканы без текста → понятная ошибка/пустой extract с явным сообщением, не silent fail.
3. Зависимости в `backend/pyproject.toml`: `pypdf` для PDF; `openpyxl` для xlsx. CSV — stdlib.
4. API `POST /documents`: те же 400 на неподдерживаемый формат; новые форматы проходят ingest и возвращают корректный `kind`.
5. Тесты: upload каждого формата; `extract_text` на фикстурах; регрессия md/docx.

**Out of scope:** OCR, `.xls` (BIFF), `pandas` в sandbox, запись обратно в xlsx/pdf, полноценная hardening (размер/zip-bomb).

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

Текущая реализация поддерживает только `.md` и `.docx`:
- `backend/app/documents/ingest.py:11` — `_EXT_TO_KIND = {".md": "md", ".docx": "docx"}`
- `backend/app/documents/extract.py:6-18` — `extract_text()` обрабатывает только `md`/`result_md`/`docx`, остальные kinds бросают `ValueError`
- `backend/app/api/documents.py:22-25` — `upload_document` ловит `ValueError` от `kind_for_filename` и возвращает 400 (этот механизм уже работает)
- `backend/app/documents/tools.py:42` — `read_document` tool вызывает `extract_text` по `row.kind`, контракт не меняется
- `backend/pyproject.toml:13` — зависимости: `python-docx` для docx, новых зависимостей для pdf/xlsx нет
- `backend/tests/test_api.py:138-143` — `test_upload_unsupported_format` проверяет, что `bad.pdf` даёт 400 (после реализации этот тест нужно обновить — `.pdf` станет поддерживаемым)
- `docs/adr/0010-first-slice-scope.md:19` — pdf/xlsx числятся в non-goals среза, п.3 ближайших шагов: «pdf/xlsx ingest»

Парный UI-план: `docs/plan/next-shift/CATALOG-65-ui-pdf-csv-xlsx-accept.md` (выполняется после этого).

## Затрагиваемые файлы

- `backend/app/documents/ingest.py` — расширить `_EXT_TO_KIND` (добавить `.pdf`, `.csv`, `.xlsx`)
- `backend/app/documents/extract.py` — добавить ветки `csv`, `xlsx`, `pdf` в `extract_text`
- `backend/pyproject.toml` — добавить `pypdf`, `openpyxl` в dependencies
- `backend/tests/test_api.py` — обновить `test_upload_unsupported_format` (pdf больше не unsupported); добавить тесты upload/extract для csv, xlsx, pdf
- `backend/tests/fixtures/` (новая директория) — минимальные фикстурные файлы: `sample.csv`, `sample.xlsx`, `sample-text.pdf`, `sample-scan.pdf` (скан без текста)

## План действий

1. Добавить зависимости в `backend/pyproject.toml`: `pypdf>=4.0` и `openpyxl>=3.1` в список `dependencies`.
2. В `backend/app/documents/ingest.py:11` расширить `_EXT_TO_KIND`: добавить `".pdf": "pdf"`, `".csv": "csv"`, `".xlsx": "xlsx"`.
3. В `backend/app/documents/extract.py` реализовать три новые ветки в `extract_text`:
   - `csv`: открыть с `encoding="utf-8"`, при `UnicodeDecodeError` retry с `cp1251`, затем `latin-1`. Вернуть содержимое как есть.
   - `xlsx`: через `openpyxl.load_workbook(path, read_only=True)`. Итерировать все листы, для каждого — собрать непустые строки в markdown-таблицу. Листы разделены заголовком `## Sheet: <name>`. Пропустить полностью пустые листы.
   - `pdf`: через `pypdf.PdfReader(path)`. Итерировать страницы, извлекать текст через `extract_text()`. Страницы разделены `\n\n--- page N ---\n\n`. Если суммарный текст пуст (скан) — вернуть строку-предупреждение, а не пустую строку.
4. Создать минимальные фикстурные файлы в `backend/tests/fixtures/`:
   - `sample.csv` — простая таблица UTF-8 (2-3 строки, русские символы).
   - `sample.xlsx` — файл с двумя листами, один с данными, один пустой.
   - `sample-text.pdf` — PDF с текстовым слоем (минимум 2 страницы).
   - `sample-scan.pdf` — PDF-файл без извлекаемого текста (можно пустой или с картинкой).
5. В `backend/tests/test_api.py`:
   - Обновить `test_upload_unsupported_format`: заменить `bad.pdf` на `bad.exe` (или другой неподдерживаемый формат).
   - Добавить `test_upload_csv`, `test_upload_xlsx`, `test_upload_pdf` — проверка 200 и корректного `kind`.
   - Добавить `test_extract_csv`, `test_extract_xlsx`, `test_extract_pdf`, `test_extract_pdf_scan` — прямые вызовы `extract_text` на фикстурах.
6. Запустить `ruff check .` и `pytest` — всё зелёное, включая регрессию существующих тестов md/docx.

## Критерии приёмки (Definition of Done)

- [ ] `_EXT_TO_KIND` содержит `.pdf`, `.csv`, `.xlsx`
- [ ] `extract_text` обрабатывает `csv`, `xlsx`, `pdf` без ошибок на валидных файлах
- [ ] CSV с UTF-8 и cp1251 извлекается корректно (fallback работает)
- [ ] XLSX: все листы с данными представлены как markdown-таблицы с заголовком листа
- [ ] PDF с текстом: постраничное извлечение с маркерами страниц
- [ ] PDF-скан: возвращает осмысленное сообщение об отсутствии текста, не падает
- [ ] `POST /documents` принимает pdf/csv/xlsx, возвращает корректный kind
- [ ] `POST /documents` отклоняет неподдерживаемые форматы с 400
- [ ] `pytest` зелёный, включая новые тесты и регрессию md/docx
- [ ] `ruff check .` без ошибок
- [ ] Парный UI-план: `docs/plan/next-shift/CATALOG-65-ui-pdf-csv-xlsx-accept.md`