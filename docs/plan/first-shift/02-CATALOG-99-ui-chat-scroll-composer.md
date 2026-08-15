# CATALOG-99 — Чат: прокрутка уезжает вниз, композер оказывается сверху пустого экрана

- **Задача Plane:** [CATALOG-99](https://app.plane.so/belchch/projects/catalog-app/work-items/99) (id: `c0310aec-9bc5-482b-beec-a5f022d8faf6`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 02 · независимый
- **Цель:** Колонка чата держит высоту main: композер прижат к низу и всегда виден, скроллится только лента `.catalog-chat__scroll`, документ и overflow-hidden-предки остаются на `scrollTop === 0`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

На главном экране планировщика колонка чата не держит высоту viewport. Карточка `.catalog-composer` оказывается у верхнего края main, под ней пустое белое пространство; лента и empty-state не видны. Воспроизводится и на новой сессии, и с историей.

Ожидание: колонка = высота main (`header` → `.catalog-layout` → `.catalog-main`); композер внизу; скролл только у `.catalog-chat__scroll`; `document.scrollingElement.scrollTop === 0` и у обёрток тоже 0; автоскролл не трогает предков.

Гипотезы по порядку: (1) `scrollIntoView` в `Chat.tsx` крутит всех предков и срабатывает на пустом `messages`; (2) рвётся `min-h-0` в цепочке flex/overflow; (3) у `.catalog-chat` нет своей высоты, `h-full` резолвится в `auto`.

Фикс: заменить `scrollIntoView` на `el.scrollTop = el.scrollHeight` у `.catalog-chat__scroll` (или `block: 'nearest'`), не скроллить при пустом `messages`, закрыть дырку `min-h-0` если подтвердится.

## Предыстория
_нет — комментариев к задаче не было_

## Контекст
Автоскролл сейчас безусловный:

```69:71:frontend/src/components/Chat.tsx
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])
```

`bottomRef` сидит в конце ленты (`Chat.tsx:158`). Эффект бежит и при `messages === []` — совпадает с симптомом на новой сессии. `scrollIntoView` без `block: 'nearest'` прокручивает все скроллируемые предки, включая `overflow: hidden` (программно) и документ.

Цепочка оболочки (`App.tsx`):

- `545` — `.catalog-shell.flex.h-screen.flex-col`
- `584` — `.catalog-layout.grid.flex-1.overflow-hidden` (в CSS `min-height: 0`, `index.css:211`)
- `702` — `.catalog-main.overflow-hidden` — **нет `min-h-0` / `h-full`**
- `731` — `flex h-full flex-col overflow-hidden`
- `766` — `flex min-h-0 flex-1 overflow-hidden`
- `767-774` — панель чата: `min-w-0 flex-1 overflow-hidden` + `flex`/`hidden` — **нет `min-h-0`**
- `776` — `flex h-full w-full flex-col overflow-hidden`
- `Chat` `111` — `.catalog-chat.flex.h-full.flex-col` — **нет `min-h-0`**
- лента `117` — `.catalog-chat__scroll.flex-1.overflow-y-auto` — **нет `min-h-0`**
- композер — сосед ленты в той же колонке (`catalog-composer-area`)

В `index.css` у `.catalog-chat` нет правил высоты (только `__content` / `__empty` / composer width, `:267-268`). Высота целиком на Tailwind `h-full`.

Ниже `lg` чат/черновик — табы (`732-765`); на `lg` две колонки. Textarea растёт авто-height (`Chat.tsx:77-81`) до `max-h-40`.

## Затрагиваемые файлы
- `frontend/src/components/Chat.tsx` — автоскролл только контейнера ленты; guard на пустой `messages`; `min-h-0` на корне и `.catalog-chat__scroll`.
- `frontend/src/App.tsx` — закрыть разрывы `min-h-0` у `.catalog-main` и панели чата (`767-776`), чтобы колонка сжималась внутри viewport.
- `frontend/src/index.css` — только если `h-full` у `.catalog-chat` не резолвится: явная высота/`min-height: 0` на `.catalog-chat` / `.catalog-main`.

## План действий
1. Подтвердить гипотезу 1 в DevTools: на новой сессии после маунта `document.scrollingElement.scrollTop` и `scrollTop` у `.catalog-main` / `.catalog-layout` ненулевые, композер визуально сверху.
2. Заменить `scrollIntoView` на скролл только `.catalog-chat__scroll`: ref на контейнер ленты, `el.scrollTop = el.scrollHeight`. Не вызывать при `messages.length === 0`.
3. Проверить цепочку высот: добавить `min-h-0` там, где flex-ребёнок может распирать предка (`.catalog-main`, панель чата, `.catalog-chat`, `.catalog-chat__scroll`). Не ломать табы ниже `lg` и двухколоночный `lg`.
4. Если после п. 2–3 `h-full` у чата всё ещё `auto` — зафиксировать высоту в `index.css` (`.catalog-main` / `.catalog-chat { min-height: 0; height: 100%; }`).
5. Ручная проверка: пустая сессия; длинная история; отправка + стриминг; `lg` и табы; рост textarea до `max-h-40`. В консоли: `document.scrollingElement.scrollTop === 0`.

## Критерии приёмки (Definition of Done)
- [ ] Пустая сессия: виден empty-state, композер внизу, прокрутки окна нет.
- [ ] Сессия с длинной историей: скроллится только лента, композер зафиксирован внизу.
- [ ] После отправки и во время стриминга лента внизу, `document.scrollingElement.scrollTop === 0`.
- [ ] Проверено на `lg` (чат + черновик) и ниже (табы).
- [ ] Рост textarea до `max-h-40` не выталкивает композер за экран.
- [ ] Автоскролл не меняет `scrollTop` документа и overflow-hidden-обёрток.
- [ ] `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` зелёные.
