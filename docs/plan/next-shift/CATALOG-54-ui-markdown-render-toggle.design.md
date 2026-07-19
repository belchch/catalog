# CATALOG-54 — Дизайн UI

- **Источник:** docs/plan/next-shift/CATALOG-54-ui-markdown-render-toggle.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Пользователь читает Markdown-контент в двух местах: ответы ассистента в чате и блок «Результат» в RunView. По умолчанию видит красивый рендер (заголовки, списки, код, таблицы GFM). Одним кликом переключается в режим исходного текста без интерпретации разметки — и обратно.

Сценарий:
1. Ассистент присылает сообщение с MD → пузырь показывает рендер (`md`), над/рядом с контентом — компактный переключатель `md | text`.
2. Пользователь жмёт `text` → видит исходную строку как есть (`whitespace-pre-wrap`), разметка не интерпретируется.
3. Пользователь жмёт `md` → снова GFM-рендер.
4. В RunView при появлении `resultText` — тот же переключатель над телом результата (default `md`); поведение идентично чату.
5. User-сообщения и tool-строки остаются plain text без toggle (вне скоупа «красивого md»).

Documents preview и новые MD-библиотеки — вне скоупа.

## Дерево компонентов и файлы

Новый:

- `frontend/src/components/MarkdownView.tsx`
  - Единый блок: сегментный toggle `md | text` + тело контента.
  - Props: `text: string`; опционально `defaultMode?: 'md' | 'text'` (default `'md'`); опционально `className?: string` для оболочки тела (размер/контекст пузыря vs панели результата).
  - Режим `md`: `ReactMarkdown` + `remarkGfm` внутри контейнера с классом `.md-body` (см. стили).
  - Режим `text`: `<pre className="… whitespace-pre-wrap break-words …">` с сырым `text` (без ReactMarkdown).
  - Локальный state режима; при смене `text` (новое сообщение / новый result) режим **не сбрасывать** внутри одного mount; при размонтировании (другой message instance / уход с RunView) — снова `defaultMode`.

Изменяемые:

- `frontend/src/components/ChatMessage.tsx`
  - Ветка `assistant`: заменить plain `div` с `{message.content}` на оболочку пузыря + `<MarkdownView text={message.content} defaultMode="md" />`.
  - User и tool — без изменений (plain).
- `frontend/src/components/RunView.tsx`
  - Убрать прямой импорт `ReactMarkdown` / `remarkGfm`.
  - При `run.resultText`: рендерить `<MarkdownView text={run.resultText} defaultMode="md" />` вместо текущего блока.
  - Empty/waiting copy («Нет текстового результата…» / «Ожидание…») — без toggle, как сейчас.
- `frontend/src/index.css`
  - Переименовать селекторы `.run-markdown` → `.md-body` (те же правила: h1–h3, p, ul/ol, code/pre, table, blockquote).
  - Допустимо оставить alias `.run-markdown` как дублирующий селектор **только** если нужен мягкий переход; предпочтительно один класс `.md-body`.

Не трогать: `Chat.tsx` layout, `ArtifactsPanel`, documents viewer, `package.json` (новых deps нет).

## Layout и состояния

### MarkdownView — структура

```
┌─────────────────────────────────────────────┐
│                          [ md ] [ text ]    │  ← сегмент, выравнивание вправо
│                                             │
│  (тело: md-body | pre text)                 │
└─────────────────────────────────────────────┘
```

- Toggle — одна строка над контентом, `flex justify-end`, gap минимальный (`gap-1`).
- Сегменты: две кнопки `type="button"`, подписи строго `md` и `text` (lowercase, как в ТЗ).
- Активный: `bg-indigo-600 text-white`; неактивный: `bg-slate-800 text-slate-300` (паттерн arity в `SkillSettingsModal` / mobile toggle в App).
- Размер кнопок: `text-[10px]` или `text-xs`, `rounded px-1.5 py-0.5` — компактно, чтобы не раздувать пузырь чата.
- Тело:
  - **md:** `div.md-body` + опциональный `className` (чат: `text-sm text-slate-100`; RunView: `text-sm text-slate-200`).
  - **text:** `pre` с `whitespace-pre-wrap break-words font-mono text-xs` (или `text-sm` в RunView), цвет как у соседнего контента (`text-slate-100` / `text-slate-200`).

### Встраивание в ChatMessage (assistant)

```
┌ my-2 flex justify-start ────────────────────┐
│  ┌ max-w-[80%] rounded-lg bg-slate-800      │
│  │   px-3 py-2                               │
│  │   MarkdownView                            │
│  └──────────────────────────────────────────┘
└──────────────────────────────────────────────┘
```

- Пузырь сохраняет текущие цвета/скругление; `whitespace-pre-wrap` с оболочки снимается (за него отвечает MarkdownView в text-режиме / MD-стили в md).
- Toggle внутри пузыря, над текстом — не отдельная колонка снаружи.

### Встраивание в RunView

В правой колонке «Результат», после баннера документа / кнопки Save (если есть):

```
Результат
[Документ создан…]          ← как сейчас, вне MarkdownView
[Сохранить…]                ← как сейчас
              [ md ] [ text ]
<body result>
```

- Toggle только когда есть непустой `run.resultText`.
- Колонка по-прежнему `overflow-y-auto`.

### Состояния

| Состояние | Что видно |
|-----------|-----------|
| **md (default)** | Toggle: `md` активен; тело — GFM-рендер в `.md-body`. |
| **text** | Toggle: `text` активен; тело — сырой `text` в `pre`, без MD. |
| **empty text** | Не монтировать MarkdownView: ChatMessage с пустым content не ожидается; RunView — существующий empty/waiting. |
| **streaming assistant** | Пока `content` растёт — MarkdownView перерисовывает тело; режим пользователя сохраняется. Частичный MD в md-режиме допустим (как обычно у react-markdown). |
| **plain без разметки** | В md-режиме выглядит как обычный абзац; toggle всё равно доступен. |

Отдельных loading/error для MarkdownView нет: контент синхронный из props.

## Взаимодействия

- Клик `md` / `text` переключает локальный режим; повторный клик по активному — no-op (кнопка может быть `aria-pressed` / disabled-look через стиль активного, без блокировки фокуса).
- Клавиатура: обе кнопки в tab-порядке; Enter/Space активируют (нативные `<button>`).
- Смена сообщения: каждый `ChatMessage` — свой instance → свой режим с `defaultMode="md"`.
- Уход с RunView и возврат — снова `defaultMode="md"`.
- Копирование: в text-режиме пользователь выделяет исходник; в md — выделенный видимый текст (как в браузере). Отдельной кнопки Copy в скоупе нет.
- Крайний случай: очень длинный MD / широкие таблицы — горизонтальный скролл у `pre`/`table` внутри `.md-body` (уже в CSS `pre { overflow-x: auto }`); пузырь чата `max-w-[80%]` + `overflow-x-auto` на теле при необходимости, чтобы не ломать layout колонки.

## Стиль и токены

- Палитра и плотность — как текущий dark UI: `slate-*`, акцент активного сегмента `indigo-600`.
- Типографика MD: перенос правил из `.run-markdown` в `.md-body` без смены визуальных значений (заголовки, списки, code/pre, tables, blockquote).
- В чате MD чуть плотнее допустим за счёт `text-sm` на контейнере; отдельные «chat-only» overrides в CSS **не обязательны** в срезе — общие `.md-body` достаточно.
- Не вводить `@tailwindcss/typography` и не добавлять пакеты.
- Карточки/тени вокруг toggle не вводить — плоские сегмент-кнопки как в остальном UI.

## Доступность (a11y)

- Группа переключателя: контейнер с `role="group"` и `aria-label="Режим отображения"` (или англ. «View mode» — выбрать русский, консистентно с UI «Результат» / «К чату»).
- Каждая кнопка: `aria-pressed={mode === 'md'|'text'}`.
- Фокус-стили кнопок: видимый ring в тон существующих focus-паттернов проекта (`focus:outline-none focus:ring-1 focus:ring-indigo-500` или нативный outline — главное, чтобы фокус был виден на тёмном фоне).
- Контраст активного сегмента: белый на `indigo-600`; неактивный `slate-300` на `slate-800` — как у соседних сегментов App/SkillSettings.
- В md-режиме заголовки — семантические `h1`–`h3` от react-markdown (приемлемо внутри пузыря для среза; не понижать до `div` без нужды).

## Контракты данных (если нужны)

Новых API/WS нет. Источники текста:

| Поверхность | Источник | Props |
|-------------|----------|--------|
| Chat assistant | `PlannerMessage.content` (`role === 'assistant'`) | `text={message.content}`, `defaultMode="md"` |
| RunView результат | `run.resultText` из `UseRunStreamResult` | `text={run.resultText}`, `defaultMode="md"` |

Зависимости (уже в `frontend/package.json`): `react-markdown`, `remark-gfm`. Новых не добавлять.

Ссылка на план: `docs/plan/next-shift/CATALOG-54-ui-markdown-render-toggle.md`.

## Критерии визуальной приёмки

- [ ] В пузыре assistant-сообщения есть сегмент `md | text`; по умолчанию активен `md`, контент отрендерен как Markdown (заголовки/списки/code/tables при наличии в тексте).
- [ ] Переключение на `text` показывает исходник без интерпретации `*`, `#`, таблиц и т.п.; обратно на `md` — снова рендер.
- [ ] User-пузыри и tool-строки без переключателя и без MD-рендера.
- [ ] В RunView при непустом результате тот же toggle; default `md`; empty/waiting без toggle.
- [ ] Стили MD общие через `.md-body` (бывший `.run-markdown`); визуально читабельны на тёмном фоне, таблицы и code-блоки не «ломают» колонку (скролл по ширине при необходимости).
- [ ] Сегменты визуально согласованы с существующими indigo/slate кнопками-сегментами; toggle компактный, не доминирует над контентом.
- [ ] Новых MD-зависимостей в UI нет; используется только `react-markdown` + `remark-gfm`.
