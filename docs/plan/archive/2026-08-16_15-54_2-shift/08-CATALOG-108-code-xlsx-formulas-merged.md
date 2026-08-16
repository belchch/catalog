# CATALOG-108 — XLSX: формулы без кэшированных значений и объединённые ячейки теряются при извлечении

- **Задача Plane:** [CATALOG-108](https://app.plane.so/belchch/projects/catalog-app/work-items/108) (id: `1cfb48db-d047-4fe1-9c54-68dddf605e0b`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 08 · независимый
- **Цель:** `_extract_xlsx` не глотает формулы без кэша и merged-ячейки: видно значение или текст формулы; merged шапка заполняет все колонки. Существующие xlsx-тесты зелёные.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

`load_workbook(..., read_only=True, data_only=True)` даёт пустые формулы без кэша и пустые хвосты merge.

1. Два прохода: `data_only=True` за значениями, `data_only=False` за формулами; нет кэша → текст формулы или явный маркер.
2. Разворачивать `merged_cells.ranges` (нужен отказ от `read_only=True`; при больших файлах — разворот только если merge есть).
3. Не ломать `test_extract_xlsx` и `test_extract_xlsx_escapes_pipes_and_newlines`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Независимо от CATALOG-67 (править только `_extract_xlsx`, не docx). `_cell_to_str` (`extract.py:100-105`) оставить общим.

Сейчас (`extract.py:46`): `read_only=True, data_only=True`, `iter_rows(values_only=True)` — merge и формулы без кэша → `None`. Тесты: `backend/tests/test_api.py:238-263`.

## Затрагиваемые файлы
- `backend/catalog/documents/extract.py` — `_extract_xlsx`.
- `backend/tests/test_api.py` — новые кейсы формула без кэша и merged A1:C1; старые xlsx-тесты.

## План действий
1. Загрузка без `read_only` (или два режима). Значение = cached or formula string.
2. Для каждого merge-диапазона скопировать верхнюю-левую ячейку на весь диапазон **после** выбора cached/formula.
3. Фикстуры через openpyxl в тесте (не обязательно бинарники в git).
4. `ruff` / `pytest`. Не коммитить `backend/catalog/static/`.

## Критерии приёмки (Definition of Done)
- [ ] Формула без кэша → значение или текст формулы, не пустая ячейка.
- [ ] Merged A1:C1 → значение во всех трёх колонках шапки.
- [ ] Экранирование `|` и переносов не регрессирует.
- [ ] Зелёные: `ruff check .`, `pytest` из `backend/`.
- [ ] `backend/catalog/static/` не в коммите.
