# CATALOG-58 — Дизайн UI

- **Источник:** docs/plan/next-shift/CATALOG-58-ui-build-error-timeout.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Пользователь в чате нажимает «Создать скилл из сессии» (или «Сохранить изменения»). После неудачи он **сразу** видит понятный текст ошибки рядом с кнопкой, кнопка снова активна (не «Собираю скилл…»).

Если ошибка — таймаут LLM сессии (HTTP 504 / `detail` про timeout), рядом с текстом доступно действие «Увеличить таймаут…», открывающее модалку. Пользователь задаёт новое значение (база 60, диапазон 30–300), подтверждает → значение сохраняется на текущую сессию → компактный индикатор timeout в UI чата обновляется. При желании можно открыть ту же модалку вручную с индикатора timeout.

Успешный build по-прежнему открывает `SkillSettingsModal` (без изменений этого потока).

## Дерево компонентов и файлы

| Файл | Назначение |
|------|------------|
| `frontend/src/components/Chat.tsx` | Зона ошибки build под кнопкой создания скилла; компактный индикатор `llm_timeout_seconds`; пропсы `buildError`, `sessionTimeoutSeconds`, колбэки открытия модалки / dismiss ошибки |
| `frontend/src/components/SessionTimeoutModal.tsx` | **Новый.** Модалка изменения per-session LLM timeout (паттерн overlay как у `SkillSettingsModal`) |
| `frontend/src/App.tsx` | Состояние `buildError`, `timeoutModalOpen`, актуальный `llm_timeout_seconds` активной сессии; в `handleCreateSkill` — сброс loading, запись ошибки, детект timeout → опционально авто-открытие модалки; обработчик PATCH timeout |
| `frontend/src/api.ts` | Поле `llm_timeout_seconds` в `SessionOut`; `getSession` / `updateSessionTimeout` (PATCH); улучшение парсинга `detail` (строка или структура) для `buildSkill` и ошибок |
| `frontend/src/hooks/useSessions.ts` | При необходимости: отражать `llm_timeout_seconds` в списке после PATCH / refresh (без отдельного глобального UI timeout в сайдбаре) |

Не трогать: planner WS `error` в чате (остаётся только для WS); успешный путь `SkillSettingsModal`.

## Layout и состояния

### Зона create-skill (низ `Chat`, под кнопкой)

```
[ кнопка Создать скилл / Собираю скилл… ]
[ компактная строка: Timeout: Ns  ·  изменить ]
[ при ошибке: красный banner с текстом + опционально CTA timeout ]
```

- **idle:** кнопка активна (если есть сообщения); timeout-строка видна при наличии `sessionId` (значение с сессии, default UI-фолбэк 60 если ещё не загружено).
- **loading (`buildingSkill`):** кнопка disabled, текст «Собираю скилл…»; предыдущий `buildError` очищается в начале запроса.
- **error:** `buildingSkill=false`; banner `role="alert"` с полным `detail`; кнопка снова кликабельна. Для timeout-ошибок — вторичная кнопка/ссылка «Увеличить таймаут…».
- **success:** ошибки нет; открывается существующая `SkillSettingsModal`.
- **empty messages:** кнопка disabled как сейчас; timeout-строку можно показать, если сессия есть.

### Header `notice`

Не полагаться на бледный header-notice как единственный канал для fail build. Ошибку build показывать в зоне кнопки. Header `notice` для build-fail **не обязателен** (допустимо не дублировать или кратко дублировать — но приёмка считается по banner у кнопки).

### `SessionTimeoutModal`

Паттерн как `SkillSettingsModal`:

- Overlay: `fixed inset-0 z-50 … bg-black/60`
- Карточка: `max-w-sm`, `bg-slate-900`, `border-slate-700`
- Заголовок: «Таймаут LLM сессии»
- Пояснение одной строкой: лимит ожидания ответа модели для этой сессии чата (секунды).
- Поле number: текущее значение; подсказка «от 30 до 300, по умолчанию 60».
- Ошибка валидации/API — `text-red-400` под полем.
- Футер: «Отмена» / «Сохранить» (на сохранении — «Сохранение…», disabled).

Состояния модалки: idle → saving → error (внутри) → success (закрытие + обновление индикатора).

## Взаимодействия

1. **Fail build (любой):** `finally` сбрасывает `buildingSkill`; UI показывает `buildError` у кнопки.
2. **Fail = timeout** (статус 504 **или** `detail` содержит признаки timeout / «timed out» / «Increase the session LLM timeout»): banner + CTA «Увеличить таймаут…». Допустимо сразу открыть модалку при timeout (предпочтительно: открыть модалку **и** оставить banner, чтобы текст причины оставался видимым после закрытия).
3. **Fail ≠ timeout** (422 артефакты / retries / прочее): только banner с `detail`; CTA timeout не обязателен (можно оставить ручной вход через индикатор «Timeout: Ns»).
4. **Клик по «Timeout: Ns» / «изменить»:** открыть модалку с текущим значением.
5. **Сохранить в модалке:** PATCH `/sessions/{id}` с `{ llm_timeout_seconds }`; при успехе закрыть, обновить локальный timeout и список сессий; при ошибке — текст в модалке, модалка остаётся открытой.
6. **Отмена / ✕ / Escape:** закрыть без сохранения; focus trap не обязателен сверх паттерна `SkillSettingsModal`, но Escape — желателен.
7. **Смена сессии / новый чат:** сбросить `buildError`; подтянуть timeout новой сессии (или 60 для новой).
8. **Повторный Create skill после увеличения timeout:** обычный повторный клик по кнопке (отдельной «Повторить» не требуется).

Крайние случаи:

- Нет `sessionId` — кнопки create нет смысла / timeout UI скрыт.
- Значение вне 30–300 — блокировать Save на клиенте + показать подсказку (бэкенд тоже валидирует).
- Во время `buildingSkill` модалку можно открыть, но Save не должен отменять текущий build; новый build — только после завершения текущего.

## Стиль и токены

Согласованность с текущим dark UI (`bg-slate-950` / `slate-800` / indigo accents):

- Banner ошибки: `rounded-md border border-red-500/40 bg-red-950/40 px-3 py-2 text-xs text-red-300` (или эквивалент `text-red-400` как у planner error в `Chat`).
- CTA timeout в banner: `text-indigo-300 underline` или компактная `border border-slate-700` кнопка `text-xs` — в духе «Переподключить».
- Индикатор timeout: `text-[11px] text-slate-500`; кликабельная часть `hover:text-slate-300`.
- Кнопка create skill — без смены визуала, только гарантированный выход из disabled после fail.
- Модалка — те же утилиты полей, что `SkillSettingsModal` (`rounded bg-slate-800 px-2 py-1 text-xs`).

Новых зависимостей и UI-библиотек нет.

## Доступность (a11y)

- Banner ошибки: `role="alert"` и/или `aria-live="assertive"`, чтобы скринридер озвучил fail без DevTools.
- Кнопка create: при loading — `aria-busy="true"`; disabled пока `buildingSkill`.
- Модалка: `role="dialog"`, `aria-modal="true"`, `aria-labelledby` на заголовок; фокус на поле timeout при открытии; возврат фокуса на триггер при закрытии (как минимум на кнопку create или ссылку timeout).
- Поле timeout: `label` «Таймаут, секунды»; `min={30}` `max={300}` `step={1}`.
- Индикатор timeout: кнопка/link с понятным `aria-label` («Изменить таймаут LLM сессии, сейчас N секунд»).
- Контраст красного текста на тёмном фоне — как у существующих `text-red-400` ошибок в чате.

## Контракты данных (если нужны)

Предусловие code-шага: `docs/plan/next-shift/CATALOG-58-code-session-timeout-errors.md`.

| Контракт | Использование UI |
|----------|------------------|
| `SessionOut.llm_timeout_seconds` (default 60) | Индикатор в чате; начальное значение модалки |
| `PATCH /sessions/{id}` body `{ "llm_timeout_seconds": int }` (ge 30, le 300) → `SessionOut` | Сохранение из модалки |
| `GET /sessions/{id}` (опционально) | Подтянуть timeout активной сессии, если список не содержит поле |
| `POST /sessions/{id}/skills` ошибки: `detail` string; timeout → **504** с текстом про increase timeout; retries/validation → **422** | Парсинг в `api.ts` / `extractApiDetail`; детект timeout для CTA/модалки |
| Уже есть `extractApiDetail` в `App.tsx` | Переиспользовать/усилить (в т.ч. если `detail` — не только строка в хвосте сообщения) |

Детект timeout для UI (достаточно одного совпадения):

- HTTP status === 504, или
- `detail` / message содержит `timed out` / `timeout` (case-insensitive) в контексте skill build.

## Критерии визуальной приёмки

- [ ] После fail build кнопка не остаётся в состоянии «Собираю скилл…» и снова доступна для клика.
- [ ] Текст ошибки build виден в зоне кнопки (красный banner), без необходимости смотреть header notice или DevTools.
- [ ] Текст ошибки содержит backend `detail` (таймаут / retries / артефакты — как пришло с API).
- [ ] При timeout-ошибке доступна модалка увеличения timeout (авто и/или через CTA «Увеличить таймаут…»).
- [ ] Модалка показывает текущее значение; база/фолбэк 60; ввод ограничен 30–300.
- [ ] После Save новое значение сохраняется для текущей сессии и отображается в компактном индикаторе «Timeout: Ns».
- [ ] Индикатор timeout в UI чата кликабелен и открывает ту же модалку вне сценария ошибки.
- [ ] Модалка визуально и по паттерну совпадает с `SkillSettingsModal` (overlay, slate/indigo, компактная типографика).
- [ ] Planner WS error и build error не смешиваются: WS — как сейчас в ленте; build — у кнопки.
- [ ] Успешный build по-прежнему открывает настройку скилла без регрессий layout.
