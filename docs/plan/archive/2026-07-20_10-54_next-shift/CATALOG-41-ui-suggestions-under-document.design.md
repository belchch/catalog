# CATALOG-41 — Дизайн UI

- **Источник:** docs/plan/next-shift/CATALOG-41-ui-suggestions-under-document.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Пользователь работает в композере чата планировщика (`Chat.tsx`) и должен однозначно различать две зоны:

1. **Документы** — состав сессии и выбор «+ документ» (attach к сообщению).
2. **Быстрые ответы** — starter-чипы или suggestions планировщика.

Сценарий:
1. Пользователь смотрит вниз панели чата (`border-t`).
2. Сначала (если есть) видит «Документы в сессии».
3. Сразу под ними — ряд выбранных к отправке docs и триггер `DocumentCombobox` с placeholder `"+ документ"`.
4. **Под** этим рядом — чипы быстрых ответов (`visibleSuggestions`).
5. Ниже — textarea и «Отправить»/«Стоп», затем «Создать скилл из сессии».

Быстрые ответы больше не стоят между сессионными документами и «+ документ», поэтому не читаются как часть doc-функциональности.

## Дерево компонентов и файлы

Изменяемый (новых компонентов и зависимостей нет):

- `frontend/src/components/Chat.tsx`
  - В футере композера (`border-t border-slate-800 p-3`) поменять **только порядок** двух соседних блоков:
    1. Ряд `selectedDocs` + `DocumentCombobox` — сразу после секции «Документы в сессии» (или в начале футера, если секция скрыта).
    2. Блок `visibleSuggestions` — **после** ряда docs, **перед** textarea.
  - Логика `visibleSuggestions`, `STARTER_SUGGESTIONS`, `onSend(s)`, `disabled={streaming}`, классы чипов и ряда docs — без изменений (если ниже не указано иное для a11y-обёртки).

Не трогать: `DocumentCombobox.tsx`, хуки, API, `App.tsx`, стили чипов/кнопок (кроме возможной обёртки suggestions — см. a11y).

## Layout и состояния

Порядок сверху вниз внутри composer-панели (заменяет порядок из CATALOG-28 / CATALOG-42 design, где suggestions шли над «+ документ»):

```
[опционально] Документы в сессии          ← sessionDocuments.length > 0
[всегда доступен] selectedDocs + «+ документ»
[если есть]       visibleSuggestions       ← starter или planner
textarea + Отправить/Стоп
«Создать скилл из сессии»
```

Структура (псевдоразметка):

```
<section «Документы в сессии»> … </section>     <!-- без изменений, mb-2 -->
<div ряд docs> selectedDocs… DocumentCombobox </div>  <!-- mb-2, как сейчас -->
<div suggestions> чипы… </div>                   <!-- mb-2, как сейчас -->
<div> textarea + submit </div>
<button> Создать скилл… </button>
```

Состояния (поведение без регрессий):

- **empty suggestions** (`visibleSuggestions.length === 0`, в т.ч. при `streaming`): блок suggestions не рендерится; ряд docs остаётся на месте над textarea.
- **empty session docs**: секция «Документы в сессии» скрыта; первым в футере идёт ряд «+ документ», под ним — suggestions (если есть).
- **starter** (`messages.length === 0`, не streaming): три стартовых чипа под «+ документ».
- **planner suggestions** (есть сообщения, `suggestions` непустой, не streaming): чипы планировщика на том же месте (под docs).
- **streaming**: suggestions скрыты (`[]`); docs-ряд и combobox disabled как сейчас.
- **error / reconnect**: вне скоупа — слоты в ленте сообщений не меняются.

Отступы: у ряда docs и у suggestions сохранить `mb-2`, чтобы зазор до следующего блока (suggestions → textarea или docs → textarea при пустых suggestions) оставался читаемым. Новых разделителей, заголовков («Быстрые ответы») и карточек не вводить.

## Взаимодействия

- **Клик по suggestion-чипу:** `onSend(s)` без `docIds` — как сейчас; текст уходит сразу, textarea/selectedDocs не трогаем.
- **Выбор «+ документ» / снятие selectedDocs:** без изменений; порядок блоков не влияет на attach при submit.
- **Tab-порядок:** session docs (если есть) → selectedDocs `×` / combobox → suggestion-кнопки → textarea → Отправить → «Создать скилл». Suggestions оказываются после doc-контролов — это ожидаемо и соответствует визуальному порядку.
- **Крайние случаи:**
  - Только «+ документ», без suggestions — норма; textarea сразу под docs.
  - Только suggestions (пустая сессия, нет selectedDocs) — чипы под триггером «+ документ», не над ним.
  - Длинные тексты suggestions — `flex-wrap gap-2` как сейчас; перенос строк не ломает порядок зон.

## Стиль и токены

Без новых цветов, радиусов, теней и зависимостей. Сохранить текущие утилиты:

- **Ряд docs:** `mb-2 flex flex-wrap items-center gap-1.5`; draft-пилюли indigo (`border-indigo-500/40 bg-indigo-600/15 …`); триггер combobox — `rounded-full …` как сейчас.
- **Suggestions:** `mb-2 flex flex-wrap gap-2`; кнопки `rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1 text-xs text-slate-200 hover:border-indigo-500 hover:bg-slate-800 disabled:opacity-50`.
- Визуальное разделение зон достигается **порядком** (docs → suggestions → input), а не новым UI: session-пилюли slate, draft indigo, suggestions — нейтральные pill-кнопки (как сейчас). Не унифицировать suggestions с draft-indigo и не добавлять заголовок секции для suggestions в этом шаге.

Консистентность с текущим тёмным UI чата (slate / indigo accents).

## Доступность (a11y)

- Кнопки suggestions остаются нативными `<button>`; `disabled` при streaming (блок и так пуст).
- Рекомендуемая минимальная доработка разметки (без смены стилей): обернуть блок suggestions в контейнер с `role="group"` и `aria-label="Быстрые ответы"` (или эквивалент), чтобы screen reader отделял группу от doc-контролов. Видимый заголовок не обязателен.
- Не менять `aria-label` у `DocumentCombobox` («Добавить документы в сессию») и у session/draft `×`.
- Фокус при клике по suggestion уходит в поток отправки (как сейчас); отдельного возврата фокуса в textarea не требуем.
- Контраст чипов — текущий; регрессий не вводить.

## Контракты данных (если нужны)

Не меняются. UI использует уже существующие props `Chat`:

- `suggestions: string[]` — ответы планировщика.
- `STARTER_SUGGESTIONS` — локальная константа при пустой ленте.
- `onSend(text, docIds?)` — клик по suggestion вызывает `onSend(s)` без `docIds`.
- `streaming` — скрывает suggestions и дизейблит doc-контролы.

Ссылки: план `docs/plan/next-shift/CATALOG-41-ui-suggestions-under-document.md`, текущая реализация `frontend/src/components/Chat.tsx` (логика `visibleSuggestions` ~стр. 83–87; разметка композера ~147–276).

## Критерии визуальной приёмки

- [ ] В композере порядок сверху вниз: (опционально «Документы в сессии») → ряд «+ документ» / selectedDocs → suggestions → textarea → «Создать скилл…».
- [ ] Стартовые чипы (пустая сессия) стоят **под** триггером «+ документ», а не над ним.
- [ ] Suggestions планировщика (после ответа с `suggestions`) стоят **под** рядом docs, а не между session-docs и «+ документ».
- [ ] При отсутствии suggestions ряд docs непосредственно над textarea; лишнего пустого зазора сверх `mb-2` у docs нет.
- [ ] Стили чипов suggestions и ряда docs визуально те же, что до шага (кроме порядка и опциональной `aria`-группы).
- [ ] Клик по suggestion по-прежнему отправляет текст через `onSend`; при streaming suggestions не видны.
- [ ] Tab-порядок следует визуальному: doc-контролы раньше suggestion-кнопок.
- [ ] У блока suggestions есть доступное имя группы (`aria-label` / `role="group"`), если обёртка добавлена по спеке.
