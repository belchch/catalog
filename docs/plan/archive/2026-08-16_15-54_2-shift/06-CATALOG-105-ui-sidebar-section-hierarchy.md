# CATALOG-105 — UI: типографическая иерархия и разделители секций сайдбара

- **Задача Plane:** [CATALOG-105](https://app.plane.so/belchch/projects/catalog-app/work-items/105) (id: `d881a287-344f-4455-8e33-5a6ce6ab61a8`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 06 · blocked_by CATALOG-104 · blocking CATALOG-106
- **Цель:** Заголовки секций сайдбара — eyebrow как в main; воздух между секциями; линии только если воздуха мало и без разреза hover/focus.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

Тип UI, дизайн-спека. Blocked by каркас сайдбара (CATALOG-104).

`.catalog-section-header__title` → 11px / 600 / letter-spacing ~.05em / uppercase / `--ink-faint` (как `text-[11px] uppercase tracking-wide text-ink-faint` в Chat/Artifacts/RunView). Регистр только CSS. Gap секций 2px → ~10px; линии — псевдоэлемент `> * + *` с отбивкой 8px, не `border-top` на секции. Шов к блоку проекта не нужен.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/2-shift/05-CATALOG-104-ui-sidebar-footer-workspace.md`. Предусловие для CATALOG-106 (sticky/z-index над разделителями).

Сейчас заголовок 14px/500 `--sidebar-ink` (`index.css:284-287`), gap 2px (`:272`). DOM `CollapsibleSection.tsx:33` — текст «Сессии» и т.д. не менять. ТЗ: правки только в `index.css`.

## Затрагиваемые файлы
- `frontend/src/index.css` — title eyebrow, gap, опционально разделители.

## План действий
1. После 104: стили title как eyebrow.
2. Gap ~10px; линии — только если в дизайн-спеке решено, что воздуха мало.
3. Не трогать JSX. Frontend-проверки.

## Критерии приёмки (Definition of Done)
- [ ] Заголовки секций тише содержимого и однотипны.
- [ ] Шкала: футер громче списков, списки громче заголовков.
- [ ] Текст заголовков в DOM без изменения регистра.
- [ ] Разделители (если есть) не режут hover и focus-ring.
- [ ] Зелёные: `pnpm run build`, `lint`, `typecheck`, `test` из `frontend/`.
