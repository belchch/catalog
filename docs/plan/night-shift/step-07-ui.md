# Step 07 — UI (React: чат-планировщик, доки, создать/коммит/применить, результат + стриминг)

- **Статус:** pending
- **Цель:** фронтенд среза на существующем стеке (Vite + React 19 + TS + Tailwind v3). Рабочий путь MVP в одном SPA: загрузка/выбор документа → чат-планировщик (стриминг) → «Создать скилл» → «Коммит» → выбрать скилл → «Применить» к документу → результат со стримингом шагов и trace.

## Зависимости
- Шаг 06 (API + WS-протокол). Без новых npm-зависимостей по умолчанию (fetch + нативный `WebSocket`). Решение по роутингу/state ниже.
- Существующий стек: React 19, Vite 8, TS 6, Tailwind v3, `oxlint`. Скрипты: `pnpm run dev`, `build` (`tsc -b && vite build`), `lint` (`oxlint`). **Нет `typecheck`-скрипта** — добавить `"typecheck": "tsc -b --noEmit"` в `package.json`.

## Архитектурные решения
- **Без фреймворка роутинга / state-библиотеки в срезе:** одна страница (`App.tsx`) с простым стейт-машинным переключением панелей (документы | чат | скиллы | результат). Состояние — `useState`/`useReducer` + хуки. Обоснование: MVP, мало экранов; добавить при росте.
- **API-клиент:** тонкий модуль `src/api.ts` (`fetch` обёртки) + `src/ws.ts` (хук `usePlannerSession`/`useRunStream` поверх `WebSocket`).
- **Markdown-рендер:** опционально `react-markdown` (добавить, если нужен предпросмотр результата). Решение: добавить `react-markdown` + `remark-gfm` для таблиц — результат скилла это markdown. Зафиксировать в ADR-0011 (frontend stack) дополнением.

## Структура `frontend/src/`
```
api.ts                 # fetch-обёртки: documents/skills/runs; типы DocumentOut/SkillOut/RunOut
ws.ts                  # connectPlanner(sessionId, handlers), connectRun(runId, handlers); типы событий
hooks/
  usePlannerSession.ts # WS /sessions/{id}: отправка user, приём token/tool_call/finish
  useRunStream.ts      # WS /runs/{id}/stream: приём tool_call/tool_result/verify/finish
  useDocuments.ts      # GET/POST /documents
  useSkills.ts         # GET /skills, commit, apply
components/
  DocumentList.tsx     # список + upload (.md/.docx); выбор currentDoc
  Chat.tsx             # история сообщений + ввод; стрим токенов
  ChatMessage.tsx      # user/assistant/tool рендер
  SkillsPanel.tsx      # список скиллов + «Коммит» + «Применить» (выбор док-та)
  RunView.tsx          # результат + стрим шагов (tool_call/tool_result/verify) + trace
  TraceSteps.tsx       # лента шагов прогона
App.tsx                # лейаут: лево — документы/скиллы, право — чат или результат
index.css              # Tailwind layers (уже есть)
```

## Поведение / пользовательский путь
1. **Загрузить документ** → `POST /documents` → попадает в `DocumentList`; выбор ставит `currentDocId`.
2. **Планировщик:** `POST /sessions` → `sessionId`; WS `/sessions/{id}`. Пользователь пишет → сервер стримит токены (растёт assistant-сообщение) + tool-вызовы (видимы в чате как системные строки «ℹ read_document(doc_id)»). Финиш → сообщение зафиксировано.
3. **Создать скилл:** кнопка в чате → `POST /sessions/{id}/skills` → `skillId` (draft); предпросмотр конфига (name, system_prompt, allowed_tools, verify_checks).
4. **Коммит:** `POST /skills/{id}/commit` → скилл в `SkillsPanel` со статусом committed.
5. **Применить:** выбрать committed-скилл + целевой документ → `POST /skills/{id}/apply {doc_id}` → `runId`; WS `/runs/{id}/stream` → `RunView` показывает ленту шагов (tool_call → tool_result → verify(passed/failures) → ...), в конце — результат (markdown-предпросмотр) и статус ok/failed. При failed — ошибки verify видны, результат (last_text) доступен.
6. **Повтор:** тот же скилл к другому документу — новый run.

## WS-клиент (`ws.ts`)
```ts
type ServerEvent =
  | { type: "step"; iteration: number }
  | { type: "token"; delta: string }
  | { type: "tool_call"; id: string; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; id: string; name: string; ok: boolean; result: unknown }
  | { type: "verify"; iteration: number; passed: boolean; failures: string[] }
  | { type: "finish"; capped: boolean; status?: string };

function connectPlanner(sessionId: string, on: (e: ServerEvent) => void): { send(text: string): void; close(): void }
function connectRun(runId: string, on: (e: ServerEvent) => void): { close(): void }
```
- Тайм-аут/реестablish — вне скоупа среза; на `onclose` без `finish` показывать «соединение закрыто».

## Тесты / проверки
- Ручной прогон полного пути против живого бэкенда (шаг 06): загрузить md/docx → чат → создать скилл → коммит → применить → результат со стримом.
- Автотесты фронта в срезе опциональны (oxlint/typesсheck обязательны). Если добавляем — `@testing-library/react` на `ws.ts`/парсер событий и `RunView`. Решение заказчика.
```bash
cd frontend
pnpm install            # react-markdown remark-gfm (если принято)
pnpm run typecheck      # добавить скрипт
pnpm run lint
pnpm run build          # без ошибок; dev-сервер :5173 проксирует API? нет — CORS на бэке уже ok
```

## Критерий приёмки
- [ ] Полный путь из пункта «Поведение» проходит в браузере против бэкенда (06): загрузка → планирование со стримом → создать draft → коммит → применить → результат + trace со стримом шагов.
- [ ] Токены планировщика стримятся в реальном времени; tool-вызовы/результаты и verify-шаги видны.
- [ ] При провале verify в UI видны ошибки и последний результат.
- [ ] `pnpm run typecheck` и `pnpm run lint` зелёные; `pnpm run build` без ошибок.
- **Нет:** FTS/поиска, git/версий/diff, pdf/xlsx, мультипользователь, полноценного редактора скиллов (только предпросмотр).

## Заметки
- API base URL: `http://localhost:8000` (бэк); WS — `ws://localhost:8000/...`. Вынести в `VITE_API_URL` (env) с дефолтом.
- Стриминг токенов требует, чтобы planner WS (шаг 06) реально слал `token`-кадры; если шаг 06 выбрал collect-режим — токены придут одним кадром (допустимо, но менее «живо»). UI не ломается в обоих случаях.
- Дизайн-минимум: Tailwind-утилиты, без дизайн-системы; читаемость важнее «красоты» — это срез.
