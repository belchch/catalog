# CATALOG-119 — Дизайн UI

- **Источник:** `docs/plan/day-shift/05-CATALOG-119-ui-trace-tree.md`
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Вызов скилла как тула (ADR-0019) перестаёт быть строкой `← skill_x: ok` и становится **раскрываемым узлом вложенного запуска**: внутри видно вход, результат, проверки и шаги дочернего run.

Где это реально происходит (проверено по коду на `pipeline/day-shift`):

- `build_session_skill_tools` подключается только в `_ws_session_tools` (`backend/catalog/api/sessions.py:729`) → вложенные запуски рождаются **в чате планировщика**.
- `WS /runs/{id}/stream` собирает только `build_document_tools` (`backend/catalog/api/runs.py:234`) → у top-level apply-прогона детей сегодня быть не может.

Поэтому узел монтируется в двух местах одним компонентом: **в чате** (там он виден пользователю уже сейчас) и **в ленте шагов прогона** (`TraceSteps`, готово к моменту, когда apply получит skill-тулы). Логика дерева — общая, в `lib/traceSegments.ts`.

Сценарий (чат):

1. Планировщик вызывает скилл-тул. В ленте появляется привычная строка `ℹ → skill_extract_terms({...})` — пока идёт вызов, ничего не меняется.
2. Пришёл результат — эта же строка **превращается** в свёрнутый узел: `⤷ skill_extract_terms · ✓ · запуск 4f2a1b3c`. Второй строки `←` больше нет: один вызов — один узел.
3. Клик по узлу раскрывает его и подгружает дочерний запуск (`GET /runs/{id}`): **вход**, **результат**, **проверки** (причина провала при `passed=false`), **шаги** дочернего запуска в том же формате ленты.
4. Свернуть/раскрыть повторно — без повторной загрузки. Ошибка загрузки — сообщение + «Повторить».

Сценарий (прогон, `RunView`): если `tool_result` несёт id дочернего запуска, соседние `tool_call` + `tool_result` сворачиваются в такой же узел внутри группы шага. Плоская пара строк остаётся только для тулов без вложенного запуска (`read_document` и т. п.).

## Дерево компонентов и файлы

**Frontend**

- `frontend/src/lib/traceSegments.ts` — вся чистая логика дерева (тестируется в `TraceSteps.test.ts`):
  - `extractChildRunId(name: string, result: unknown): string | null` — id вложенного запуска из payload тула. Работает только при `name.startsWith('skill_')`. Порядок попыток: объект → `result.run_id`; строка → `JSON.parse` → `run_id`; строка не распарсилась (обрезана `_snip_result` до 400 символов) → регексп `/"run_id"\s*:\s*"([0-9a-f]{8,})"/`. Иначе `null`.
  - `type TraceItemNode = { kind: 'item'; item: RunStep } | { kind: 'run'; runId: string; toolName: string; input?: string; ok: boolean; result: RunStep }`.
  - `foldNestedRuns(items: RunStep[]): TraceItemNode[]` — `tool_result` с `childRunId` становится узлом `run`; непосредственно предшествующий `tool_call` того же тула поглощается и отдаёт `input`. Всё остальное — `item` в исходном порядке.
  - `runTraceToSteps(trace: unknown[] | null, runId: string): RunStep[]` — конвертация `TraceEntry[]` дочернего запуска в `RunStep[]` (таблица маппинга ниже).
  - `segmentTraceSteps` / `traceGroupStatus` **остаются как есть**: группировка по `step_id` ортогональна дереву (pipeline-шаги), а не заменяется им.
- `frontend/src/components/TraceSteps.tsx` — сюда же добавляется `TraceRunNode` и экспортируется из этого файла. Один файл сознательно: `TraceSteps` рендерит `TraceRunNode`, а `TraceRunNode` рендерит `TraceSteps` для шагов ребёнка — взаимная рекурсия в одном модуле безопаснее циклического импорта двух файлов.
  - `TraceSteps` получает новый необязательный проп `depth?: number` (по умолчанию `0`). Узлы вложенных запусков рендерятся только при `depth === 0`; глубже — плоская строка (ADR-0019: глубина 1).
  - `TraceRunNode` props: `runId: string`, `toolName: string`, `input?: string`, `ok?: boolean`, `depth?: number`, `className?: string`.
- `frontend/src/hooks/usePlannerSession.ts`:
  - `PlannerMessage` расширяется: `childRunId?: string`, `input?: string`, `ok?: boolean`.
  - `tool_call` для `skill_*` — как и раньше пушится строка `→ …`, но с `input` (см. «Взаимодействия»).
  - `tool_result` для `skill_*` с извлечённым `run_id` — **не пушит новое сообщение**, а заменяет последнее «висящее» сообщение того же тула (роль `tool`, без `childRunId`, контент начинается с `→`), проставляя `childRunId`/`ok`. Нет id или нет пары — поведение сегодня без изменений (отдельная строка `←`).
  - `mapStoredMessages` — для роли `tool` парсит сохранённый JSON `{ok, result}` (он в БД **не обрезан**, `sessions.py:650`) и берёт `result.run_id` в `childRunId`. Аргументы вызова в истории не сохраняются → после перезагрузки `input` отсутствует.
- `frontend/src/components/ChatMessage.tsx` — для `role === 'tool'` с `childRunId` рендерит `TraceRunNode` вместо строки `ℹ`; без `childRunId` — как сейчас.
- `frontend/src/hooks/useRunStream.ts` — `RunStep` получает `toolName?: string` и `childRunId?: string`; заполняются в `tool_call`/`tool_result` (`childRunId` — через `extractChildRunId`).
- `frontend/src/api.ts` — `RunOut` получает `parent_run_id: string | null`. `getRun()` уже есть, новых функций не нужно.
- Тесты: `frontend/src/components/TraceSteps.test.ts` — `extractChildRunId`, `foldNestedRuns`, `runTraceToSteps`; `frontend/src/components/TraceRunNode.test.tsx` — раскрытие узла с моком `getRun` (loading → результат → ошибка).

**Backend (минимальный хвост, разрешён планом)**

- `backend/catalog/api/schemas.py` — `RunOut.parent_run_id: str | None = None`.
- `backend/catalog/api/runs.py` — `get_run_endpoint` прокидывает `parent_run_id` из строки (в `repo_run.get_run` поле уже есть, менять репозиторий не нужно).
- `backend/catalog/skills/skill_tools.py` — в успешном возврате `_run` идентификаторы ставятся **перед** `text`: `ok`, `status`, `run_id`, `skill_id`, `skill_name`, `config_hash`, `verify_failures`, затем `text`. Семантики не меняет, но `_snip_result` (400 символов) перестаёт срезать `run_id` в живом кадре.

**Осознанное отклонение от плана:** отдельный список детей в API (`GET /runs/{id}/children`) **не заводим**. Ребро дерева приходит в payload тула — и живьём, и после перезагрузки истории; сегодня у apply-прогона детей не бывает, поэтому такой endpoint остался бы без потребителя. `parent_run_id` в `RunOut` отдаём — узел использует его, чтобы подписать запуск вложенным.

## Layout и состояния

Узел визуально повторяет `TraceStepGroup` (та же карточка, та же типографика) — трейс должен читаться как одна лента, а не как два разных виджета.

Оболочка:

```
rounded border border-line bg-surface p-1.5
```

В чате узел заворачивается в `catalog-message catalog-message--tool my-2` + `max-w-[88%]` (как ассистентские сообщения). В `TraceSteps` — как `li` внутри существующего `ol`.

Свёрнутый вид (`summary`, `flex cursor-pointer items-center gap-2 font-mono text-[11px] text-ink-muted`):

```
⤷ skill_extract_terms                    ✓ · запуск 4f2a1b3c
```

- `⤷` — `shrink-0 text-ink-faint`, `aria-hidden`.
- имя тула — `min-w-0 truncate`, `title` с полным именем.
- правый блок — `ml-auto flex shrink-0 items-center gap-1.5 text-ink-faint`: глиф статуса + `запуск {runId.slice(0, 8)}`.
- глиф: `✓` `text-success-ink` / `✗` `text-danger-ink` / `…` `text-ink-faint`.
- `<span class="sr-only">` со словом статуса: «ок» / «ошибка» / «выполняется».

Раскрытый вид — контейнер `mt-1 flex flex-col gap-1.5 border-l border-line pl-3` (та же лесенка вложенности, что у группы шага), блоки сверху вниз:

1. **Вход** — только если `input` задан: `<details>` с `summary` «вход» (`cursor-pointer text-ink-faint`) и `<pre class="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 text-ink-muted">`.
2. **Результат** — `result_text` дочернего запуска, тот же `<details>`/`<pre>`, `summary` «результат», текст `text-success-ink`. Пусто → блок не рендерим.
3. **Проверки** — из записей `kind="verify"` трейса: есть провалы → `<p class="text-danger-ink">✗ проверки: {failures.join('; ')}</p>`; записи есть и все прошли → `<p class="text-success-ink">✓ проверки пройдены</p>`; записей нет → блока нет.
4. **Шаги** — `<TraceSteps steps={runTraceToSteps(run.trace, runId)} depth={depth + 1} />`. Пустой трейс → `<p class="text-xs text-ink-faint">Шагов нет.</p>` (тот же текст-плейсхолдер, что у пустой ленты).
5. **Подпись** — `text-[11px] text-ink-faint`: `вложенный запуск · статус {run.status}`; при `run.parent_run_id === null` слово «вложенный» опускаем.

Состояния узла:

| Состояние | Что показываем |
|---|---|
| Свёрнут (по умолчанию) | только `summary`; запрос не отправлен |
| Загрузка после первого раскрытия | `<p role="status" aria-live="polite" class="text-[11px] text-ink-faint">Загружаю запуск…</p>`, на `details` — `aria-busy="true"` |
| Загружено, `status = 'ok'` | глиф `✓`, блоки входа/результата/проверок/шагов |
| Загружено, `status = 'failed' \| 'cancelled'` | глиф `✗`, сверху `rounded bg-danger-soft p-1.5 text-danger-ink` с причиной: failures проверок, иначе `Запуск завершился со статусом {status}` |
| Загружено, `status = 'pending' \| 'running'` | глиф `…`, текст «Запуск ещё выполняется» + `btn-secondary text-[11px]` «Обновить» |
| Ошибка запроса | `role="alert"` `rounded bg-danger-soft p-1.5 text-[11px] text-danger-ink` с `detail` из `ApiError` + `btn-secondary text-[11px]` «Повторить» |
| `404 run not found` (прогон удалён вместе со скиллом) | `text-[11px] text-ink-faint` «Запуск не найден» — без danger-оформления и без «Повторить» |

Статус в свёрнутом виде до загрузки берётся из `ok` payload'а тула (`✓`/`✗`), после загрузки — из `run.status`.

Маппинг `runTraceToSteps` (`TraceEntry` → `RunStep`, `id = nested-{runId}-{index}`, `stepId = data.step_id`):

| `kind` записи | `RunStep` |
|---|---|
| `script` | `kind: 'script'`, `stage: data.ok ? 'done' : 'error'`, `text: 'Скрипт: готово'` / `'Скрипт: ошибка'`, при `data.chars` — суффикс ` · {chars} симв.` |
| `verify` | `kind: 'verify'`, `text: 'Проверка (итерация {iteration})'`, `passed`, `failures` |
| `tool_call` | `kind: 'tool_call'`, `text: '→ {name}({args})'` через `formatToolArgs` |
| `tool_result` | `kind: 'tool_result'`, `text: '← {name}'`, `ok`, `result` через `formatToolResult` |
| `error` | `kind: 'script'`, `stage: 'error'`, `text: 'Ошибка'`, `error: data.error` |
| `llm` | `kind: 'step'`, `text: 'Итерация {iteration}'`, `iteration` |
| `skill_pin` | `kind: 'step'`, `text: 'пин конфига · {data.config_hash}'` |
| прочее | `kind: 'step'`, `text: kind` |

## Взаимодействия

- **Раскрытие.** Нативный `<details>`; загрузка на `onToggle` при `open === true` и отсутствии уже загруженных данных. Повторные сворачивания/раскрытия запрос не повторяют. «Повторить»/«Обновить» сбрасывают ошибку и грузят заново.
- **Гонки.** Ответ применяется, только если `runId` не изменился (проверка перед `setState`); размонтирование во время запроса не должно писать состояние.
- **Апгрейд строки в чате.** `tool_result` для `skill_*` с извлечённым `run_id` заменяет последнее «висящее» сообщение того же тула. Не нашли пару (например, кадр пришёл после переподключения) — пушим отдельное сообщение-узел, строка `→` остаётся выше как есть.
- **Вход.** Из аргументов вызова: `arguments.text`, если строка; иначе `arguments.texts.join('\n\n---\n\n')`; иначе `formatToolArgs(arguments)`. Пустая строка — блок не показываем.
- **Ошибочный вызов без запуска.** Ранние возвраты `skill_tools._run` (`provide text or texts`, исключение до `create_run`) не содержат `run_id` → узел не создаётся, чат показывает привычные `→`/`←` строки. Это осознанно: узел без запуска раскрывать нечем.
- **Смена сессии / очистка истории.** Узлы уходят вместе с сообщениями, состояние загрузки живёт внутри компонента и умирает с ним.
- **Крайние случаи.**
  - Очень длинный вход или результат — `<pre>` с `whitespace-pre-wrap break-words overflow-x-auto`, как в существующих блоках трейса; узел не растягивает колонку.
  - Дочерний трейс пуст или `null` (запуск не дошёл до `finish_run`) — блок «Шаги» показывает плейсхолдер, остальные блоки рендерятся по наличию данных.
  - Глубина > 1 — внутри дочернего `TraceSteps` (`depth = 1`) узлы не создаются, `tool_result` остаётся плоским.
  - Несколько вызовов одного и того же скилла подряд — каждый апгрейдит **своё** последнее висящее сообщение, id запусков разные, узлы независимы.

## Стиль и токены

- Только семантические утилиты `docs/ui-style-guide.md`: `border-line`, `bg-surface`, `bg-surface-muted`, `bg-danger-soft`, `text-ink-muted`, `text-ink-faint`, `text-success-ink`, `text-danger-ink`. Сырые палитры (`slate-*`, `red-*`, …) запрещены.
- Типографика трейса неизменна: `font-mono text-[11px]`; плейсхолдеры — `text-xs text-ink-faint`.
- Ритм и вложенность — как у `TraceStepGroup`: карточка `p-1.5`, лесенка `border-l border-line pl-3`, зазоры `gap-1.5`.
- Кнопки «Повторить» / «Обновить» — примитив `.btn-secondary` с `text-[11px]`; новых классов в `index.css` не заводим.
- Глифы текстовые (`⤷ ✓ ✗ …`), как в существующей ленте; новых иконок в `icons.tsx` и новых зависимостей нет.

## Доступность (a11y)

- Раскрытие через нативные `<details>/<summary>` — клавиатура и скринридер работают без ARIA-костылей (тот же паттерн, что у группы шага и блоков «код»/«результат»).
- Глифы статуса `aria-hidden`; словесный статус дублируется в `sr-only` внутри `summary`.
- Загрузка — `role="status"` + `aria-live="polite"`, на `details` `aria-busy` во время запроса.
- Ошибка — `role="alert"`; «Запуск не найден» — обычный текст, без alert (не событие, а факт).
- Кнопки получают фокус-кольцо из примитива (`focus-visible:ring-2 ring-brand`); порядок фокуса — естественный DOM-порядок ленты.
- Шаги дочернего запуска — `<ol>`/`<li>` существующего `TraceSteps`, семантика списка сохраняется.

## Контракты данных

- `GET /runs/{run_id}` → `RunOut`: `id`, `skill_id`, `status`, `trace: TraceEntry[] | null`, `result_text`, **`parent_run_id: string | null`** (новое поле). Дочерний запуск создаётся с `persist=false`, поэтому `output_doc_id` пуст — в узле его не показываем.
- Payload скилл-тула (`skill_tools._run`, ADR-0019): `ok`, `status`, `run_id`, `skill_id`, `skill_name`, `config_hash`, `verify_failures`, `text`. Порядок ключей значим — см. backend-хвост выше.
- WS-кадр `tool_result`: `{ name, ok, result }`, где `result` — строка, обрезанная до 400 символов (`_snip_result`). Отсюда правило «сначала `JSON.parse`, потом регексп».
- Сохранённое сообщение роли `tool`: `content = {"ok": …, "result": {…}}` **без обрезки** (`sessions.py:650`) — после перезагрузки истории `run_id` берётся отсюда.
- `parent_run_id` вложенного запуска сегодня равен sentinel `"session"` (ADR-0019 §7). UI **не сравнивает** его с id родителя и не строит дерево по этому значению — только отличает `null` от не-`null` для подписи. Так узел одинаково работает и в чате, и в ленте прогона, когда там появятся дети.

## Критерии визуальной приёмки

- [ ] В чате вызов скилл-тула отображается **одним** узлом (`⤷ имя_тула · глиф · запуск {8 символов id}`), а не парой строк `→`/`←`.
- [ ] Узел свёрнут по умолчанию; первое раскрытие запускает `GET /runs/{id}`, повторное — нет.
- [ ] Раскрытый узел показывает вход (когда аргументы известны), результат, проверки и шаги дочернего запуска.
- [ ] Провал проверок виден как список причин в токенах danger (`bg-danger-soft` + `text-danger-ink`), а не как один глиф `✗`.
- [ ] Шаги дочернего запуска отрендерены существующим `TraceSteps` (`font-mono text-[11px]`, лесенка `border-l border-line pl-3`), внутри них узлы второго уровня не создаются.
- [ ] Состояния «Загружаю запуск…», «Запуск ещё выполняется» + «Обновить», ошибка + «Повторить», «Запуск не найден» реализованы и различимы.
- [ ] Оформление узла совпадает с `TraceStepGroup`: `rounded border border-line bg-surface p-1.5`, `summary` в `font-mono text-[11px] text-ink-muted`.
- [ ] Глифы статуса `aria-hidden`, словесный статус есть в `sr-only`; загрузка — `role="status"`, ошибка — `role="alert"`.
- [ ] Тул без вложенного запуска (`read_document`, ошибочный вызов без `run_id`) рендерится по-старому — плоской строкой.
- [ ] В `TraceSteps` пара `tool_call` + `tool_result` с `childRunId` сворачивается в узел, а `tool_result` без него остаётся плоским (покрыто тестом `foldNestedRuns`).
- [ ] В диффе нет сырых палитр Tailwind, новых классов в `index.css`, новых иконок и новых зависимостей.
