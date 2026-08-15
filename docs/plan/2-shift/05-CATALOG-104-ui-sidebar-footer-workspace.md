# CATALOG-104 — UI: убрать дубли в шапке сайдбара, перенести воркспейс в футер

- **Задача Plane:** [CATALOG-104](https://app.plane.so/belchch/projects/catalog-app/work-items/104) (id: `566bcf15-9478-4276-b17b-35c2ba740f22`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 05 · blocking CATALOG-105
- **Цель:** Один «Catalog» в header, одно имя папки — в закреплённом футере сайдбара. Brand-строка и `WorkspaceBar` удаляются; функции бара переезжают в `WorkspaceFooter`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

Тип UI, нужна дизайн-спека. Удалить brand-строку; удалить `WorkspaceBar`, перенести функции в футер `frontend/src/components/WorkspaceFooter.tsx`; скролл с `aside` на секции; оживить плашку футера. Сохранить: клик по строке → пикер; рескан отдельной icon-кнопкой (не вложенный button); `RefreshIcon`/`SpinnerIcon`, `aria-busy`, `disabled` при rescan, `hasWorkspace`; `title` с полным путём. Кнопку «Открыть папку» из empty `WorkspaceBar` не переносить. Текст плашки — `folderLabel`, не полный путь. Скролл: `aside` `overflow-hidden min-h-0`; `.catalog-sidebar__sections` `flex:1; min-height:0; overflow-y:auto`; у футера убрать `margin-top:auto`, отрицательные горизонтальные margin оставить. Аватар `C` → `▱`; hover full-bleed; имя `--ink` вес 600; паддинг 10–12px; живой `⌄`. Удалить мёртвый CSS brand/chevron/project-title/avatar; не удалять `.catalog-mark` и `--mark-bg`. Метку «Проект» удалить.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Независимо от CATALOG-64. Предусловие для CATALOG-105 (типографика считает, что блока «Проект» и скролла на aside уже нет).

Сейчас: brand `App.tsx:678-682`, метка «Проект» `:696`, `WorkspaceBar` `:697-703`, футер `:785-792` с `display_name || path`, `aside` `overflow-y-auto` `:677`. `folderLabel` уже в `WorkspaceBar.tsx:11-16`. CSS: `index.css:248-277`.

Главный риск ТЗ: раскладка `<lg` (`grid-cols-1`) — футер/секции могут схлопнуться.

## Затрагиваемые файлы
- `frontend/src/App.tsx` — убрать brand, метку, `WorkspaceBar`; aside overflow; подключить `WorkspaceFooter`.
- `frontend/src/components/WorkspaceFooter.tsx` — новый.
- `frontend/src/components/WorkspaceBar.tsx` — удалить после переноса `folderLabel`.
- `frontend/src/index.css` — скролл секций, футер, удалить мёртвые селекторы.

## План действий
1. Вынести `folderLabel` + кликабельная плашка + рескан в `WorkspaceFooter`.
2. Собрать сайдбар: поиск и «Новый чат» как шапка, секции скроллятся, футер pinned.
3. Стили плашки по ТЗ; почистить CSS.
4. Проверить `<lg` глазами (критерий в дизайн-спеке). Frontend-проверки.

## Критерии приёмки (Definition of Done)
- [ ] «Catalog» в UI один раз — в верхнем header.
- [ ] Имя папки в сайдбаре один раз — в футере (`folderLabel`, путь в `title`).
- [ ] Футер закреплён, не уезжает со скроллом секций.
- [ ] Клик по плашке открывает пикер; рескан со спиннером; пустой воркспейс — «Папка не открыта», кликабельно.
- [ ] В `index.css` нет перечисленных мёртвых селекторов.
- [ ] Зелёные: `pnpm run build`, `lint`, `typecheck`, `test` из `frontend/`.
