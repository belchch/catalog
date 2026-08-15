# CATALOG-103 — Скиллы: действия только внутри карточки, иконками с цветовым кодом

- **Задача Plane:** [CATALOG-103](https://app.plane.so/belchch/projects/catalog-app/work-items/103) (id: `3dadef59-676b-472f-8d48-f8bdc98ecfe4`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 06 · независимый
- **Цель:** Один набор действий скила — в раскрытой карточке, четыре иконки с цветовым кодом (переименовать / редактировать / коммит / удалить). Строка без кнопок, kebab нет, удаление одним кликом до подтверждения.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

После CATALOG-97/98 действия продублированы: hover-иконки в строке (`SkillsPanel.tsx:494-549`) и текстовые кнопки в панели (`:662-757`). Нужно: убрать набор из строки; в панели — иконки в один ряд (Pencil нейтральный, новая CodeIcon brand, CommitIcon success, новая TrashIcon danger справа через `ml-auto`); kebab удалить; контрастные залитые кнопки из токенов (не hex); `aria-label` + `title`; size-7 / ≥28px; inline-confirm удаления сохранить; форму переименования не трогать; почистить `overflowOpen` / kebab-рефы / шаг overflow в `escapeCascade`. Тип: UI, нужна дизайн-спека до кода.

## Предыстория
_нет — комментариев к задаче не было_

## Контекст
Сейчас два набора:

- Строка (`:494-549`): `PencilIcon` = edit-сессия, `CommitIcon`, kebab `MoreHorizontalIcon`. Показ через `opacity-0 group-hover` / выбранная строка. Низкий контраст `.btn-icon-ghost` (`index.css:146-152`, `text-ink-faint`).
- Панель (`:662-723`): текстовые «Переименовать / Редактировать / Коммит» + `⋯` → «Удалить». Узкий сайдбар переносит кнопки.
- Confirm (`:725-753`) живой; «Отмена» фокусит `kebabRef` (`:748`).
- `escapeCascade` (`:300-318`): confirm → overflow → rename → deselect; overflow больше не нужен.
- `onBlur` панели (`:584-597`) ищет `.catalog-skill-row__actions` — после удаления блока упростить.
- Медиазапрос `index.css:273-276` форсит opacity иконок строки на touch — удалить вместе с классом.

Иконки: `PencilIcon`, `CommitIcon`, `MoreHorizontalIcon` в `icons.tsx`. `CodeIcon` / `TrashIcon` нет. Библиотек иконок, DropdownMenu, Tooltip в проекте нет — не добавлять.

Токены: `index.css:34-60`, tailwind `brand-soft` / `brand-ink` / `success-*` / `danger-*`. Выбранная строка — `bg-brand-soft` (`index.css:262-264`).

## Затрагиваемые файлы
- `frontend/src/components/SkillsPanel.tsx` — удалить иконки строки 494–549; заменить текстовые кнопки 662–692; удалить kebab 693–723; confirm вызывать с корзины; почистить `overflowOpen`, `kebabRef`, `focusKebabRef`, `escapeCascade`, `selectSkill` / `moveSelection` / `closeMenus`; фокус после отмены — на Trash.
- `frontend/src/components/icons.tsx` — `CodeIcon` (`</>`) и `TrashIcon`, тот же `iconBase` (16×16, stroke 1.75).
- `frontend/src/index.css` — классы залитых icon-кнопок рядом с `.btn-icon-ghost`; удалить `.catalog-skill-row__actions` (`:273-276`). Не хардкодить hex.

## План действий
1. Удалить блок `catalog-skill-row__actions` из строки. В строке: статус, имя, бейджи, арность.
2. Добавить `CodeIcon` и `TrashIcon` в `icons.tsx` в стиле feather/`iconBase`.
3. В `@layer components` — варианты вроде `btn-icon-soft-brand` / `success` / `danger` / нейтральный: заливка `*-soft`, цвет `*-ink`, рамка `--line` / `--danger-line`, hover насыщеннее, `focus-visible:ring-brand`, disabled как у ghost (не другой hue). Контраст иконки к заливке ≥ 3:1 и на `bg-brand-soft` выбранной строки.
4. В панели выбранного скила — один ряд `size-7`: Переименовать (`PencilIcon`, нейтральный/brand), Редактировать (`CodeIcon`, brand), Коммит (`CommitIcon`, success, `disabled={status !== 'draft'}`, динамический `title`), Удалить (`TrashIcon`, danger, `ml-auto`). У всех `aria-label` + `title`. Kebab и `overflowOpen` убрать.
5. Корзина сразу ставит `confirmOpen`. Inline-confirm (`:725-753`) без изменений текста. «Отмена» и Escape из confirm фокусят кнопку удаления (`deleteBtnRef`). Из `escapeCascade` убрать шаг overflow.
6. Форму переименования (`:600-659`) не менять. `onBlur` панели — без поиска row-actions. Удалить CSS `.catalog-skill-row__actions`.
7. Ручная проверка в узком сайдбаре: ряд в одну строку; confirm не перекрывает соседей; ↑↓/Enter; Tab по четырём кнопкам; hover строки пустой.

## Критерии приёмки (Definition of Done)
- [ ] В строке скила нет кнопок; hover ничего не проявляет.
- [ ] Действия только в раскрытой панели выбранного скила.
- [ ] Четыре иконки: переименовать, редактировать, коммит, удалить. Kebab нет.
- [ ] Удаление — один клик до существующего подтверждения.
- [ ] Цвета из токенов: brand — правка, success — коммит, danger — удаление; hex нет.
- [ ] Контраст иконки к заливке ≥ 3:1, в том числе на выбранной строке.
- [ ] У каждой кнопки `aria-label` и `title`; всё доступно с Tab.
- [ ] Коммит disabled при `status !== 'draft'` и выглядит выключенным.
- [ ] Escape: confirm → rename → снять выбор; фокус после отмены удаления — на корзине.
- [ ] ↑↓ и Enter как раньше; `overflowOpen` и связанные рефы удалены.
- [ ] В узком сайдбаре четыре иконки в одну строку, не выдавливают контент.
- [ ] Inline-confirm не перекрывает соседние скилы.
- [ ] Новых npm-зависимостей нет.
- [ ] `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` из `frontend/` зелёные.
