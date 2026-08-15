# CATALOG-106 — UI: снизить визуальный шум секций сайдбара

- **Задача Plane:** [CATALOG-106](https://app.plane.so/belchch/projects/catalog-app/work-items/106) (id: `82a385d0-5bf9-442d-bcc4-1ca62e03aa92`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 07 · blocked_by CATALOG-105
- **Цель:** Кнопки в заголовках секций — только hover/focus-within (на таче всегда видны); счётчики; общий класс icon-кнопок с футером; sticky-заголовки в скролле секций.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

Тип UI. Делать после типографики. Blocked by CATALOG-105.

1. Actions по hover: `opacity`, не `display:none`; `focus-within`; `@media (hover: hover)`; класс на обёртку в `CollapsibleSection.tsx:36`.
2. Счётчики рядом с названием — `badge-neutral`.
3. Общий класс icon-кнопок: рескан в футере и кнопки заголовков.
4. Sticky: `position: sticky; top: 0; background: var(--sidebar)`; z-index выше разделителей 105.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/2-shift/06-CATALOG-105-ui-sidebar-section-hierarchy.md` (и транзитивно 104: скролл на `.catalog-sidebar__sections`, `WorkspaceFooter`).

Actions сейчас всегда видны (`App.tsx:709-772`, `CollapsibleSection.tsx:35`). Счётчиков нет — прокинуть `count` в `CollapsibleSection` из длин сессий/доков/скилов.

## Затрагиваемые файлы
- `frontend/src/components/CollapsibleSection.tsx` — класс actions, optional `count`.
- `frontend/src/App.tsx` — передать counts.
- `frontend/src/components/WorkspaceFooter.tsx` — общий icon-класс (после 104).
- `frontend/src/index.css` — hover-opacity, sticky, icon-класс.

## План действий
1. После 105: hover-actions + media hover.
2. `count` в заголовок через `badge-neutral`.
3. Вынести icon-кнопку в один CSS-класс, применить в футере и секциях.
4. Sticky на `.catalog-section-header`. Frontend-проверки.

## Критерии приёмки (Definition of Done)
- [ ] В покое на hover-устройствах кнопок в заголовках нет; на таче доступны.
- [ ] Ширина заголовка не прыгает при появлении кнопок.
- [ ] Sticky не просвечивает и не перекрывается разделителем.
- [ ] Зелёные: `pnpm run build`, `lint`, `typecheck`, `test` из `frontend/`.
