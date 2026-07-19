# CATALOG-54 — Добавить красивое отображение md

- **Задача Plane:** [CATALOG-54](https://app.plane.so/belchch/projects/catalog-app/work-items/54) (id: `bdc3debe-b510-4340-802a-eccce02aaeed`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** Красивый рендер Markdown с переключателем режимов **md / text** там, где сейчас сырой текст (прежде всего сообщения чата и/или блок результата), без новой MD-библиотеки — использовать уже подключённые `react-markdown` + `remark-gfm`.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи)_

Сейчас просто текст. И переключатель режимов — md / text.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

| Место | Сейчас |
|---|---|
| `RunView` результат | Уже `ReactMarkdown` + `remarkGfm` (`RunView.tsx:127-129`), стили `.run-markdown` в `index.css:5-52`. **Нет** переключателя md/text. |
| `ChatMessage` | Plain `whitespace-pre-wrap` (`ChatMessage.tsx:18-19`, `:39-40`) — «просто текст». |
| Documents preview | Нет viewer контента документа. |

Зависимости уже есть: `frontend/package.json` — `react-markdown`, `remark-gfm`.

Фокус ТЗ: (1) красивый MD, (2) toggle md/text. Минимальный охват — assistant-сообщения в чате + toggle на результате RunView (где MD уже есть, но без text-режима). Общий компонент предпочтительнее копипасты.

## Затрагиваемые файлы

- `frontend/src/components/MarkdownView.tsx` — **новый** (рендер + toggle md/text, переиспользует `.run-markdown` или общий класс)
- `frontend/src/components/ChatMessage.tsx` — assistant (и при желании user) через MarkdownView
- `frontend/src/components/RunView.tsx` — toggle над результатом
- `frontend/src/index.css` — при необходимости обобщить стили (`.run-markdown` → `.md-body`)

## План действий

1. **Компонент `MarkdownView`.** Props: `text`, опционально `defaultMode: 'md' | 'text'`. UI: сегмент/кнопки md|text; md → `ReactMarkdown`+`remarkGfm`; text → `<pre>`/pre-wrap.
2. **Чат.** В `ChatMessage` для assistant заменить plain div на `MarkdownView` (default md). Tool-строки оставить plain.
3. **RunView.** Обернуть результат в тот же компонент с toggle (default md).
4. **Стили.** Переиспользовать/расширить `.run-markdown` для чата (размеры под пузырь).
5. **Проверки.** lint/typecheck/build; ручной: сообщение с заголовками/списком/кодом; переключение md↔text.

## Критерии приёмки (Definition of Done)

- [ ] Есть переключатель md / text на поверхностях с markdown-контентом (чат assistant и результат run).
- [ ] Режим md рендерит headings, lists, code, tables (GFM) читабельно.
- [ ] Режим text показывает исходник без интерпретации разметки.
- [ ] Новых MD-зависимостей нет (только существующие `react-markdown` / `remark-gfm`).
- [ ] `frontend/`: `pnpm run lint`, `typecheck`, `build` зелёные.
- [ ] Соответствие дизайн-спеке UI-шага.
