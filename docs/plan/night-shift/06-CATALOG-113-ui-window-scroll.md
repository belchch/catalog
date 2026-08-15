# CATALOG-113 — UI: окно прокручивается — приложение уезжает за верх экрана

- **Задача Plane:** [CATALOG-113](https://app.plane.so/belchch/projects/catalog-app/work-items/113) (id: `e98020d9-745f-4285-8a4a-daea93b97a93`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 06 · независимый
- **Цель:** Документ страницы не скроллится. `document.scrollingElement.scrollTop` всегда 0; крутятся только внутренние области.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

На главном экране колесо/трекпад крутит документ: шапка уезжает, снизу белая пустота. CATALOG-99 починил ленту чата, окно всё ещё скроллится (артефакты STEPS/PROMPT).

Ожидание: скролл только у `.catalog-chat__scroll`, `.catalog-sidebar__sections`, редакторов артефактов.

Гипотезы: (1) у `html/body/#root` нет `height: 100%` / `overflow: hidden`, оболочка на `h-screen`; (2) `focus()` без `preventScroll` в `ArtifactsPanel`; (3) `100vh` vs viewport → `100dvh`.

## Предыстория
_нет — комментариев к задаче не было_

## Контекст
- `frontend/src/index.css` — нет правил на `html, body, #root`. `.catalog-shell` только цвет.
- `frontend/src/App.tsx:688` — оболочка `catalog-shell flex h-screen flex-col`. `:675` — ещё один `h-screen` (загрузка).
- `frontend/src/components/ArtifactsPanel.tsx:229-250` — `scrollIntoView` + `focus()` без `preventScroll`.
- Остальной `focus()`: `App.tsx:173` (кнопка настроек), `SettingsPanel.tsx:39,44,54`, `WorkspacePicker.tsx:202,233,236`, `SkillsPanel.tsx:208,290,358,653`, `SkillTrackPicker.tsx:34`, `DocumentCombobox.tsx:142`, `ModelCombobox.tsx:108`, `SessionTimeoutModal.tsx:28`, `RescanReportModal.tsx:15`.
- Внутренние скроллеры уже есть: чат, секции сайдбара, `artifact-editor__body`.

Независимо от 109–112: те правят сайдбар/футер, не lock документа.

## Затрагиваемые файлы
- `frontend/src/index.css` — lock `html, body, #root`; оболочка `100dvh`.
- `frontend/src/App.tsx` — `h-screen` → `h-dvh` / класс оболочки.
- `frontend/src/components/ArtifactsPanel.tsx` — `focus({ preventScroll: true })`.
- Остальные `focus()` в скроллируемых областях — `preventScroll: true`, если клик/открытие сдвигает документ.

## План действий
1. `html, body, #root { height: 100%; overflow: hidden; }`. Оболочка — `height: 100dvh` (не только `h-screen`).
2. В эффекте подсветки артефактов: `focus({ preventScroll: true })`; `scrollIntoView` оставить на ближайшем скроллере (`block: 'nearest'`).
3. Пройти остальные `focus()`: модалки — обычно ок (фокус внутри overlay); внутри списков/редакторов — `preventScroll`.
4. Проверить `lg` и табы, textarea `max-h-40`.
5. `pnpm run build`, `lint`, `typecheck`, `test`.

## Критерии приёмки (Definition of Done)
- [ ] Колесо над шапкой, сайдбаром, чатом, артефактами не меняет `document.scrollingElement.scrollTop`.
- [ ] Клик по шагу/промпту в трейсе подсвечивает секцию, окно не скроллится.
- [ ] Открытие/закрытие `SettingsPanel`, `WorkspacePicker`, `ToolsPopover` не сдвигает документ.
- [ ] Проверено на `lg` и ниже, при выросшей textarea.
- [ ] `pnpm run build`, `lint`, `typecheck`, `test` зелёные.
