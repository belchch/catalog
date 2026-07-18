# CATALOG-2 — Дизайн UI

- **Источник:** docs/plan/night-shift/CATALOG-2-ui-session-history.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Пользователь должен видеть список прошлых чатов, открывать любой из них с восстановлением ленты и удалять ненужные. После F5 диалог не теряется.

Сценарий:
1. Пользователь ведёт диалог с планировщиком в текущей сессии.
2. В левой панели видит блок «Сессии» — список прошлых чатов с превью (заголовок, дата, статус). Текущая сессия подсвечена.
3. Клик по элементу списка → лента этой сессии восстанавливается в области `Chat`; можно продолжить диалог (WS переподключается на выбранный `sessionId`).
4. Кнопка «+ Новый чат» сбрасывает текущую сессию в пустой чат (сама сессия создаётся лениво при первом сообщении, как сейчас).
5. Кнопка удаления у элемента → двухшаговое подтверждение → сессия исчезает из списка и удаляется на сервере. Если удалили текущую — переходим в пустой чат.
6. После обновления страницы: последний открытый `sessionId` восстанавливается из `localStorage`, лента гидрируется, список сессий доступен.

## Дерево компонентов и файлы

- `frontend/src/api.ts` (**изменить**) — добавить типы и вызовы:
  - `interface SessionOut { id: string; status: string; created_at: string; updated_at: string; title: string | null; skill_id: string | null }`
  - `interface MessageOut { id: number; session_id: string; role: string; content: string | null; tool_name: string | null; tool_call_id: string | null; created_at: string }`
  - `listSessions(params?: { limit?: number; offset?: number; status?: string }): Promise<SessionOut[]>` → `GET /sessions`
  - `listSessionMessages(sessionId: string): Promise<MessageOut[]>` → `GET /sessions/{id}/messages`
  - `deleteSession(sessionId: string): Promise<void>` → `DELETE /sessions/{id}` (204, тело не парсить — использовать `fetch` напрямую, т.к. `jsonFetch` ждёт JSON)
- `frontend/src/hooks/useSessions.ts` (**новый**) — по образцу `useDocuments.ts`:
  - `interface UseSessionsResult { sessions: SessionOut[]; loading: boolean; error: string | null; refresh: () => Promise<void>; remove: (id: string) => Promise<void> }`
  - `refresh` тянет `listSessions()`, сортировка сервера (updated_at/created_at DESC) сохраняется; авто-`refresh` на маунте через `useEffect`.
  - `remove(id)` вызывает `deleteSession(id)`, затем оптимистично убирает элемент из `sessions`.
- `frontend/src/components/SessionsPanel.tsx` (**новый**) — панель списка сессий: заголовок с кнопками «+ Новый чат» и «Обновить», список элементов сессий, состояние загрузки/пусто/ошибка. Пропсы: `sessions: UseSessionsResult`, `currentSessionId: string | null`, `onSelect: (id: string) => void`, `onNewChat: () => void`, `onDelete: (id: string) => void`.
- `frontend/src/hooks/usePlannerSession.ts` (**изменить**) — гидрация ленты из API при смене `sessionId` (см. «Контракты данных» и «Взаимодействия»).
- `frontend/src/App.tsx` (**изменить**) — подключить `useSessions`, вставить `SessionsPanel` в левый `aside`, реализовать `onSelect` / `onNewChat` / `onDelete`, persist/restore `sessionId` в `localStorage`, дергать `sessions.refresh()` при создании сессии и по завершении хода планировщика.

Новых зависимостей не вводить — только текущий стек (React 19 + Vite + TS + Tailwind v3) и уже существующие паттерны.

## Layout и состояния

Общий layout не меняется: `header` → `notice` → `grid [320px_1fr]`. `SessionsPanel` размещается **первым** блоком в левом `aside` (над «Документы» и «Скиллы`), т.к. это точка входа в диалог. Разделение блоков — существующим `flex flex-col gap-4` контейнера `aside`.

Структура `SessionsPanel`:
- Шапка: заголовок «Сессии» (`text-sm font-semibold text-slate-200`) + справа кнопки «+ Новый чат» и «Обновить» в стиле кнопок `DocumentList` (`rounded bg-slate-800 px-2 py-1 text-xs`).
- Тело: `<ul class="flex flex-col gap-1">` c элементами-сессиями.

Состояния:
- **loading** (первичная загрузка, `sessions.length === 0 && loading`): строка-заглушка `text-xs text-slate-500` — «Загрузка…»; на кнопке «Обновить» — «…», `disabled`.
- **empty** (`!loading && sessions.length === 0 && !error`): `text-xs text-slate-500` — «Пока нет сохранённых сессий».
- **error** (`error`): `text-xs text-red-400` с текстом ошибки; список при этом может оставаться из прошлого успешного запроса.
- **success**: список элементов. Каждый элемент:
  - Заголовок: `title` или фолбэк «Без названия» (`truncate`, `title`-атрибут для полного текста).
  - Мета-строка: дата (`updated_at`, форматирование `new Date(updated_at).toLocaleString()`), при желании — компактно; + бейдж статуса (`text-[10px] uppercase`, стиль как `kind`-бейдж в `DocumentList`).
  - Кнопка удаления (иконка-крестик/«×» или «Удалить»), появляется/акцентируется при hover и всегда доступна с клавиатуры.
- **active**: текущая сессия (`id === currentSessionId`) подсвечена как выбранный документ в `DocumentList` — `bg-indigo-600 text-white`; невыбранные — `bg-slate-800/60 text-slate-300 hover:bg-slate-800`.

Гидрация ленты (в области `Chat`): пока сообщения выбранной сессии грузятся, допускается кратковременное пустое состояние `Chat` (существующий плейсхолдер) — отдельный лоадер поверх ленты не обязателен для этого среза. Ошибку гидрации показываем через существующий механизм (`error` в `Chat` или `notice`).

## Взаимодействия

- **Выбор сессии**: клик по элементу → `onSelect(id)` → в `App` `setSessionId(id)` (+ сброс `editingSkill`, `activeRunId=null`, запись id в `localStorage`). Смена `sessionId` запускает в `usePlannerSession` гидрацию: загрузка `listSessionMessages(id)`, маппинг в `PlannerMessage[]`, установка в `messages`; параллельно/после — переподключение WS на этот `sessionId` для продолжения диалога. Повторный клик по уже активной сессии — no-op.
- **Новый чат**: `onNewChat` → `setSessionId(null)` (+ сброс `editingSkill`, `activeRunId`, очистка id в `localStorage`). Пустой `Chat` со стартовыми подсказками; реальная сессия создаётся лениво в `ensureSession` при первом `send` (текущее поведение сохраняется).
- **Удаление**: двухшаговое подтверждение без нативного `window.confirm`. Первый клик по кнопке удаления переводит элемент в состояние подтверждения (кнопка меняется на «Удалить?» / появляются «Удалить» + «Отмена`); повторный клик по подтверждению → `onDelete(id)`; «Отмена» или потеря фокуса/клик по другому элементу — возврат в обычное состояние. Состояние подтверждения — локальный `useState` в `SessionsPanel` (`confirmId: string | null`).
  - `onDelete` в `App`: `await sessions.remove(id)`; если `id === sessionId` — перейти в пустой чат (`setSessionId(null)`, очистить `localStorage`). Ошибку удаления показать в `notice`/`error` панели.
- **Обновление списка**: список пере-запрашивается после: (1) создания сессии в `ensureSession`; (2) завершения хода планировщика — когда `planner.streaming` переходит `true → false` (появляется/обновляется `title`/`updated_at`); (3) ручного клика «Обновить»; (4) после удаления (оптимистично + не обязателен повторный `refresh`).
- **Restore после F5**: на маунте `App` читает `localStorage['catalog.sessionId']`; если есть — инициализирует `sessionId` этим значением (гидрация подхватит ленту). Если сессия уже удалена на сервере (`listSessionMessages` → 404 или `GET /sessions/{id}` отсутствует в списке) — молча сбросить в пустой чат и очистить ключ.

Крайние случаи:
- WS-`error` «session not found» при устаревшем `sessionId` из `localStorage` → сброс в пустой чат, очистка ключа.
- Гидрация сессии с историей, где последний ход был оборван, — просто показываем сохранённые сообщения; никаких авто-отправок.
- Длинные заголовки — `truncate` + `title`-атрибут.

## Стиль и токены

Полная консистентность с существующим тёмным UI (Tailwind v3, палитра slate/indigo):
- Контейнер панели — `flex flex-col gap-2` (как `DocumentList`).
- Заголовок блока — `text-sm font-semibold text-slate-200`.
- Кнопки шапки («+ Новый чат», «Обновить») — `rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 disabled:opacity-50 hover:bg-slate-700`.
- Элемент списка — кнопка `w-full text-left rounded px-2 py-1.5 text-xs`, выбранная `bg-indigo-600 text-white`, обычная `bg-slate-800/60 text-slate-300 hover:bg-slate-800`.
- Мета-строка внутри элемента — `text-[10px] text-slate-400` (в выбранном — `text-indigo-100/80`), бейдж статуса — `rounded bg-slate-700/60 px-1 text-[10px] uppercase` (как `kind` в `DocumentList`).
- Кнопка удаления — компактная, `text-slate-400 hover:text-red-400`; в состоянии подтверждения «Удалить» — `text-red-400`, «Отмена» — `text-slate-400`.
- Ошибки — `text-xs text-red-400`; заглушки/пусто — `text-xs text-slate-500`.
- Никаких карточек-дэшборда и новых цветовых токенов — одна плоская панель списка (согласно плану).

## Доступность (a11y)

- Список — семантический `<ul>/<li>`; элемент сессии — `<button>` (фокусируемый, активируется Enter/Space).
- Активный элемент — `aria-current="true"` (или `aria-selected`), не только цветом.
- Кнопка удаления — отдельный `<button>` с `aria-label="Удалить сессию"`; не вложена в кнопку выбора (избежать вложенных интерактивов) — оба лежат рядом в контейнере элемента (`relative`/`flex`), клик по удалению не триггерит выбор (`stopPropagation`).
- Состояние подтверждения удаления доступно с клавиатуры; после отмены фокус остаётся на элементе.
- Кнопки «+ Новый чат» / «Обновить» — с понятным текстом; `disabled` во время загрузки.
- Контраст: выбранный `indigo-600` на белом тексте и `slate-800/60` на `slate-300` — соответствуют остальному UI.

## Контракты данных

Backend уже реализован (парный code-план `CATALOG-2-code-session-history-api.md`):
- `GET /sessions?limit=&offset=&status=` → `SessionOut[]`: `{ id, status, created_at, updated_at, title|null, skill_id|null }`, отсортировано DESC по свежести.
- `GET /sessions/{id}/messages` → `MessageOut[]`: `{ id, session_id, role, content|null, tool_name|null, tool_call_id|null, created_at }`; 404 если сессии нет.
- `DELETE /sessions/{id}` → `204 No Content`; 404 если сессии нет.

Маппинг `MessageOut[]` → `PlannerMessage[]` при гидрации (типы из `usePlannerSession.ts`):
- `role === 'user'` → `{ role: 'user', content }`.
- `role === 'assistant'` → `{ role: 'assistant', content }`.
- `role === 'tool'` → `content` это JSON-строка `{"ok": boolean, "result": ...}`. Отобразить как live-`tool_result`: `{ role: 'tool', toolName: tool_name ?? undefined, content: '← ' + (tool_name ?? 'tool') + ': ' + (ok ? 'ok' : 'fail') }`. При ошибке парсинга — показать сырой `content`. Персистентных `tool_call` (стрелка `→ name(args)`) в истории нет — это ожидаемо, показываем только результаты.
- Сообщения с `content === null` (кроме tool) — пропускать.

`localStorage`: ключ `catalog.sessionId` (строка id или отсутствует). Пишется при выборе/создании сессии, очищается при «Новый чат» и удалении текущей.

## Критерии визуальной приёмки

- [ ] В левой панели над «Документы» есть блок «Сессии» со списком прошлых сессий: заголовок (или «Без названия»), дата, бейдж статуса.
- [ ] Текущая (открытая) сессия визуально подсвечена (`indigo-600`) и помечена `aria-current`.
- [ ] Клик по сессии восстанавливает её ленту в области чата (user/assistant/tool сообщения в правильном стиле), после чего диалог можно продолжить.
- [ ] Кнопка «+ Новый чат» открывает пустой чат со стартовыми подсказками; новая сессия появляется в списке после первого сообщения / завершения хода.
- [ ] У каждого элемента есть удаление с двухшаговым подтверждением (без нативного диалога); подтверждение убирает сессию из списка; удаление текущей переводит в пустой чат.
- [ ] После F5 последний открытый чат восстанавливается (лента на месте), список сессий доступен; устаревший id из `localStorage` не ломает UI (тихий сброс в пустой чат).
- [ ] Показаны состояния loading / empty («Пока нет сохранённых сессий») / error (`red-400`).
- [ ] Стиль панели консистентен с `DocumentList`/`SkillsPanel` (Tailwind, slate/indigo), без карточного dashboard-шума.
- [ ] Список сессий и кнопки корректно доступны с клавиатуры; кнопка удаления имеет `aria-label` и не триггерит выбор сессии.
