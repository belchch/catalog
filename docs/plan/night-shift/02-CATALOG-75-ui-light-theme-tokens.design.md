# CATALOG-75 — Дизайн UI

- **Источник:** docs/plan/night-shift/02-CATALOG-75-ui-light-theme-tokens.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Визуальный язык не меняется — цель чисто инженерная: перевести весь UI на семантические токены и снести двухслойную перекраску. Для пользователя «до» и «после» должны быть визуально неотличимы, но с двумя честными улучшениями:

1. Исчезают тёмные пятна там, где перекраска по списку не срабатывала (бейджи скиллов `python`/`ai`, run-meta, trace-блоки, оверлеи модалок сейчас рендерятся тёмными на светлом фоне).
2. Кнопки композера «Отправить»/«Стоп» становятся честными icon-кнопками, а не текстом, спрятанным через `font-size: 0`.

Пользовательский путь без изменений: чат слева, черновик справа (на мобиле — табы «Чат / Черновик»), сайдбар со свёрнутыми секциями «Сессии / Документы / Скиллы», прогон скилла открывает `RunView`, настройки/таймаут/выбор трека — в модалках. Экран остаётся светлым: белый фон, сайдбар `#eef7ff`, карточки с мягкой тенью, акцент `#1d83c4`.

## Дерево компонентов и файлы

Слой токенов (источник правды цвета):

- `frontend/src/index.css` — `:root` наполняется CSS-переменными (см. «Стиль и токены»); удаляется блок перекраски (строки 62–82), структурные селекторы (85–90), хак композера (106–109). Хардкод hex внутри `.catalog-*` заменяется на `var(--…)`.
- `frontend/tailwind.config.cjs` — `theme.extend.colors / borderRadius / boxShadow` мапят токены в утилиты Tailwind.

Слой примитивов (рекомендуемый подход — `@layer components` в `index.css`, не React-компоненты):

- `.btn` + модификаторы `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-danger` / `.btn-icon` — единая кнопка.
- `.badge` + `.badge-info` / `.badge-accent` / `.badge-success` / `.badge-warning` / `.badge-danger` / `.badge-neutral` — статусные бейджи и теги.
- `.field` — инпут/textarea/select.
- `.modal-overlay` + `.modal-card` — единый оверлей и контейнер модалки.
- `.chip` / `.chip-brand` — «таблетки» документов в композере.

Обоснование выбора `@layer components`: кодовая база уже опирается на семантические CSS-классы (`.catalog-*`, `.icon-button`, `.artifact-*`), а не на React-примитивы; централизация в `@layer components` даёт минимальный диф по 20 файлам и единый источник токенов без новой директории и новых пропсов. Если генератору удобнее — допустимо вынести повторяющиеся строки классов в константы внутри компонента, но новые UI-зависимости и UI-библиотеки запрещены.

Слой потребителей (замена `slate-*`/`indigo-*`/сырых палитр на токены/примитивы):

- `frontend/src/App.tsx` — actions-кнопки секций сайдбара, мобильные табы «Чат/Черновик», `git sha`.
- `frontend/src/components/Chat.tsx` — композер: textarea, чипы документов, быстрые ответы, icon-кнопки «Отправить»/«Стоп», баннер редактирования, блок ошибки сборки.
- `frontend/src/components/CollapsibleSection.tsx` — заголовок секции получает явный класс `.catalog-section-header` (взамен селектора на цепочке утилит).
- `frontend/src/components/SkillsPanel.tsx` — поиск, тулбар, список скиллов, бейджи тегов (`python`→info, `ai`→accent), точка статуса (committed→success, draft→warning), меню «ещё», подтверждение удаления, кнопки «В док»/«На экран».
- `frontend/src/components/RunView.tsx` — статус-бейдж прогона (ok→success, error→danger), панели «Лента шагов»/«Результат», run-meta блок, плашка «Документ создан».
- `frontend/src/components/TraceSteps.tsx` — цвета шагов (script/reasoning/tool_result/verify), блоки `pre` с кодом/результатом/ошибкой.
- `frontend/src/components/SessionTimeoutModal.tsx`, `SkillSettingsModal.tsx`, `SkillTrackPicker.tsx` — единый оверлей+карточка через `.modal-overlay`/`.modal-card`, поля через `.field`, кнопки через `.btn-*`.
- Остальные `*.tsx` (ChatMessage, SessionsPanel, DocumentList, DocumentCombobox, ModelCombobox, ModelSelector, ArtifactsPanel, MarkdownView, MessageCommands, SkillTrackPicker) — вычистить точечные `slate-*`/`indigo-*` на токены.

## Layout и состояния

Структура экрана и её поведение не трогаются — меняется только палитра источника. По состояниям определяем целевую светлую подачу (сейчас часть из них тёмная):

- **loading** (кнопки «Обновить», «Собираю скилл…», «Сохранение…»): текст-лейбл меняется как сейчас; disabled-вид = `surface.muted` фон + `ink.faint` текст + `cursor-not-allowed`, без `opacity-50`.
- **empty**: «Скиллов пока нет…», «Шаги появятся здесь…», «нет документов», пустой чат — текст `ink.faint` на белом.
- **error**: баннер ошибки сборки в чате и алерты в модалках — `danger.soft` фон + `danger.line` рамка + `danger.ink` текст; строчные ошибки (`Ошибка: …`) — `danger.ink`. Никаких `bg-red-950/40`.
- **success**: статус прогона ok, плашка «Документ создан», галочки trace — `success.soft`/`success.ink`. Точка committed — `success`.
- **reconnecting / closed**: статус-строка — `warning.ink` текст, кнопка «Переподключить» — `.btn-secondary`.

Мобильный брейкпоинт `<1024px` без регрессий: сайдбар скрыт, табы «Чат/Черновик» видны, `artifact-summary`/`artifact-editor` — полноэкранные без рамки/тени/радиуса (правило в `@media` сохраняется).

## Взаимодействия

- **Композер, «Отправить»**: честная icon-кнопка — `<button aria-label="Отправить">` со стрелкой ↑ по центру; `inline-flex size-9 items-center justify-center rounded-full shrink-0`, фон `brand`, hover `brand.hover`, disabled — приглушённый круг (`surface.muted` + `ink.faint`, `cursor-not-allowed`), без исчезновения.
- **Композер, «Стоп»**: тот же размер/форма, глиф ■ по центру, фон `danger`, hover `danger.hover`, `aria-label="Остановить генерацию"`. Обе кнопки одинакового диаметра (36×36), заменяют друг друга без сдвига layout.
- **Чипы документов / быстрые ответы / теги сессии**: `.chip` — pill на `surface.muted`, рамка `line`, текст `ink.muted`; выбранные документы — `.chip-brand` (`brand.soft` + `brand.ink`). Кнопка «×» — `ink.faint`, hover `ink`.
- **Список скиллов**: строка hover → `surface.hover`; выбранная (`aria-selected`) → `brand.soft` фон + `ink` текст (сохранить текущий `aria-current`/`aria-selected` контракт). Клавиатура ↑/↓/Enter/Escape не меняется.
- **Тулбар скиллов**: `Переименовать/Редактировать/Коммит/⋯` — `.btn-secondary`; «Удалить» в меню и подтверждение — `danger.ink`/`.btn-danger`. Меню «⋯» — карточка на `surface` с рамкой `line` и тенью.
- **Модалки**: клик по `.modal-overlay` вне карточки поведение не меняем (Escape закрывает там, где уже реализовано); focus при открытии — как сейчас.
- **Крайние случаи**: очень длинные имена скиллов/документов — `truncate` сохраняется; текст ошибки — `whitespace-pre-wrap break-words`; disabled-состояния читаемы (не прозрачный текст на белом).

## Стиль и токены

Единый конвейер: **CSS-переменные `:root` → семантические цвета в `tailwind.config.cjs` → утилиты в компонентах**. Значения взяты из текущего светлого CSS и слоя перекраски (`index.css` 16–159), визуальный язык сохраняется.

### CSS-переменные (`:root`)

Поверхности:
- `--surface: #ffffff`
- `--surface-muted: #f5f6f6` (приглушённая поверхность; бывш. `bg-slate-800`)
- `--surface-sunken: #e7eaeb` (утопленная; бывш. `bg-slate-700`, фон тегов)
- `--surface-hover: #e9eff2` (hover-заливка контролов)

Линии:
- `--line: #e4e6e5`
- `--line-strong: #b9c5cc` (пунктир / усиленные разделители)
- `--line-brand: #4b9fcf`

Текст (ink):
- `--ink: #292c31`
- `--ink-muted: #4f565d`
- `--ink-faint: #717981`
- `--ink-placeholder: #8e969c`

Бренд:
- `--brand: #1d83c4`
- `--brand-hover: #146fa9`
- `--brand-soft: #e1f1fa`
- `--brand-ink: #155e91`
- `--brand-link-hover: #0c6ba5`

Статусы (фон бейджа + контрастный текст ≥ 4.5:1 на белом):
- danger: `--danger: #d64545`, `--danger-hover: #be3b3b`, `--danger-soft: #fff1f1`, `--danger-ink: #a63838`, `--danger-line: #f0c6c6`
- success: `--success-soft: #e3f4ec`, `--success-ink: #1c6b48`, `--success-line: #bfe3d0`
- warning: `--warning-soft: #fbeecd`, `--warning-ink: #8a5a12`, `--warning-line: #f2d5aa`
- info (тег `python`, нейтральная инфо-подача): `--info-soft: #e1f1fa`, `--info-ink: #155e91`
- accent (тег `ai`): `--accent-soft: #efe6f8`, `--accent-ink: #7a3ea6`

Оверлей и элевация:
- `--overlay: rgba(23, 33, 41, .35)`
- `--shadow-card: 0 4px 18px rgba(42, 54, 62, .09)`
- `--radius-control: 8px`, `--radius-card: 20px`, `--radius-card-lg: 24px`

Примечание про два тег-хью: `python`/`ai` сейчас закодированы разными цветами (`sky`/`fuchsia`), но эти бейджи не попали в слой перекраски и рендерятся тёмными — устойчивой светлой подачи у них ещё нет. Дизайн сохраняет двухцветное различение в светлой форме: `python` → `info` (синий), `ai` → `accent` (фиолетовый). Это не расширение визуального языка, а перенос уже существовавшего семантического различия на светлую тему.

### Мапинг в Tailwind (`theme.extend`)

`colors`:
- `surface: { DEFAULT, muted, sunken, hover }`
- `line: { DEFAULT, strong, brand }`
- `ink: { DEFAULT, muted, faint, placeholder }`
- `brand: { DEFAULT, hover, soft, ink }`
- `danger: { DEFAULT, hover, soft, ink, line }`
- `success: { soft, ink, line }`
- `warning: { soft, ink, line }`
- `info: { soft, ink }`
- `accent: { soft, ink }`

Каждое значение — `var(--…)`. Дополнительно: `borderRadius.card`/`card-lg`, `boxShadow.card`.

### Как применять в компонентах

- Кнопка primary: `bg-brand text-white hover:bg-brand-hover` (или `.btn-primary`); disabled — `disabled:bg-surface-muted disabled:text-ink-faint disabled:cursor-not-allowed`.
- Кнопка secondary/ghost: `bg-surface-muted text-ink-muted hover:bg-surface-hover` / прозрачный фон + hover.
- Бейдж: `bg-{info|accent|success|warning|danger}-soft text-{…}-ink`.
- Поверхности/панели: `bg-surface` (карты), `border-line`; run/trace-блоки — `bg-surface-muted` вместо `bg-slate-950/*`.
- Текст: `text-ink` / `text-ink-muted` / `text-ink-faint`; плейсхолдеры `placeholder:text-ink-placeholder`.
- Оверлей модалки: `bg-[color:var(--overlay)]` (или класс `.modal-overlay`) — единый для всех трёх модалок.

## Доступность (a11y)

- Каждый интерактивный элемент имеет видимый `focus-visible`: кольцо на `brand` (`focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand`). Заменить существующие `focus:ring-slate-600`/`ring-indigo-500` на `ring-brand`.
- Icon-кнопки композера обязаны иметь `aria-label` («Отправить», «Остановить генерацию»); глиф помечается `aria-hidden`.
- Контраст текста бейджей и статусов на белом ≥ 4.5:1 (значения `*-ink` подобраны под это).
- Disabled ≠ невидимость: `surface.muted` + `ink.faint`, читаемо; не полагаться на `opacity-50` как основной механизм.
- Сохранить существующие роли/атрибуты: `role="listbox"/"option"`, `aria-selected`, `aria-current`, `role="dialog" aria-modal`, `role="tablist"/"tab"/"tabpanel"`, `role="radiogroup"/"radio"`, `aria-expanded`, `aria-busy`, `aria-live`.

## Контракты данных (если нужны)

Изменений в данных/API/хуках нет (anti-goal плана). UI продолжает читать те же типы (`SkillOut`, `DocumentOut`, `RunStep`, `UseRunStreamResult`, `SkillPreview`, `SkillTrack`) и те же пропсы. Единственное поведенческое исключение, разрешённое планом: текст кнопок «Отправить»/«Стоп» заменяется иконкой с `aria-label` — обработчики `onClick`/`disabled` остаются прежними.

## Критерии визуальной приёмки

- [ ] Экран визуально идентичен текущей светлой теме: белый фон, сайдбар `#eef7ff`, карточки с радиусом 20–24px и мягкой тенью, акцент `#1d83c4`.
- [ ] В `frontend/src` нет `slate-*` и `indigo-\d`; нет `(bg|text|border)-(red|emerald|amber|sky|fuchsia|black)-`.
- [ ] Все цвета берутся из токенов; хардкод hex вне `:root` отсутствует (в т.ч. внутри `.catalog-*`).
- [ ] Кнопки «Отправить» и «Стоп»: круг 36×36, глиф по центру, одинаковый диаметр, `aria-label`; различимы состояния hover/active/focus-visible/disabled; хак `font-size: 0` + `::after` удалён.
- [ ] Ни одного тёмного пятна: run-meta, trace-блоки (`pre` кода/результата/ошибки), статусы ok/error, бейджи `python`/`ai`, оверлеи всех трёх модалок — светлые.
- [ ] Статусные бейджи (`python`/`ai`, `draft`/`committed`, `ok`/`error`) читаемы на белом, контраст текста ≥ 4.5:1; `python` и `ai` визуально различимы (info-синий vs accent-фиолетовый).
- [ ] Каждый интерактивный элемент имеет видимый `focus-visible` (кольцо на `brand`).
- [ ] Disabled-состояния читаемы (не прозрачный текст на белом): `surface.muted` + `ink.faint` + `cursor-not-allowed`.
- [ ] Три модалки (`SessionTimeoutModal`, `SkillSettingsModal`, `SkillTrackPicker`) визуально согласованы: единый оверлей `rgba(23,33,41,.35)`, одинаковый радиус/граница/тень карточки, единая типографика заголовка.
- [ ] Заголовок секции сайдбара (`CollapsibleSection`) оформлен явным классом, без зависимости от цепочки Tailwind-утилит.
- [ ] 1440px и 375px: на мобиле сайдбар скрыт, табы «Чат/Черновик» работают, `artifact-summary`/`artifact-editor` — полноэкранные без рамки/тени; регрессий нет.
