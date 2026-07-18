# CATALOG-28 — Дизайн UI

- **Источник:** `docs/plan/night-shift/CATALOG-28-ui-doc-combobox-fixes.md`
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Сценарий — выбор документов для включения в контекст сообщения планировщику в composer'е чата. Composer стоит у нижней грани viewport.

Шаги пользователя:

1. Юзер открывает чат сессии, видит composer внизу: текстера, кнопка отправки, строка выше с чипами выбранных документов и кнопкой-комбобоксом `+ документ`.
2. Кликает `+ документ` — раскрывается **upward listbox**: инпут поиска сверху, под ним список чекбоксов с названиями документов. Листбокс раскрывается **вверх** от триггера и остаётся полностью в viewport даже при 10+ документах.
3. Кликает пункт (или чекбокс в пункте) — пункт переходит в выбранное состояние (галка), триггер меняет подпись на `N выбрано`, над триггером появляется чип выбранного документа. Список остаётся открытым для множественного выбора.
4. Повторный клик по выбранному пункту снимает галку, чип исчезает, счётчик декрементируется.
5. Поиск: юзер вводит строку — список фильтруется по подстроке в `title` (case-insensitive). После фильтрации клик по пункту корректно переключает выбор.
6. Закрытие: клик вне комбобокса, Escape (с возвратом фокуса на триггер), или переход `disabled` (например, начало стрима).

Регрессионный сценарий — `SkillsPanel`:

- В модалке `DocumentCombobox` стоит в потоке контента (не у нижней грани). Там остаётся раскрытие **вниз** (дефолт `placement='bottom'`), поведение single и multiple не меняется.

## Дерево компонентов и файлы

Изменяемые файлы (новых компонентов не добавляется):

- `frontend/src/components/DocumentCombobox.tsx`
  - **Тип:** добавить опциональный проп `placement?: 'bottom' | 'top'` (default `'bottom'`) — общая часть типа, не привязанная к multiple/single.
  - **Поведение закрытия:** убрать `onBlur` на корневом `<div>` (`DocumentCombobox.tsx:99-103`). Внешний клик уже ловится `mousedown` outside-listener (`:37-47`), Escape — в `onKeyDown` триггера (`:122-127`) и listbox (`:140-146`). Это чинит баг 1: в multiple-режиме клик по `<label>` с вложенным `<input type="checkbox">` перестаёт обрываться преждевременным `close()` до срабатывания `onChange` чекбокса.
  - **Позиционирование listbox:** ветвить класс позиционирования корня listbox в зависимости от `placement`:
    - `'bottom'` (default) → `mt-1` (как сейчас, `:139`).
    - `'top'` → `bottom-full mb-1`.
    - Остальные классы (`absolute z-10 max-h-48 w-full overflow-y-auto rounded border border-slate-700 bg-slate-900 shadow-xl`) не меняются.
  - Single-режим (`<div role="option" onClick>`), фильтр, триггер, подпись «N выбрано» — без изменений.

- `frontend/src/components/Chat.tsx`
  - В `<DocumentCombobox multiple ...>` composer'а (`:203`) добавить `placement="top"`. Других изменений в `Chat.tsx` нет: чипы, `selectedDocIds`, `onSend(text, docIds?)` уже работают как задумано.

- `frontend/src/components/SkillsPanel.tsx` — **не трогать**. Все 4 вызова `DocumentCombobox` (single + multiple, `:366-413`) берут дефолт `placement='bottom'` и сохраняют текущее поведение.

Не в скоупе шага, но值得 отметить ревьюеру: аналогичный `onBlur` на root div есть в `frontend/src/components/ModelCombobox.tsx:66-70`. Single-режим без `<label>` там не страдает от бага 1, поэтому фикс в этом шаге сознательно ограничен `DocumentCombobox`.

## Layout и состояния

Структура composer'а (не меняется, контекст для позиционирования):

```
<div flex h-full flex-col>
  … сообщения …
  <div border-t p-3>                        ← composer
    [Документы в сессии]                    ← optional section
    [suggestions chips]                     ← optional
    <div mb-2 flex flex-wrap items-center gap-1.5>
      [chip] [chip] …                       ← selectedDocs
      <div w-44 max-w-[12rem]>              ← враппер комбобокса
        <DocumentCombobox placement="top" multiple>
          ├─ button (+ документ | N выбрано)
          └─ [open] listbox ↗ раскрывается ВВЕРХ
        </DocumentCombobox>
      </div>
    </div>
    <textarea/> + [Отправить | Стоп]
    [Создать скилл из сессии]
  </div>
</div>
```

Состояния `DocumentCombobox` (composer-инстанс, `placement="top"`):

- **closed** — кнопка-триггер показывает подпись: `+ документ` (нет выбора) или `N выбрано` (где N = `selectedDocIds.length`). Иконка `▾`. Класс триггера через `triggerClassName` от `Chat.tsx`.
- **open, has results** — listbox раскрыт вверх от триггера: поиск (sticky не обязателен, см. стиль), список опций-чекбоксов с названиями; выбранная опция имеет `<input type="checkbox" checked>` и `aria-selected="true"`.
- **open, empty filter** — под инпутом поиска: текст `нет совпадений` (тот же класс, что сейчас).
- **disabled** (`streaming===true`) — триггер `disabled`, `aria-disabled`, opacity-50; listbox закрыт.
- **error** — у комбобокса своего error-состояния нет; ошибки уровня сессии рисуются отдельно в `Chat.tsx:142`.

Loading-состояние не нужно: `documents: DocumentOut[]` приходит синхронно как проп из родительского контейнера, отдельного фетча комбобокс не делает.

Высота listbox: `max-h-48` (192px) + `overflow-y-auto` — сохраняется. При `placement="top"` этого достаточно: composer у нижней грани, listbox растёт вверх в область сообщений, которая сама по себе scrollable — listbox всегда помещается в viewport.

## Взаимодействия

- **Клик по триггеру** — toggle `open`. При открытии поле поиска получает `autoFocus`.
- **Клик по пункту multiple (label или checkbox)** — `toggleMulti(docId)` → `onChange(nextIds)` → родитель обновляет `selectedDocIds` → `Chat.tsx` перерисовывает чипы и подпись триггера. Listbox остаётся открытым.
  - Гарантия после фикса `onBlur`: клик по `<label>` (не точно по `<input>`) корректно доходит до `onChange` чекбокса, потому что преждевременное закрытие по blur убрано.
- **Ввод в поиск** — `setFilter(e.target.value)`, `options` перефильтруется по `title.toLowerCase().includes(q)`.
- **Escape** (с фокусом на триггере или внутри listbox) — `close()` + фокус возвращается на `<button>` триггера (`rootRef.current?.querySelector('button')?.focus()`).
- **Клик вне rootRef** — `mousedown` outside-listener → `close()`. Это единственный механизм закрытия по внешнему клику после удаления `onBlur`.
- **Чип «×»** в `Chat.tsx` — `removeSelected(id)`, отдельно от комбобокса; не закрывает и не открывает listbox.
- **Сабмит сообщения** — очищает `selectedDocIds`, чипы и счётчик сбрасываются; listbox в этот момент обычно уже закрыт юзером.

Крайние случаи:

- `documents.length === 0` — комбобокс открывается с пустым списком; чип выбран нельзя. В composer это unlikely (документы всегда есть), но компонент обязан не падать.
- Быстрый повторный клик по триггеру во время стрима — `disabled` блокирует toggle.
- Клик по `<label>` с зажатым выделением текста — после удаления `onBlur` поведение сводится к стандартному label+checkbox; некорректных «иногда не выбирается» больше нет.

## Стиль и токены

Стек — Tailwind v3 (ADR-0011). Новых зависимостей нет. Все классы ниже уже используются в существующем UI; вводимые изменения — только ветвление `mt-1` ↔ `bottom-full mb-1`.

Триггер (composer, остаётся как есть):

```text
flex w-full items-center justify-between rounded-full border border-slate-700
bg-slate-800/60 px-3 py-1 text-left text-xs text-slate-200
hover:border-indigo-500 hover:bg-slate-800 disabled:opacity-50
```

Listbox (общая часть, не меняется):

```text
absolute z-10 max-h-48 w-full overflow-y-auto
rounded border border-slate-700 bg-slate-900 shadow-xl
```

Позиционирование listbox по `placement`:

- `bottom` (default): `mt-1` — листбокс **под** триггером.
- `top`: `bottom-full mb-1` — листбокс **над** триггером, прижат нижней гранью к верхней грани триггера, отступ `mb-1` (4px) — симметрия с `mt-1`.

Содержимое listbox не меняется: инпут поиска (`rounded bg-slate-800 px-2 py-1 text-[11px]`), empty-state (`px-2 py-1 text-[11px] text-slate-500`), опции multiple (`flex items-center gap-1.5 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800` + чекбокс `h-3 w-3 accent-indigo-500`), опции single — без изменений.

Консистентность с существующим UI сохраняется: те же `slate-800/900`, `border-slate-700`, `text-[11px]`, `accent-indigo-500`, `max-h-48`, `z-10`, `shadow-xl`. Чипы выбранных документов в `Chat.tsx:182-201` — без изменений.

## Доступность (a11y)

Минимум для среза (без расширения a11y-поведения относительно текущего кода):

- Триггер `<button type="button" role="combobox" aria-haspopup="listbox" aria-expanded={open} aria-controls={listId} aria-label={ariaLabel}>`.
- Listbox: `<div role="listbox" aria-multiselectable={multiple || undefined}>`, `id={listId}` связан с `aria-controls` триггера.
- Опции: `<label role="option" aria-selected={selected}>` (multiple) или `<div role="option" aria-selected={selected}>` (single).
- **Клавиатура:**
  - Escape — закрывает listbox и возвращает фокус на триггер. Сохраняется после удаления `onBlur`.
  - Tab — естественный порядок фокуса: триггер → поиск (autoFocus) → чекбоксы (multiple) / опции (single).
  - Стрелки/Enter-on-option в этом шаге **не добавляются** (их нет в текущем коде, вне скоупа фикса).
- **Фокус после закрытия** — на триггер, чтобы юзер не терял позицию в composer'е.
- **Контраст:** все используемые пары (text-slate-100/200/300 на bg-slate-800/900, indigo-100 на indigo-600/15) уже прошли визуальный приём в существующем UI; новых контрастных пар не появляется.
- Дежурное: `aria-disabled={disabled || undefined}` на триггере (уже есть).

## Контракты данных

Без изменений относительно уже реализованного (см. раздел «Предыстория» плана):

- `Chat.tsx` хранит `selectedDocIds: string[]`, рисует чипы из `selectedDocs = selectedDocIds.map(...documents.find)`, передаёт `onSend(text, selectedDocIds.length > 0 ? selectedDocIds : undefined)`.
- `usePlannerSession` проксирует `docIds` в WS `send(text, docIds?)` (`frontend/src/ws.ts:87-91`), который шлёт фрейм `{type:'user', content, doc_ids}`.
- `DocumentCombobox` получает `documents: DocumentOut[]` (read-only проп) и сообщает через `onChange(ids: string[])`.

Дизайн **не вводит** новых типов, эндпоинтов или WS-контрактов. Весь контракт для UI — новый опциональный проп `placement?: 'bottom' | 'top'` у `DocumentCombobox`.

## Критерии визуальной приёмки

- [ ] В composer чата клик по пункту multiple-комбобокса (по чекбоксу **и** по тексту `<label>`) добавляет документ в `selectedDocIds` и рисует чип над текстерой — стабильно, на каждой попытке (не «иногда»).
- [ ] Повторный клик по выбранному пункту снимает выбор: галка пропадает, чип исчезает, счётчик `N выбрано` декрементируется.
- [ ] Фильтр по поиску работает; после фильтрации клик по оставшемуся пункту корректно переключает выбор.
- [ ] При 10+ документах listbox в composer'е раскрывается **вверх** от триггера (виден отступ между верхней гранью триггера и нижней гранью listbox) и **целиком помещается в viewport** — без скролла страницы, без обрезки.
- [ ] Направление раскрытия ветвится по `placement`: при `placement="top"` listbox раскрывается вверх, при `placement="bottom"` (default) — вниз.
- [ ] В `SkillsPanel` все 4 инстанса `DocumentCombobox` раскрываются вниз и ведут себя как раньше (single-выбор закрывает список, multiple — оставляет открытым); визуальных отличий от текущей реализации нет.
- [ ] Закрытие по внешнему клику сохранено во всех режимах (`placement="top"`, `placement="bottom"`, single, multiple).
- [ ] Escape закрывает listbox и возвращает фокус на триггер — в обоих `placement` и в обоих режимах.
- [ ] `disabled`-состояние (стрим) блокирует и триггер, и раскрытие; `aria-disabled` присутствует.
- [ ] Чипы выбраных документов и подпись триггера (`+ документ` / `N выбрано`) обновляются синхронно с `selectedDocIds`.
- [ ] Новый проп `placement` опциональный (default `'bottom'`); вызовы `DocumentCombobox` без `placement` в `SkillsPanel` не требуют правок.
