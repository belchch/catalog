# CATALOG-111 — UI: переработать нижнюю плашку воркспейса в сайдбаре

- **Задача Plane:** [CATALOG-111](https://app.plane.so/belchch/projects/catalog-app/work-items/111) (id: `415c743c-00b5-4ed8-a842-6099b2f6cd9e`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 03 · blocked_by CATALOG-110
- **Цель:** Сделать футер сайдбара тихой статусной строкой: без стрелки, без full-bleed hover, с понятными aria-именами. Делать после CATALOG-110.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: UI. Нужна дизайн-спека. Зависит от задачи про `FolderIcon` — делать после неё.

Плашка чужеродная: стрелка `⌄`, `font-semibold`, `py-[11px]`, full-bleed `margin: 0 -12px -12px` / `rounded-none`. Рескан «Пересканировать» без объекта. `aria-label` плашки = имя папки, без смысла «выбор воркспейса».

Что сделать: убрать стрелку; вес обычный/средний; паддинг 8–9px; hover/фокус как у `.catalog-new-chat`; явная раскладка трёх состояний; рескан «Пересканировать папку»; контекст в aria плашки; обновить тесты.

## Предыстория
_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/night-shift/02-CATALOG-110-ui-folder-icon.md` — в футере уже `FolderIcon`, не `▱`.

Сейчас:

- `frontend/src/components/WorkspaceFooter.tsx:30-57` — кнопка пикера: `rounded-none py-[11px] pl-5 pr-3 text-sm font-semibold`, глиф, `ml-auto` стрелка `⌄`, `aria-label={label}`.
- Там же `:58-74` — рескан только при `hasWorkspace`, `aria-label="Пересканировать"`.
- `frontend/src/index.css:260-265` — `.catalog-new-chat`: `width: calc(100% - 16px); margin: 0 8px 16px; padding: 8px 11px; border-radius: 9px`.
- `frontend/src/index.css:274-278` — `.catalog-sidebar__footer`: `margin: 0 -12px -12px` (full-bleed).
- `frontend/src/components/WorkspaceFooter.test.tsx:21,40,58` — имя «Пересканировать»; `:19` — имя плашки «Папка не открыта».
- Старая спека: `docs/plan/2-shift/05-CATALOG-104-ui-sidebar-footer-workspace.design.md`.

`aside` уже `overflow-hidden` (`App.tsx:730`) — фокус-кольцо нельзя сажать на кромку.

## Затрагиваемые файлы
- `frontend/src/components/WorkspaceFooter.tsx`
- `frontend/src/components/WorkspaceFooter.test.tsx`
- `frontend/src/index.css` — `.catalog-sidebar__footer`
- `docs/plan/2-shift/05-CATALOG-104-ui-sidebar-footer-workspace.design.md` — синхронизировать устаревшие критерии.

## План действий
1. Удалить стрелку `⌄`. Раскладка: иконка + `truncate` имя + слот рескана фиксированной ширины (пустой, если нет воркспейса), чтобы высота/ширина не прыгали.
2. Типографика: не выше `font-medium`; вертикальный паддинг 8–9px.
3. Убрать отрицательные маржины футера. Hover/радиус как у «Новый чат» (инсет 8px, `border-radius: 9px` / `--radius-control`).
4. `aria-label` плашки: «Выбрать воркспейс: {label}» (или эквивалент); `aria-haspopup="dialog"` оставить.
5. Рескан: `aria-label`/`title` = «Пересканировать папку»; `aria-busy`/`disabled`/`SpinnerIcon` без изменений поведения.
6. Обновить тесты под новые имена. Поправить критерии в спеке CATALOG-104.
7. `pnpm run build`, `lint`, `typecheck`, `test`.

## Критерии приёмки (Definition of Done)
- [ ] Стрелки `⌄` нет; клик по строке открывает пикер, клик по рескану — нет.
- [ ] Вес не выше среднего, вертикальный паддинг 8–9px.
- [ ] Hover/фокус согласованы с «Новый чат»; кольцо не подрезано `aside`.
- [ ] Высота/ширина футера стабильны: нет папки / есть папка / рескан.
- [ ] Длинное имя — одна строка с многоточием.
- [ ] Без воркспейса: «Папка не открыта» приглушённо, рескана нет, плашка кликабельна.
- [ ] Доступное имя плашки говорит про выбор воркспейса; `aria-haspopup="dialog"`.
- [ ] Рескан: `aria-busy`, `disabled`, `SpinnerIcon`; отчёт в `RescanReportModal`.
- [ ] Ниже `lg` сайдбар скрыт, второй полосы прокрутки нет.
- [ ] `WorkspaceFooter.test.tsx` обновлён; проверки frontend зелёные.
- [ ] Критерии в `05-CATALOG-104-ui-sidebar-footer-workspace.design.md` приведены к новому решению.
