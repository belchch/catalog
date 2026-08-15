# CATALOG-110 — UI: нормальная иконка папки вместо глифа ▱ во всех местах

- **Задача Plane:** [CATALOG-110](https://app.plane.so/belchch/projects/catalog-app/work-items/110) (id: `a97a0a4a-6a6d-4c1e-a836-e7dfb3d9c22f`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 02 · blocking CATALOG-111
- **Цель:** Заменить глиф `▱` на SVG `FolderIcon` во всех четырёх местах. Символа в `frontend/src` не остаётся.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: UI. Нужна дизайн-спека.

Папка обозначена `▱` (U+25B1): разный рендер по шрифтам, не стыкуется с SVG из `icons.tsx`. Четыре места: шапка, пустое `main`, футер сайдбара, список папок в пикере.

Что сделать:

- Добавить `FolderIcon` в `icons.tsx` по `iconBase` (viewBox 0 0 24 24, stroke currentColor, strokeWidth 1.75, round caps, aria-hidden, `className`).
- Заменить `▱` в `App.tsx` (шапка и пустое main), `WorkspaceFooter.tsx`, `WorkspacePicker.tsx`.
- В пустом main — явный размер ~32–36px, не 16px из `iconBase`.
- Судьбу маркера в шапке (оставить декоративным или убрать) зафиксировать в дизайн-спеке.
- Почистить `.catalog-header__folder` (`font-size: 1.35rem` для текста).

## Предыстория
_нет — комментариев к задаче не было_

## Контекст
Актуальные строки (сдвинулись относительно ТЗ):

- `frontend/src/App.tsx:691` — шапка, `span.catalog-header__folder` с `▱`.
- `frontend/src/App.tsx:861-863` — пустое main, `text-3xl` + `▱`.
- `frontend/src/components/WorkspaceFooter.tsx:38-43` — `text-[18px]` + `▱`.
- `frontend/src/components/WorkspacePicker.tsx:574` — `▱` в строке папки.
- `frontend/src/index.css:233` — `.catalog-header__folder { font-size: 1.35rem }` — для SVG бесполезно.
- `frontend/src/components/icons.tsx:4-16` — общий `iconBase` 16×16.

Парный план CATALOG-111 перерабатывает футер **после** этой замены (`110 blocking 111`). Здесь только иконка, без типографики/стрелки/hover футера.

Рекомендация для дизайн-спеки: маркер в шапке оставить как декоративный `FolderIcon` (без имени папки) — иначе шапка теряет якорь; имя папки живёт в футере.

## Затрагиваемые файлы
- `frontend/src/components/icons.tsx` — новый `FolderIcon`.
- `frontend/src/App.tsx` — шапка и пустое main.
- `frontend/src/components/WorkspaceFooter.tsx` — глиф → иконка, размер ~18px.
- `frontend/src/components/WorkspacePicker.tsx` — строка папки, `shrink-0`.
- `frontend/src/index.css` — убрать/заменить правила под текстовый глиф.

## План действий
1. Нарисовать `FolderIcon` в том же штрихе, что `RefreshIcon`/`SettingsIcon`.
2. Заменить все четыре `▱`. В пустом main: `className` ~`size-9` (36px). В футере и пикере: `size-[18px]` / `size-4` + `shrink-0`.
3. В дизайн-спеке зафиксировать: шапка — декоративный маркер, не дублирует имя папки.
4. Переписать `.catalog-header__folder` под SVG (цвет через `currentColor` / `--header-folder`), без `font-size`.
5. Поиск `▱` по `frontend/src` — ноль совпадений. Имена кнопок не менять.
6. `pnpm run build`, `lint`, `typecheck`, `test`.

## Критерии приёмки (Definition of Done)
- [ ] Символа `▱` в `frontend/src` нет.
- [ ] `FolderIcon` согласован с `RefreshIcon`/`SettingsIcon`, цвет через `currentColor`.
- [ ] В пустом main иконка ~32–36px.
- [ ] Все вхождения `aria-hidden`; доступные имена кнопок не изменились.
- [ ] В пикере `truncate` работает, иконка `shrink-0`.
- [ ] В `index.css` нет правил, завязанных на текстовый глиф папки.
- [ ] `pnpm run build`, `lint`, `typecheck`, `test` зелёные.
