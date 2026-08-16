# CATALOG-67 — Word/.docx: содержимое таблиц полностью теряется при извлечении текста

- **Задача Plane:** [CATALOG-67](https://app.plane.so/belchch/projects/catalog-app/work-items/67) (id: `72bd5822-8990-41b8-8223-f6437ef3e57d`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 02 · независимый
- **Цель:** `extract_text(..., "docx")` обходит тело документа в порядке элементов и рендерит таблицы markdown-таблицами (как xlsx), включая вложенные. Документ без таблиц не меняется.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

`document.paragraphs` не включает ячейки таблиц — таблица недостатков (44 строки) теряется, агент видит только заголовок.

1. Обходить `document.element.body` в порядке `CT_P` / `CT_Tbl`, не «сначала все параграфы, потом все таблицы».
2. Рендерить таблицу markdown-таблицей, переиспользуя `_cell_to_str`.
3. Вложенные таблицы через `cell.tables`.
4. Ширина = `max(len(row.cells) for row in table.rows)`, не `table.columns` (нет `w:tblGrid` → `InvalidXmlError`).
5. Merged: дублировать текст верхней-левой ячейки (дефолт `row.cells`).
6. Колонтитулы вне scope. Лимит `MAX_TOOL_RESULT_CHARS` — CATALOG-66.

Критерии: на `defects_table_10_2025-06-09T13_36_18.docx` ≥4000 символов, шапка и `ГОСТ 31173-2016`; заголовок перед таблицей; без `tblGrid` без исключения; docx без таблиц как раньше; тесты: таблица, смесь параграф/таблица/параграф, merge.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Независимо от CATALOG-64 (ingest) и CATALOG-108 (xlsx формулы/merged в том же `extract.py` — править только docx-ветку, `_cell_to_str` не ломать).

Сейчас (`backend/catalog/documents/extract.py:18-20`):

```
document = docx.Document(path)
return "\\n".join(p.text for p in document.paragraphs)
```

xlsx уже рендерится markdown-таблицами (`extract.py:42-72`). Script-скиллы ждут этот формат (`backend/catalog/skills/script_runner.py:136`). Существующий docx-тест: `backend/tests/test_storage.py:183-184` — два параграфа без таблиц.

Фикстура `defects_table_10_…docx` в репо не найдена — положить в `backend/tests/fixtures/` (если файла нет у исполнителя — синтетическая фикстура с той же шапкой/ГОСТ и ≥4000 символов, плюс отдельный тест на реальный файл если он появится).

## Затрагиваемые файлы
- `backend/catalog/documents/extract.py` — `_extract_docx`: walk body, markdown tables, nested tables; не трогать `_extract_xlsx`.
- `backend/tests/test_storage.py` — существующий docx без таблиц остаётся зелёным.
- `backend/tests/test_api.py` или новый `backend/tests/test_extract_docx.py` — фикстуры: таблица; para→table→para; merge; без tblGrid.
- `backend/tests/fixtures/` — docx-фикстуры.

## План действий
1. Вынести обход body: для каждого child, если параграф — текст, если таблица — `_docx_table_to_md`.
2. Ширина по `row.cells`; экранирование через `_cell_to_str`; вложенные таблицы дописывать после ячейки или отдельным блоком внутри ячейки (зафиксировать в тесте).
3. Не вызывать `table.columns`.
4. Тесты + прогон `ruff` / `pytest`. Не коммитить `backend/catalog/static/`.

## Критерии приёмки (Definition of Done)
- [ ] `extract_text` на таблице недостатков (или эквивалентной фикстуре) ≥4000 символов, есть шапка и `ГОСТ 31173-2016`.
- [ ] Заголовок «Таблица недостатков» (или аналог) идёт перед таблицей.
- [ ] Файл без `w:tblGrid` не бросает исключение.
- [ ] Документ без таблиц — как раньше (`test_storage` docx).
- [ ] Тесты: таблица; смесь; merged cells.
- [ ] Зелёные: `ruff check .`, `pytest` из `backend/`.
- [ ] `backend/catalog/static/` не в коммите.
