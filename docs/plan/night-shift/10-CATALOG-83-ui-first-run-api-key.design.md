# CATALOG-83 — Дизайн UI: экран ввода API-ключа при первом запуске

- **Источник:** docs/plan/night-shift/10-CATALOG-83-ui-first-run-api-key.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Первый запуск на чистой машине: ключи провайдера ещё не заданы (ни в env, ни в persist). До любой работы с воркспейсом пользователь должен увидеть один экран онбординга и ввести ключ.

Сценарий:

1. Пользователь открывает приложение в браузере.
2. Пока статус setup неизвестен — нейтральный полноэкранный лоадер (без хедера, сайдбара, пикера).
3. `keys_configured === false` → показываем **только** `SetupKeyScreen` (полноэкранный онбординг), основной layout не рендерится и недоступен.
4. Пользователь выбирает провайдера (OpenRouter / z.ai), вставляет ключ в password-поле, жмёт «Сохранить ключ».
5. Успех → экран исчезает, рендерится обычный shell приложения. Воркспейс ещё не открыт — работает empty state из CATALOG-80 («Воркспейс не открыт» + кнопка «Открыть папку»).
6. Ошибка (401 / 422 / сеть) → текст ошибки на форме, экран не сбрасывается, введённые данные сохраняются, можно повторить.
7. Повторный вход при уже настроенных ключах экран не показывает — сразу основной layout.

Контракт бэкенда (готов в code-шаге):

- `GET /setup` → `{ keys_configured: boolean, provider: string, openrouter_configured: boolean, zai_configured: boolean }`. Секретов нет.
- `PUT /setup/keys` body `{ openrouter_api_key?: string | null, zai_api_key?: string | null }` → тот же `SetupOut`. Нужно передать минимум одно поле, иначе `422`. Секрет в ответ не возвращается.

Замечание по скоупу: поле «base URL» из плана в контракт `/setup/keys` не входит — бэкенд его не принимает, поэтому в этом срезе base URL **не показываем** (можно добавить отдельным тикетом при расширении контракта).

## Дерево компонентов и файлы

- `frontend/src/api.ts` — **изменить**: добавить тип `SetupOut` и функции:
  - `getSetup(): Promise<SetupOut>` → `GET /setup`.
  - `saveProviderKey(input: { openrouter_api_key?: string; zai_api_key?: string }): Promise<SetupOut>` → `PUT /setup/keys` (JSON, method `PUT`). Ключ уходит только здесь; в `getSetup` его нет.
- `frontend/src/hooks/useSetup.ts` — **новый** (тонкий хук статуса setup, чтобы не раздувать App):
  - Возвращает `{ status: 'unknown' | 'ready', keysConfigured: boolean, markConfigured: (s: SetupOut) => void }`.
  - На маунте зовёт `getSetup()`; при ошибке сети трактует статус как «неизвестно, но экран показать» безопаснее → по умолчанию `keysConfigured=false` (лучше лишний раз показать форму, чем пустить в нерабочий UI). Значение из ответа — источник истины.
  - `markConfigured` вызывается из `SetupKeyScreen` после успешного `saveProviderKey`, переводит в `ready`/`keysConfigured=true` без повторного запроса.
- `frontend/src/components/SetupKeyScreen.tsx` — **новый**: полноэкранная форма онбординга.
- `frontend/src/App.tsx` — **изменить**: ветвление «лоадер / SetupKeyScreen / обычный shell» на верхнем уровне рендера; проброс `keysConfigured` в `useSettings`.
- `frontend/src/hooks/useSettings.ts` — **изменить**: принять флаг `enabled` (= `keysConfigured`); не дёргать `listProviders` / `getProviderModels` пока ключей нет (иначе 502, как в CATALOG-68). Когда `enabled` становится `true` — выполнить первичную загрузку.

Новые зависимости не вводятся (React 19 + TS + Tailwind v3, существующие утилиты/классы).

## Layout и состояния

Верхний уровень `App` (до текущего `catalog-shell`):

- **`status === 'unknown'`** → полноэкранный нейтральный лоадер: контейнер `flex h-screen items-center justify-center` на `bg-surface`, по центру `role="status" aria-live="polite"` текст «Загрузка…» цветом `text-ink-faint`. Без хедера/сайдбара.
- **`keysConfigured === false`** → `<SetupKeyScreen onConfigured={markConfigured} />`, ничего больше.
- **`keysConfigured === true`** → существующий shell без изменений (включая empty state воркспейса из CATALOG-80).

`SetupKeyScreen` — полноэкранная страница (НЕ overlay-модалка, за ней ничего нет):

- Внешний контейнер: `flex min-h-screen items-center justify-center bg-surface p-4`.
- Карточка по центру: класс `modal-card max-w-md` (переиспользуем токен карточки) + внутренний вертикальный ритм `space-y-4`.
- Шапка карточки: строка с фирменной меткой (`catalog-mark` «C») и заголовком `h1` `text-base font-semibold text-ink` — «Настройка Catalog». Подзаголовок `text-xs text-ink-faint` — «Добавьте ключ LLM-провайдера, чтобы начать работу».
- Форма (`<form>`), блоки сверху вниз:
  1. Выбор провайдера.
  2. Поле ключа (password).
  3. Блок ошибки (условный).
  4. Кнопка submit.
  5. Подсказка «где взять ключ».

Состояния формы:

- **idle** — поля активны, submit активен если ключ непустой (после `trim`).
- **submitting** — все поля и submit `disabled`; текст кнопки «Сохранение…»; `aria-busy` на форме.
- **error** — блок ошибки виден (`text-xs text-danger-ink`, `role="alert"`), поля снова активны, значения сохранены, фокус остаётся на форме.
- **success** — компонент размонтируется, т.к. App переключается на основной shell (отдельного «успешного» экрана внутри не нужно).
- **empty (ключ пуст)** — submit `disabled`, без текста ошибки (пассивная валидация).

## Взаимодействия

- **Выбор провайдера:** два варианта — `openrouter` (подпись «OpenRouter») и `zai` (подпись «z.ai»). Реализация — `radiogroup` из двух радиокнопок (компактнее и доступнее select для 2 опций) ИЛИ `<select className="field">`; допустимы оба, приоритет — radiogroup с видимыми подписями. По умолчанию выбран `openrouter`. Смена провайдера очищает текст ошибки (не очищает введённый ключ обязательно, но допустимо очистить — решение генератора; ошибку сбросить нужно).
- **Ввод ключа:** одно поле `type="password"`, класс `field`, `autoComplete="off"`, `spellCheck={false}`, автофокус при маунте. Placeholder — нейтральный («Вставьте API-ключ»). Опционально кнопка-глазок show/hide (переключает `type` password/text) — не обязательна, но если делать, то через `btn-ghost`/`icon-button` с `aria-label` «Показать/Скрыть ключ». Секрет с сервера никогда не подставляется в поле.
- **Submit:** по клику на кнопку и по Enter в поле (`<form onSubmit>`). Формируем тело: для выбранного провайдера кладём соответствующее поле (`openrouter_api_key` или `zai_api_key`) с `trim()`-значением; второе поле не отправляем. Вызываем `saveProviderKey`.
  - Успех → `onConfigured(result)` (App покажет основной shell).
  - Провал → `setError(extractApiDetail(e))` (используем существующий `extractApiDetail` / `ApiError`), `submitting=false`.
- **Крайние случаи:**
  - Пустой/пробельный ключ → submit заблокирован, POST не уходит (защита от 422 «at least one api key field is required»).
  - `401` от провайдера / невалидный ключ → показываем `detail` как есть на форме; экран не сбрасывается.
  - Сетевая ошибка → тот же блок ошибки, разрешаем повтор.
  - Двойной сабмит исключён через `submitting`-guard.

## Стиль и токены

Только существующие утилиты/классы (ADR-0011, `index.css`):

- Карточка: `modal-card max-w-md` (радиус, граница `border-line`, фон `bg-surface`, тень `shadow-card`), внутренний `space-y-4`.
- Заголовки/текст: `text-base font-semibold text-ink` (h1), `text-xs text-ink-faint` (подписи/хелп), метки полей `text-[11px] text-ink-faint` в стиле существующих секций.
- Поля ввода/селект: класс `field`.
- Радио провайдера: обёртки в стиле выбираемых строк — `flex items-center gap-2 rounded border border-line bg-surface-muted px-3 py-2`, активный `focus-visible:ring-2 focus-visible:ring-brand`; выбранный помечаем рамкой `border-line-brand`/фоном `bg-brand-soft` (консистентно с recents-строками в `WorkspacePicker`).
- Кнопка submit: `btn-primary w-full`.
- Ошибка: `text-xs text-danger-ink` (как `browseError` в пикере).
- Ссылки на получение ключа: `text-brand-ink hover:underline`, `target="_blank" rel="noopener noreferrer"`.
- Фирменная метка: `catalog-mark` (существующий класс).
- Отступы/типографика — в масштабе текущего UI (мелкие `text-xs`/`text-[11px]`, `px-2/px-3`, радиусы `rounded`/`rounded-control`).

Копирайт (коротко, без README):

- Заголовок: «Настройка Catalog».
- Пояснение: «Catalog обращается к LLM-провайдеру. Вставьте API-ключ — он сохранится локально и не показывается обратно.»
- Хелп: «Где взять ключ: OpenRouter — [openrouter.ai/keys](https://openrouter.ai/keys), z.ai — [z.ai](https://z.ai).» (ссылка соответствует выбранному провайдеру; можно показать обе).

## Доступность (a11y)

- Обёртка формы — `<form>` с `aria-labelledby` на заголовок (`useId`).
- Заголовок `h1` (единственный на экране, т.к. основной layout не отрисован).
- Выбор провайдера — `role="radiogroup"` с `aria-label="Провайдер"`; каждая опция — нативный `<input type="radio">` со связанным `<label>` (клик по подписи выбирает).
- Поле ключа — связанный `<label htmlFor>` (визуально может быть `sr-only`, но метка обязана существовать), `type="password"`, автофокус.
- Блок ошибки — `role="alert"` / `aria-live="assertive"`, чтобы озвучивался при появлении.
- Лоадер верхнего уровня — `role="status" aria-live="polite"`.
- Клавиатура: submit по Enter; весь фокус-порядок — провайдер → ключ → (глазок) → submit → ссылки; видимый фокус через `focus-visible:ring-brand`.
- Контраст — токенами темы (`text-ink` на `surface`, `text-danger-ink` для ошибки) — соответствует остальному UI.

## Контракты данных

- `GET /setup` → `SetupOut { keys_configured, provider, openrouter_configured, zai_configured }` (см. `backend/catalog/api/schemas.py`, endpoint `backend/catalog/api/models.py`).
- `PUT /setup/keys` body `SetupKeysUpdate { openrouter_api_key?, zai_api_key? }` → `SetupOut`; ≥1 поле обязательно (422); секрет не возвращается.
- Ошибки — через существующий `ApiError` + `extractApiDetail` (`frontend/src/api.ts`).
- `useSettings(enabled)` грузит `listProviders` / модели только при `enabled === true` (после конфигурации ключей) — предотвращает 502 (CATALOG-68).
- Ссылки на план: пункты «План действий» 1–5 и «Затрагиваемые файлы» в `10-CATALOG-83-ui-first-run-api-key.md`.

## Критерии визуальной приёмки

- [ ] При `status === 'unknown'` виден только нейтральный полноэкранный лоадер (`role="status"`), без хедера/сайдбара/пикера.
- [ ] При `keys_configured === false` рендерится только `SetupKeyScreen`; основной shell (хедер, сайдбар, main) отсутствует в DOM.
- [ ] Экран — полноэкранная центрированная карточка (`modal-card max-w-md`), не overlay-модалка; фон `bg-surface`.
- [ ] Есть выбор провайдера (OpenRouter / z.ai), по умолчанию OpenRouter, и одно password-поле для ключа с автофокусом.
- [ ] Поле base URL отсутствует (вне контракта).
- [ ] Пустой/пробельный ключ блокирует submit; POST не отправляется.
- [ ] При submit кнопка показывает «Сохранение…» и заблокирована; повторный сабмит невозможен.
- [ ] Ошибка (401/422/сеть) отображается на форме (`role="alert"`, `text-danger-ink`), экран не сбрасывается, введённые данные сохранены.
- [ ] Успешное сохранение переключает App на основной shell; далее доступен empty state воркспейса (CATALOG-80) с кнопкой «Открыть папку».
- [ ] Ключ нигде не отображается после сохранения и не подставляется в поле из ответа сервера.
- [ ] При уже настроенных ключах (`keys_configured === true`) экран не показывается — сразу основной layout.
- [ ] Провайдеры/модели не запрашиваются, пока ключ не настроен (нет фонового 502 на первом экране).
- [ ] Экран доступен с клавиатуры (Tab-порядок, Enter-submit, видимый фокус), метки связаны с полями, есть `radiogroup` для провайдера.
- [ ] Стиль консистентен с существующим UI: классы `modal-card`, `field`, `btn-primary`, токены `text-ink*`, `border-line*`, `text-danger-ink`, `catalog-mark`.
