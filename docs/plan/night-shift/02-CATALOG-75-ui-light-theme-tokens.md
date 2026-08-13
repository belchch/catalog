# CATALOG-75 — Светлая тема: единая система токенов, убрать слой переопределений Tailwind

- **Задача Plane:** [CATALOG-75](https://app.plane.so/belchch/projects/catalog-app/work-items/75) (id: `82b6bf78-4705-407d-98c6-ca39406ca1bd`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 02 · независимый
- **Цель:** Довести уже прижившийся светлый визуал до продакшн-качества: перевести компоненты на семантические токены и удалить двойной слой, где кастомный CSS перекрашивает тёмные Tailwind-утилиты по неполному списку. Визуальный язык не менять.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — комментариев не было)_

Светлая тема остаётся целевой (белый фон, сайдбар `#eef7ff`, карточки 20–24px + мягкая тень, акцент `#1d83c4`). Реализация черновая: компоненты написаны в `slate-*` / `indigo-*`, светлая тема накинута блоком переопределений в `index.css`.

Устранить четыре корневые причины:

1. Перекраска по списку принципиально неполна — любая утилита вне списка рендерится тёмным Tailwind-значением.
2. Смысл цвета потерян: `bg-slate-800` значит «приглушённая поверхность», правки нужны в двух местах.
3. Структурные селекторы завязаны на цепочки утилит (ломаются от правки разметки).
4. Хаки вместо разметки: кнопки композера прячут текст через `font-size: 0` + `::after`.

Целевая архитектура: CSS-переменные в `:root` → семантические цвета в `tailwind.config.cjs` (`surface` / `line` / `ink` / `brand` / `danger` / `success` / `warning` / `info`) → компоненты на токенах → блок `.catalog-shell .bg-slate-*` удалить полностью.

Контроль: `rg 'slate-|indigo-\d|(bg|text|border)-(red|emerald|amber|sky|fuchsia)-\d' frontend/src` пусто.

Anti-goals: не редизайн, не тёмная тема, не новые UI-библиотеки, не backend, не менять поведение/API/хуки.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

`frontend/tailwind.config.cjs` — `theme.extend` пустой, semantic colors ещё нет.

`frontend/src/index.css`:

- `:root` задаёт Inter и светлый фон (`#fff` / `#25282d`), hex размазан по `.catalog-*` классам (16–159).
- Слой переопределений Tailwind: строки 62–82 (`.catalog-shell .bg-slate-*`, `.text-slate-*`, `.bg-indigo-600`, `.text-red-300`, `.bg-red-950/40`).
- Структурные селекторы: 85–90 — `.catalog-sidebar .flex.flex-col.gap-2 > .flex.items-center.justify-between.gap-2` бьёт в разметку `CollapsibleSection.tsx:21–22`.
- Хак композера: 106–109 — `button.bg-indigo-600` / `button.bg-red-600` → круг 36×36, `font-size: 0`, иконка в `::after`. Источник кнопок: `Chat.tsx:266–282` (`bg-red-600` «Стоп», `bg-indigo-600` «Отправить»).
- Карточки/композер уже задают целевые радиус/тень: `.catalog-composer` 20px + `0 4px 18px rgba(42,54,62,.09)` (99–102), `.artifact-summary` 24px (113).

20 файлов `frontend/src/**/*.tsx`. Grep `slate-|indigo-` находит совпадения во всех компонентах кроме `main.tsx` и `ArtifactSummaryCard.tsx` (плюс 19 совпадений в `index.css`). `docs/ui-style-guide.md` отсутствует.

Известные тёмные пятна (подтверждены описанием, линии могут чуть съехать): `RunView.tsx` `bg-slate-950/40`, `TraceSteps.tsx` `bg-slate-950/60` / `bg-red-950/40`, бейджи в `SkillsPanel.tsx` (`sky`/`fuchsia`/`emerald`/`amber`), оверлеи `bg-black/60` в трёх модалках.

## Затрагиваемые файлы

- `frontend/src/index.css` — `:root` токены; удалить 62–82 и структурные селекторы 85–90; убрать `font-size: 0` / `::after`; hex в `.catalog-*` свести к `var(--…)`.
- `frontend/tailwind.config.cjs` — `theme.extend.colors` / `borderRadius` / `boxShadow`.
- `frontend/src/components/*.tsx` и `App.tsx` — замена `slate-*`/`indigo-*`/сырых статусных палитр на токены; явные классы вместо цепочек утилит (`CollapsibleSection`); icon-кнопки композера в `Chat.tsx`.
- Опционально: `frontend/src/components/ui/` или `@layer components` — примитивы кнопки/бейджа/инпута/карточки/оверлея.
- `docs/ui-style-guide.md` — новый, таблица токенов + когда какой вариант кнопки/бейджа.

Backend не трогать.

## План действий

1. **Этап 0 — инвентаризация.** Пройти все 20 `*.tsx` + `index.css`, составить таблицу `файл:строка → текущий класс → целевой токен`. Каталог дефектов в ТЗ — стартовая точка, не исчерпывающий список.
2. **Токены.** В `:root` — поверхности, границы, текст, акцент, статусы, оверлей, тени, радиусы. Значения взять из текущего светлого CSS (`#eef7ff`, `#1d83c4`, `#f5f6f6`, `#292c31`, …). В `tailwind.config.cjs` завести `surface` (DEFAULT/muted/sunken), `line` (DEFAULT/strong), `ink` (DEFAULT/muted/faint), `brand` (DEFAULT/hover/soft), `danger`/`success`/`warning`/`info` (фон бейджа + контрастный текст), плюс radius/shadow карточек.
3. **Примитивы.** Кнопка (primary / secondary / ghost / destructive / icon-only), бейдж, инпут/textarea, карточка, оверлей модалки. React-компоненты или `@layer components` — единообразно, с обоснованием в работе. Disabled: `surface.muted` + `ink.faint` + `cursor-not-allowed`, не `opacity-50`. Focus-visible: ring на `brand`.
4. **Композер.** «Отправить»/«Стоп» — честные icon-кнопки в JSX: `inline-flex size-9 items-center justify-center rounded-full shrink-0`, `aria-label`. Удалить хак 106–109. «Стоп» на токене `danger`.
5. **Компоненты по группам.** Чат → сайдбар (сессии/документы/скиллы, `CollapsibleSection` → `.catalog-section-header`) → артефакты → run/trace → модалки (единый оверлей ~`rgba(23,33,41,.35)`, те же радиус/граница/тень что у карточек).
6. **Снести слой.** Удалить `.catalog-shell .*-slate-* / .*-indigo-*` и селекторы на цепочках утилит. Хардкод hex вне `:root` — в `var(--…)`.
7. **Проверки + гайд.** `rg` из DoD пуст. 1440px и 375px. `docs/ui-style-guide.md`. `pnpm run build` / `lint` / `typecheck`.

## Критерии приёмки (Definition of Done)

- [ ] `rg 'slate-|indigo-\d' frontend/src` — пусто.
- [ ] `rg '(bg|text|border)-(red|emerald|amber|sky|fuchsia|black)-' frontend/src` — пусто.
- [ ] Блок `.catalog-shell .bg-slate-* / .text-slate-* / .bg-indigo-* / .text-red-300 / .bg-red-950\/40` в `index.css` удалён.
- [ ] В `index.css` нет селекторов, опирающихся на цепочки Tailwind-утилит.
- [ ] В `index.css` нет `font-size: 0` и декоративных `::after`-иконок.
- [ ] Все цвета из токенов; хардкод hex вне `:root` отсутствует.
- [ ] Кнопки «Отправить» и «Стоп»: круг 36×36, иконка по центру, одинаковый размер, `aria-label`, hover/active/focus-visible/disabled различимы.
- [ ] Ни одного тёмного пятна: run-meta, trace, ошибки/успех, оверлеи модалок — светлая палитра.
- [ ] Статусные бейджи (`python`/`ai`, `draft`/`committed`, `ok`/`error`) читаемы на белом, контраст текста ≥ 4.5:1.
- [ ] Каждый интерактивный элемент имеет видимый `focus-visible`.
- [ ] Disabled-состояния читаемы (не прозрачный текст на белом).
- [ ] Три модалки визуально согласованы: оверлей, радиус, граница, тень, типографика заголовка.
- [ ] 1440px и 375px: мобильные табы «Чат / Черновик», скрытие сайдбара, полноэкранные карточки без регрессии.
- [ ] Из `frontend/`: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` зелёные.
- [ ] `docs/ui-style-guide.md` создан и отражает фактические токены.
- [ ] Визуальная приёмка — по дизайн-спеке `CATALOG-75.design.md` (фаза catalog-designer).

## Вне объёма

- Смена визуального языка (композиция, отступы, скругления, тени).
- Тёмная тема и инфраструктура переключения тем.
- Новые UI-библиотеки / зависимости.
- Backend, поведение, API-контракты, хуки, тексты (кроме замены текста кнопки на иконку с `aria-label`).
