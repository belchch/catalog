# CATALOG-131 — code: конвертер md → docx (render_docx)

- **Задача Plane:** [CATALOG-131](https://app.plane.so/belchch/projects/catalog-app/work-items/131) (id: `5809aa77-e858-4b97-b86f-b087887329f3`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 02 · blocking CATALOG-132
- **Цель:** Чистая функция `render_docx(md) -> bytes` пишет поддерживаемое подмножество Markdown в docx; неподдерживаемое не теряется; round-trip через `extract_text` сохраняет структуру.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Новый модуль `backend/catalog/documents/export_docx.py`, симметрично `extract.py`.

- `render_docx(md: str, *, template: Path | None = None) -> bytes` через BytesIO, без ФС и БД.
- Подмножество: ATX 1–6 → Heading N; абзацы; списки → List Bullet / List Number; pipe-таблицы (первая строка header, разделитель отбросить, `\|` разэкранировать как `extract.py:214`); `**bold**` / `*italic*` / инлайн-код; fenced → monospace; `---` → разрыв.
- `template` → `docx.Document(template)` и стили заказчика; `None` — дефолт python-docx.
- Неподдерживаемая разметка падает в обычный абзац текстом.
- Wikilink: `[[Target|alias]]` → alias, `[[Target]]` / `[[Target#Heading]]` → Target; секция `## Ссылки` от `ensure_parent_wikilinks` → «Источники» (флаг вырезать); YAML-frontmatter вырезать, `title`/`author` в core properties; `![[embed]]` вне скоупа.

Вне скоупа: тул, REST, UI (CATALOG-132/133).

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Чтение docx есть, записи нет:

- `backend/catalog/documents/extract.py:6-19` — `extract_text`; docx → абзацы и таблицы как markdown.
- `backend/catalog/documents/extract.py:209-214` — `|` в ячейке экранируется как `\|`.
- `backend/catalog/documents/obsidian.py:106` — `ensure_parent_wikilinks` дописывает секцию ссылок.
- `python-docx>=1.1` уже в `backend/pyproject.toml`.

Следующий шаг (API/тул) — `docs/plan/2-shift/03-CATALOG-132-code-export-docx-api.md`.

## Затрагиваемые файлы
- `backend/catalog/documents/export_docx.py` — новый модуль, `render_docx`.
- `backend/tests/test_export_docx.py` — уровни заголовков, списки, таблица с `\|`, bold/italic, три формы wikilink, frontmatter, шаблон, round-trip.

## План действий
1. Реализовать парсер подмножества Markdown → python-docx (BytesIO).
2. Wikilink и frontmatter — до блочной вёрстки; неподдерживаемое — абзац как есть.
3. Опциональный `template`; стили Heading/Normal/Table Grid наследуются.
4. Тест round-trip: `extract_text(render_docx(md), "docx")` совпадает по заголовкам, строкам таблиц и тексту.
5. Точечные тесты из ТЗ.

## Критерии приёмки (Definition of Done)
- [ ] `render_docx` возвращает bytes открываемого docx без записи на диск.
- [ ] Неподдерживаемая разметка не пропадает.
- [ ] Round-trip через `extract_text(..., "docx")` сохраняет структуру.
- [ ] Тесты из ТЗ зелёные.
- [ ] `ruff check .`, `pytest` из `backend/`.
