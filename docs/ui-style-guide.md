# UI Style Guide — Catalog

Светлая тема. Источник цвета: CSS-переменные в `frontend/src/index.css` (`:root`) → семантические утилиты в `frontend/tailwind.config.cjs` → классы в компонентах / `@layer components`.

## Токены

| Группа | Tailwind | Назначение |
|--------|----------|------------|
| surface | `bg-surface`, `bg-surface-muted`, `bg-surface-sunken`, `bg-surface-hover` | Фон страницы, приглушённые панели, теги, hover |
| line | `border-line`, `border-line-strong`, `border-line-brand` | Рамки и разделители |
| ink | `text-ink`, `text-ink-muted`, `text-ink-faint`, `placeholder:text-ink-placeholder` | Текст |
| brand | `bg-brand`, `hover:bg-brand-hover`, `bg-brand-soft`, `text-brand-ink` | Акцент `#7c3aed` (фиолетовый) |
| danger | `bg-danger`, `bg-danger-soft`, `text-danger-ink`, `border-danger-line` | Ошибки, стоп |
| success | `bg-success`, `bg-success-soft`, `text-success-ink` | ok / committed / сессия «готово» |
| warning | `bg-warning`, `bg-warning-soft`, `text-warning-ink` | draft / reconnect |
| info | `bg-info-soft`, `text-info-ink` | тег `python` |
| accent | `bg-accent`, `hover:bg-accent-hover`, `bg-accent-soft`, `text-accent-ink`, `border-accent-line` | Яркий фиолетовый `#7c3aed`: CTA «Создать скилл» (градиент в фуксию), hover подсказок, тег `ai`, сессия «планирование» |
| teal | `bg-teal-soft`, `text-teal-ink` | тип документа, input `documents` |
| rose | `bg-rose-soft`, `text-rose-ink` | arity трека, input `previous` |
| gold | `text-gold`, `text-gold-ink` | Тёплый контраст-акцент: плашка-логотип «C», иконка пера, индикатор «планировщик думает» |

Логотип в шапке: золотая плашка «C» (26px, radius 8) + словомарка «Catalog» шрифтом Space Grotesk (700, сплошной `--ink`) + подзаголовок через тонкий разделитель. Градиентный текст не используется.
| elev | `rounded-card` / `rounded-card-lg`, `shadow-card` | Карточки 20–24px |

Оверлей модалок: `var(--overlay)` / класс `.modal-overlay`. Сайдбар: `var(--sidebar)` (`#f3f8fc`).

## Примитивы (`@layer components`)

| Класс | Когда |
|-------|--------|
| `.btn-primary` | Главное действие (сохранить, собрать, «В док») |
| `.btn-accent` | Фиолетовый градиентный CTA («Создать скилл») |
| `.btn-secondary` | Вторичное (обновить, отмена, «На экран», переподключить) |
| `.btn-ghost` | Тихий текст/иконка без заливки |
| `.btn-danger` | Деструктивное подтверждение |
| `.btn-icon-brand` / `.btn-icon-danger` | Круг 36×36 в композере (отправить / стоп) |
| `.badge-*` | Статусы и теги (`info`/`accent`/`success`/`warning`/`danger`/`teal`/`rose`/`neutral`) |
| `.field` | input / textarea / select |
| `.chip` / `.chip-brand` | Документы в композере (нейтральный / выбранный) |
| `.modal-overlay` + `.modal-card` | Все модалки |

## Состояния

- **Disabled:** `surface-muted` + `ink-faint` + `cursor-not-allowed` (не `opacity-50`).
- **Focus-visible:** кольцо `ring-2 ring-brand`.
- **Error:** `bg-danger-soft` + `border-danger-line` + `text-danger-ink`.
- **Selected row:** `bg-brand-soft` + `text-ink` (список скиллов); активная сессия/док — `bg-brand text-white`.

Не использовать сырые палитры Tailwind (`slate-*`, `indigo-*`, `red-*`, …) в `frontend/src`.
