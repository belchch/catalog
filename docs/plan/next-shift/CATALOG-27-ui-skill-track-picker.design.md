# CATALOG-27 — Дизайн UI

- **Источник:** docs/plan/next-shift/CATALOG-27-ui-skill-track-picker.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Перед настройкой скилла (`SkillSettingsModal`) вставляется шаг **дизамбигуации операции**. Пользователь нажимает «Создать скилл из сессии» → система за кулисами вызывает фазу A (`proposeSkillTracks`). Дальше три исхода:

1. **Неоднозначно (>1 трек).** Пользователь видит модалку выбора: список вариантов операции, у каждого — название и обоснование. Выбирает один → нажимает «Собрать скилл» → идёт обычный build → открывается `SkillSettingsModal`.
2. **Однозначно (ровно 1 трек).** Модалка не показывается: система тихо фиксирует трек и сразу строит скилл → `SkillSettingsModal`.
3. **Скип/фолбэк (edit-сессия, пустой список, `fallback: true`, ошибка сети).** Фаза A не влияет: сразу обычный build → `SkillSettingsModal`, ровно как сегодня.

Ключевой сценарий пользователя видим только в исходе (1): короткий момент «подбираю варианты…», затем компактная модалка с выбором, затем привычная сборка.

## Дерево компонентов и файлы

- `frontend/src/components/SkillTrackPicker.tsx` — **новый**. Модальный диалог выбора трека операции. Показывает список `SkillTrack` (name + rationale + operation + бейдж арности), одиночный выбор, CTA «Собрать скилл» и «Отмена». Владеет локальным состоянием: `selectedIndex` и `submitting` (пока идёт select + build).
- `frontend/src/App.tsx` — **изменяется**. Оркестрация фазы A в `handleCreateSkill`; новые состояния `proposingTracks` и `trackChoice`; рендер `SkillTrackPicker` рядом с `SkillSettingsModal`; гейт по `editingSkill` (не запускать фазу A на edit-flow).
- `frontend/src/api.ts` — **изменяется**. Типы `SkillTrack`, `SkillTracksOut`, `SkillTrackSelected`; функции `proposeSkillTracks(sessionId)` и `selectSkillTrack(sessionId, track)`.
- `frontend/src/components/Chat.tsx` — **лёгкая правка**. Новый проп `proposingTracks: boolean`; кнопка сборки во время фазы A показывает «Подбираю варианты…» и блокируется (в дополнение к текущему `buildingSkill`). Planner-flow не меняется.
- `frontend/src/components/SkillSettingsModal.tsx` — **не трогать**. Остаётся шагом configure после успешного build.

## Layout и состояния

**`SkillTrackPicker` — структура (по образцу `SessionTimeoutModal`/`SkillSettingsModal`):**

- Оверлей: `fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4`.
- Панель: `w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-xl`, `role="dialog"`, `aria-modal="true"`, `aria-labelledby`.
- Шапка: заголовок «Выбор операции» (`text-sm font-semibold text-slate-100`) + крестик закрытия справа (как в других модалках).
- Подзаголовок-пояснение: `text-xs text-slate-400`, напр. «Уточните, что делаем с документами — от этого зависит скилл.»
- Список треков: вертикальный `role="radiogroup"`, каждый трек — кнопка `role="radio"` во всю ширину:
  - Название трека — `text-xs font-medium text-slate-100`.
  - Операция (`operation`) — `text-[11px] text-slate-300`.
  - Обоснование (`rationale`) — `text-[11px] text-slate-400`.
  - Бейдж арности справа/в углу: «1 документ» / «2 документа» / «Список» (по `input_arity` 1 / 2 / null), стиль как chip `rounded bg-slate-700/60 px-1 text-[10px] uppercase text-slate-400`.
  - Выбранный элемент: рамка/фон акцента `border-indigo-500 bg-indigo-600/15`; невыбранные — `border-slate-700 bg-slate-800/60 hover:border-indigo-500 hover:bg-slate-800`.
- Футер: справа «Отмена» (`bg-slate-700`) и «Собрать скилл» (`bg-indigo-600`, primary).

**Состояния экрана:**

- **loading фазы A** (`proposingTracks`): модалки нет; в `Chat` кнопка сборки показывает «Подбираю варианты…» и `aria-busy`. Остальной ввод чата блокируется как при `buildingSkill`.
- **empty / автоскип**: `tracks.length <= 1` или `skipped`/`fallback` — модалка не монтируется вовсе, сразу переход к build (кнопка «Собираю скилл…»).
- **выбор (success фазы A, >1 трек)**: модалка открыта, первый трек предвыбран.
- **submitting (внутри модалки)**: после «Собрать скилл» кнопки диалога блокируются, primary-кнопка показывает «Собираю скилл…», крестик и «Отмена» задизейблены — до ответа build.
- **error фазы A**: не отдельный экран. Сетевая ошибка/5xx `proposeSkillTracks` трактуется как фолбэк → сразу build (не блокируем). Ошибка build после выбора трека → модалка закрывается, ошибка показывается существующим `buildError`-блоком в `Chat` (как сегодня).

## Взаимодействия

- **Открытие**: только из `handleCreateSkill` при `editingSkill == null` и `tracks.length > 1`.
- **Выбор трека**: клик по строке выбирает её; стрелки ↑/↓ (и ←/→) перемещают выбор по образцу `radiogroup` в `SkillSettingsModal` (`tabIndex` активного = 0, остальных = -1).
- **Подтверждение**: кнопка «Собрать скилл» или Enter → `onSelect(track)` (async): parent делает `selectSkillTrack` (тихая запись user-сообщения) → `buildSkill` → открывает `SkillSettingsModal`. Во время ожидания — состояние submitting.
- **Отмена**: кнопка «Отмена», крестик или Escape → `onCancel()`; модалка закрывается, скилл **не** создаётся, сессия и чат без изменений. Во время submitting отмена недоступна.
- **Фокус**: при открытии фокус на выбранной (первой) строке; Escape закрывает (кроме submitting) — слушатель `keydown` как в `SessionTimeoutModal`.
- **Крайние случаи**:
  - `proposeSkillTracks` вернул `skipped: true` (edit по контракту) — фаза A всё равно не должна доходить сюда, т.к. UI гейтит по `editingSkill`; но если дошло — трактуем как автоскип → build.
  - `fallback: true` или `tracks: []` — автоскип → build.
  - Двойной клик по «Создать скилл»: `proposingTracks`/`buildingSkill` блокируют кнопку, повторного запуска фазы A нет.
  - Выбор трека не уходит в planner WS `send` — используется только `selectSkillTrack` (тихий append) + `buildSkill`.

## Стиль и токены

Полная консистентность с существующими модалками (`SessionTimeoutModal`, `SkillSettingsModal`):

- Палитра: фон панели `bg-slate-900`, оверлей `bg-black/60`, рамки `border-slate-700`, вторичный текст `text-slate-400`, акцент `indigo-600` (primary CTA / выбранный трек), нейтральная кнопка `bg-slate-700`.
- Типографика: заголовок `text-sm font-semibold`, тело/кнопки `text-xs`, подписи/бейджи `text-[11px]` / `text-[10px]`.
- Отступы: панель `p-4`, `mb-2`/`mb-3` между блоками, `gap-2` в футере, список треков `space-y-2`.
- Радиусы: панель `rounded-lg`, элементы `rounded`, бейджи/чипы `rounded`.
- Никаких карточных дашбордов и новых зависимостей — только Tailwind-утилиты, уже используемые в проекте.

## Доступность (a11y)

- Диалог: `role="dialog"`, `aria-modal="true"`, `aria-labelledby` на заголовок (через `useId`).
- Выбор: контейнер `role="radiogroup"` с `aria-label="Варианты операции"`; строки `role="radio"` + `aria-checked`; roving `tabIndex` (активный 0, прочие -1); навигация стрелками.
- Клавиатура: Enter — подтвердить, Escape — отмена (кроме submitting); Tab доходит до кнопок футера.
- Кнопка сборки в `Chat` во время фазы A — `aria-busy` и понятная подпись «Подбираю варианты…».
- Контраст: акцентный `indigo-600` на тёмном фоне и `text-slate-100/300/400` — как в остальном UI (достаточно для среза).

## Контракты данных

Backend уже реализован (code-план `CATALOG-27-code-skill-tracks-anti-domain.md`). UI использует:

- `POST /sessions/{id}/skill-tracks` → `SkillTracksOut { tracks: SkillTrack[]; skipped: boolean; fallback: boolean }`.
- `POST /sessions/{id}/skill-tracks/select` тело `{ track: SkillTrack }` → `SkillTrackSelected { session_id: string; content: string }` (тихая запись user-сообщения, без planner-turn).
- `POST /sessions/{id}/skills` → существующий `buildSkill` (`SkillBuilt`).

Тип `SkillTrack`: `{ name: string; description: string; operation: string; input_arity: number | null; rationale: string }`.

Матрица решений в `handleCreateSkill` (только create, `editingSkill == null`):

- edit-сессия (`editingSkill != null`) → фазу A **не вызывать**, сразу текущий `buildSkill`.
- `proposeSkillTracks`: `skipped || fallback || tracks.length === 0` → `buildSkill`; `tracks.length === 1` → `selectSkillTrack(tracks[0])` → `buildSkill` (без UI); `tracks.length > 1` → открыть picker.
- сетевая ошибка/5xx фазы A → фолбэк на `buildSkill` (не блокировать сборку).

## Критерии визуальной приёмки

- [ ] При >1 треке модалка выбора появляется **до** `SkillSettingsModal`; в каждом варианте видны название и обоснование (плюс операция и арность).
- [ ] Ровно 1 трек / `skipped` / `fallback` / пустой список — модалка не показывается, сразу открывается настройка скилла.
- [ ] Edit-сессия («Сохранить изменения») не показывает шаг выбора трека.
- [ ] Ошибка/фолбэк фазы A не блокирует сборку — открывается обычный build → settings.
- [ ] «Отмена»/Escape/крестик закрывают модалку без создания скилла; чат и сессия не меняются.
- [ ] Во время фазы A кнопка сборки в чате показывает «Подбираю варианты…» и заблокирована; при build — «Собираю скилл…».
- [ ] Стиль модалки (палитра, типографика, отступы, primary/secondary кнопки) визуально согласован с `SessionTimeoutModal`/`SkillSettingsModal`.
- [ ] Клавиатура: стрелки переключают трек, Enter подтверждает, Escape отменяет; выбранный трек имеет видимый акцент (`indigo`).
