# CATALOG-37 — Дизайн UI

- **Источник:** `docs/plan/night-shift/CATALOG-37-ui-rename-input-collapse.md`
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Пользователь в `SkillsPanel` жмёт «✎» рядом с именем скила → имя превращается в инлайн text input с кнопками «Сохранить» / «Отмена». Сегодня на узком сайдбаре input схлопывается до одной буквы, потому что `flex-wrap` + `flex-1` (`flex-basis: 0`) + две неразмеченные кнопки раскладываются так, что инпут получает только `min-w-0`.

Цель фикс — переопределить CSS-раскладку блока переименования так, чтобы:

- input занимал всю доступную ширину строки минус кнопки;
- при нехватке места кнопки **контролируемо** уходили на новую строку, а инпут растягивался на всю ширину карточки;
- поведение save / cancel / blur / Enter / Escape осталось прежним.

Скоуп — только Tailwind-классы блока rename в `SkillsPanel.tsx`. Новых компонентов, иконок, библиотек, API — нет.

## Дерево компонентов и файлы

Один файл, без добавления сущностей:

- `frontend/src/components/SkillsPanel.tsx` — изменить структуру и Tailwind-классы блока `renaming` (сейчас `SkillsPanel.tsx:197–248`). Логика (`startRename` / `saveRename` / `clearRename`, обработчики `onKeyDown` / `onBlur`, `renameSaving`, `renameEmpty`) **не трогается** — только разметка и классы.

Новых компонентов не вводим: rename-блок остаётся инлайн в `<li>`, как сейчас.

## Layout и состояния

### Текущая (сломанная) структура

```tsx
<div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5" onBlur={…}>
  <input className="min-w-0 flex-1 …" … />
  <button>Сохранить</button>
  <button>Отмена</button>
</div>
```

`flex-wrap` + `flex-1` на инпуте (= `flex: 1 1 0%`) + кнопки без `shrink-0` → при узком родителе инпут сжимается до `min-w-0` (1 символ), кнопки забирают `max-content`.

### Целевая структура

```tsx
<div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5" onBlur={…}>
  <div className="flex min-w-[8rem] flex-1 items-center">
    <input className="w-full rounded bg-slate-800 px-2 py-1 text-xs text-slate-100 disabled:opacity-50" … />
  </div>
  <div className="flex shrink-0 items-center gap-1.5">
    <button …>{renameSaving ? '…' : 'Сохранить'}</button>
    <button …>Отмена</button>
  </div>
</div>
```

Ключевые изменения:

1. **Инпут обёрнут во flex-wrapper** `min-w-[8rem] flex-1 items-center`. Это убирает `flex-basis: 0` прямо с `<input>` и гарантирует, что инпут-блок не ужается меньше 8rem.
2. **Инпут получает `w-full`** внутри wrapper'а — занимает всю ширину wrapper'а, а не пытается быть flex-item'ом родителя. Длинные имена скроллятся внутри input (нативное поведение), не растягивая карточку.
3. **Кнопки объединены в отдельный flex-ребёнок** `flex shrink-0 items-center gap-1.5`. `shrink-0` запрещает им сжиматься, `flex` делает их единой группой — они переносятся на новую строку целиком, а не по одной.
4. **`flex-wrap` остаётся** на внешнем контейнере — это и есть «контролируемый перенос»: когда `min-w-[8rem]` + естественная ширина кнопок не помещаются в ширину карточки, кнопки уходят на новую строку, а wrapper инпута (`flex-1`) занимает всю доступную ширину.

### Состояния

| Состояние | Что показываем |
|---|---|
| **Idle** (не rename) | Текущая строка: `имя + ✎` слева, теги/status справа. Не меняется. |
| **Rename, хватает места** | Инпут занимает ширину карточки минус кнопки минус tags/status, всё в одну строку. |
| **Rename, узкий сайдбар** | Кнопки переносятся под инпут; инпут растягивается на всю ширину карточки; tags/status остаются справа в первой строке (поведение `justify-between` родителя сохранено). |
| **Rename, очень длинное имя (40+ символов)** | Инпут скроллит текст горизонтально (нативное), карточка не растягивается. |
| **Saving** (`renameSaving=true`) | Инпут и обе кнопки `disabled`, «Сохранить» показывает `…`. Layout не меняется. |
| **Empty** (`renameEmpty=true`) | «Сохранить» disabled, layout не меняется. |

### Соседние элементы

Родитель `<div className="flex items-center justify-between gap-2">` (строка 196) и правый блок tags/status (строки 262–286) **не меняются**. В rename-режиме:

- правый блок tags/status остаётся на своём месте (`shrink-0`, не давит на rename-блок);
- `flex-1 min-w-0` на rename-контейнере корректно отдаёт ему остаток ширины после tags/status.

## Взаимодействия

Поведение переименовано **не будет** — фикс чисто визуальный. Перечислено как контракт для приёмки:

- **Enter** в инпуте → `saveRename` (preventDefault).
- **Escape** в инпуте → `clearRename` (preventDefault).
- **Blur** (фокус покинул контейнер rename) → `clearRename`, кроме случая `renameSavingRef.current=true`. Реализация через `requestAnimationFrame` + `container.contains(document.activeElement)` — сохраняется как есть.
- **«Сохранить»** → `saveRename(s.id, s.name)`. Disabled при `renameSaving || renameEmpty`.
- **«Отмена»** → `clearRename`. Disabled при `renameSaving`.
- **autoFocus** инпута + `onFocus` ставит курсор в конец значения (`setSelectionRange(len, len)`) — сохраняется.

Крайние случаи:

- Имя не изменилось → `saveRename` сразу вызывает `clearRename` (мутации нет).
- Сетевой сбой → `catch` сбрасывает `renameSaving`, инпут остаётся активным с введённым текстом, пользователь может повторить. Layout не ломается.
- Параллельный rename нескольких скилов невозможен: `renameId` хранит один id.

## Стиль и токены

Только существующие Tailwind v3 utilities, согласовано с окружающим UI:

| Параметр | Значение | Контекст в коде |
|---|---|---|
| Внешний контейнер | `flex min-w-0 flex-1 flex-wrap items-center gap-1.5` | без изменений (родитель уже flex-row) |
| Wrapper инпута (новый) | `flex min-w-[8rem] flex-1 items-center` | `min-w-[8rem]` — сломать гибкость ниже этого порога нельзя |
| Инпут | `w-full rounded bg-slate-800 px-2 py-1 text-xs text-slate-100 disabled:opacity-50` | вместо `min-w-0 flex-1 …` |
| Группа кнопок (новая) | `flex shrink-0 items-center gap-1.5` | как существующий правый блок tags/status (строка 262) |
| «Сохранить» | `rounded bg-indigo-600 px-2 py-1 text-[11px] text-white disabled:opacity-50` | без изменений |
| «Отмена» | `rounded bg-slate-700 px-2 py-1 text-[11px] text-slate-200 disabled:opacity-50` | без изменений |

Цветовая палитра (`slate-700/800/900`, `indigo-600` для primary, `text-slate-100/200/400`) и типографические размеры (`text-xs`, `text-[11px]`) совпадают с остальной `SkillsPanel`. Отступы `gap-1.5` и `px-2 py-1` — те же, что в соседних кнопках (`Редактировать` / `Коммит` / `Удалить`).

`min-w-[8rem]` — arbitrary value, в стиле проекта уже есть (`min-w-[12rem]` / `max-w-[18rem]` в `ModelSelector.tsx`, `max-w-[12rem]` в `SkillsPanel.tsx:79`). 8rem ≈ 128px — достаточно, чтобы набрать минимум 10–12 символов имени без обрезки и при этом оставить место под кнопки в типичном сайдбаре.

`flex-nowrap` как альтернатива `flex-wrap` отвергнута: на узком сайдбаре (< ~220px) инпут с `min-w-[8rem]` + кнопки всё равно не умещаются, и без wrap кнопки либо обрежутся, либо вылезут за карточку. Wrap с группой кнопок `shrink-0` даёт чистый controlled fallback.

## Доступность (a11y)

Сохраняется текущий минимум, новых требований не появляется:

- `<input type="text" aria-label="Имя скила">` — подпись для screen reader.
- `autoFocus` — при входе в rename фокус сразу на инпуте, клавиатурный пользователь может печатать без лишнего Tab.
- Клавиатурные сокращения **Enter** (сохранить) и **Escape** (отменить) работают, оба с `preventDefault`.
- `<button type="button">` у «Сохранить» / «Отмена» — стандартная активация Enter/Space.
- Контраст текста инпута `text-slate-100` на `bg-slate-800` ≈ 9.7:1 (AAA); подписи кнопок `text-white` / `text-slate-200` на `bg-indigo-600` / `bg-slate-700` — ≥ 4.5:1 (AA+).
- Disabled-состояние (`disabled:opacity-50`) визуально отличается; при `renameSaving` фокус остаётся в контейнере, чтобы screen reader корректно отчитал переход.
- Layout-изменение не меняет DOM-порядок фокуса: input → «Сохранить» → «Отмена» → (выход из контейнера = blur = cancel).

## Контракты данных (если нужны)

Без изменений. UI использует уже прокинутые в `SkillsPanel` props:

- `onRename(skillId: string, name: string): Promise<void>` — вызов из `saveRename`.
- Внутренний стейт `renameId` / `renameValue` / `renameSaving` / `renameSavingRef` — сигнатуры те же.

Новых API, WebSocket-событий или типов не появляется. Ссылки на план: секция «Постановка задачи» и «План действий», п. 1–3.

## Критерии визуальной приёмки

- [ ] При клике на «✎» инпут сразу занимает всю доступную ширину карточки скила минус кнопки — не схлопывается в одну букву.
- [ ] Кнопки «Сохранить» и «Отмена» — единая flex-группа (`shrink-0`), на одной строке с инпутом при типичных ширинах сайдбара.
- [ ] При ширине сайдбара, где `min-w-[8rem]` + кнопки не помещаются, кнопки переносятся под инпут целой группой, инпут растягивается на всю ширину карточки (controlled wrap, не «маленькое поле»).
- [ ] Длинное имя скила (40+ символов) в инпуте скроллится горизонтально внутри input, карточка не растягивается.
- [ ] Инпут обёрнут в `min-w-[8rem] flex-1 items-center`, на самом `<input>` класс `w-full` (а не `min-w-0 flex-1`).
- [ ] Правый блок tags/status в rename-режиме не меняет положение (остаётся в `justify-between` справа), не наезжает на инпут.
- [ ] Saving-состояние (`renameSaving=true`): инпут и обе кнопки disabled, «Сохранить» показывает `…`, layout не дёргается.
- [ ] Empty-состояние (`renameEmpty=true`): «Сохранить» disabled, layout не меняется.
- [ ] Поведение Enter / Escape / blur / autoFocus / `setSelectionRange` — прежнее (см. «Взаимодействия»).
- [ ] Никаких визуальных регрессий в обычном режиме (не rename): имя + ✎, tags/status — как раньше.
- [ ] Изменения касаются только Tailwind-классов и структуры блока rename; логика `startRename` / `saveRename` / `clearRename` / обработчиков не правится.
