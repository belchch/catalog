# CATALOG-141 — Дизайн UI

- **Источник:** `docs/plan/shift-2026-08-18/03-CATALOG-141-ui-script-dry-run.md`
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Пользователь отлаживает Python-черновик скилла сам, без диалога с моделью, и заранее видит, почему сборка скилла заблокирована.

Сценарий (панель «Черновик скилла» → секция `Script`):

1. Пользователь правит код в textarea. Под кодом — строка статуса прогона: «Не прогонялся».
2. Нажимает «Прогнать». Кнопка уходит в pending («Прогоняю…», `aria-busy`), повторные клики игнорируются. Если в textarea есть несохранённые правки — код сначала сохраняется (тот же путь, что «Сохранить script»), потом гоняется dry-run: статус всегда относится к сохранённому коду.
3. Ошибка — бейдж «Ошибка», стадия (`validate` / `run` / `verify`), текст ошибки, строка с номером и её исходным текстом, кнопка «Перейти к строке N» (фокус в textarea + выделение этой строки + скролл).
4. Успех — бейдж «Прогон ok», метаданные (длительность, тип и длина вывода, исходы verify) и два свёрнутых блока: `input_preview` и `output_preview`. Усечённое превью помечено.
5. Правка кода после зелёного прогона → статус «Устарел»; сборка снова заблокирована.
6. В сводке (`ArtifactSummaryCard`) строка «Скрипт» несёт тот же статус компактным бейджем, без превью.
7. В шапке чата под кнопкой «Создать скилл» — причина блокировки сборки («скрипт не прогнан» / «прогон устарел» / «прогон упал»), видимая до клика, а не только как 422 после.
8. Прогон, сделанный моделью через `try_skill_script`, приезжает кадром `session_artifacts` и меняет бейджи без перезагрузки: превью при этом нет (их не хранит backend), только статус.

## Дерево компонентов и файлы

Новое:

- `frontend/src/lib/dryRun.ts` — чистый модуль вывода статуса (без React). Экспортирует:
  - `type DryRunState = 'none' | 'ok' | 'error' | 'stale'`
  - `scriptDryRun(artifacts): ScriptDryRunStatus | null` — статус слота `script` из payload;
  - `dryRunState({ status, artifactUpdatedAt, dirty }): DryRunState`;
  - `dryRunLabel(state): string` — короткая подпись бейджа;
  - `dryRunBadgeClass(state): string` — `badge-*` по состоянию;
  - `stageLabel(stage): string` — RU-подпись стадии;
  - `buildBlockReason(artifacts): string | null` — причина блокировки сборки для CTA (учитывает `kind` из `meta` и script-шаги `steps`);
  - `errorLineNo(status, lastRun): number | null` — номер строки из ответа прогона, иначе из текста ошибки.
  Обоснование выделения модуля: одна и та же логика нужна трём компонентам (`ArtifactsPanel`, `ArtifactSummaryCard`, `App` → `Chat`), и её удобно покрыть юнит-тестами без рендера.
- `frontend/src/lib/dryRun.test.ts` — таблица состояний и текстов причины блокировки.
- `frontend/src/components/ArtifactsPanel.test.tsx` — четыре статуса, disabled при пустом коде, анти-даблклик, показ номера строки, свёрнутые превью.

Изменяемое:

- `frontend/src/api.ts` — типы `ScriptDryRunStatus` (`slot`, `sha256`, `ok`, `stage`, `error`, `time`), `ScriptTryResult` (по `ScriptTryOut`: `ok`, `stage`, `error`, `input_preview`, `input_len`, `output_preview`, `output_len`, `output_kind`, `duration_ms`, `verify`, `line_no`, `source_line`), поле `dry_run?: ScriptDryRunStatus | ScriptDryRunStatus[] | null` в `SessionArtifact`, функция `trySkillScript(sessionId, body?)` → `POST /sessions/{id}/artifacts/script/try`.
- `frontend/src/hooks/usePlannerSession.ts` — `tryScript(): Promise<ScriptTryResult>`: сохраняет script при dirty (через существующий `saveScript`), вызывает `trySkillScript`, затем обновляет артефакты (`getSessionArtifacts` → `setArtifacts`), чтобы бейдж и гейт совпали с серверным состоянием (HTTP dry-run не рассылает WS-кадр). Кадр `session_artifacts` уже несёт `dry_run` — правок в обработчике не требуется.
- `frontend/src/components/ArtifactsPanel.tsx` — блок dry-run внутри секции `Script`: кнопка, статус, ошибка со строкой, свёрнутые превью, in-flight guard.
- `frontend/src/components/ArtifactSummaryCard.tsx` — бейдж статуса в строке «Скрипт».
- `frontend/src/App.tsx` — `buildBlockReason(planner.artifacts)` → новый prop в `Chat`.
- `frontend/src/components/Chat.tsx` — подсказка причины блокировки в шапке.

## Layout и состояния

### Секция `Script` в `ArtifactsPanel`

Порядок сверху вниз внутри существующего `sectionShell('script', …)`:

1. Заголовок `SCRIPT` + `statusRow` (как сейчас).
2. Подсказки по `kind` (как сейчас).
3. `textarea` с кодом (как сейчас).
4. Ошибка статической валидации `scriptArt.error` (как сейчас).
5. **Строка dry-run** — новый блок:
   `<div role="status" aria-live="polite">` слева бейдж + мета, справа кнопка «Прогнать».
   Класс контейнера: `mt-2 flex items-center justify-between gap-2`.
6. **Блок результата** — под строкой dry-run (только при наличии данных).
7. Существующий `saveBtn('script', …)`.

### Матрица состояний

| Состояние | Условие | Бейдж | Дополнительно |
|---|---|---|---|
| `none` | `dry_run` отсутствует или `dry_run.time === null` | `badge-neutral` «Не прогонялся» | мета-строка: «прогон нужен для сборки» |
| `ok` | `dry_run.ok === true` и нет несохранённых правок | `badge-success` «Прогон ok» | время прогона (`time`, локальный формат), блок результата |
| `error` | `dry_run.ok === false`, `time !== null`, код не менялся после прогона | `badge-danger` «Ошибка» | стадия + текст ошибки + строка |
| `stale` | несохранённые правки в textarea, **или** `dry_run.ok === false` и `updated_at` артефакта позже `dry_run.time` | `badge-warning` «Устарел» | «код менялся после прогона — прогоните снова» |

Вывод состояния (правила по порядку, первое сработавшее):

1. `dirty` (`scriptDraft !== serverScript`) → `stale`.
2. `status == null || status.time == null` → `none`.
3. `status.ok` → `ok` (сервер уже сверил `sha256`, поэтому зелёный не может быть устаревшим).
4. `Date.parse(artifact.updated_at) > Date.parse(status.time) + 1000` → `stale`.
5. иначе → `error`.

Осознанный компромисс: если пользователь сохранил идентичный код после упавшего прогона, состояние покажет «Устарел», а не «Ошибка». Действие пользователя в обоих случаях одно и то же (прогнать снова), а хеша кода у клиента нет — sha256 в браузере не считаем.

### Кнопка «Прогнать»

- Класс `btn-secondary`, `type="button"`, текст «Прогнать» / pending «Прогоняю…».
- `disabled` при: пустом `scriptDraft.trim()`, in-flight прогоне, `streaming` (общий `inputsDisabled`), `saving === 'script'`.
- `title` в disabled-состоянии: «Добавьте код скрипта» / «Идёт генерация» / «Прогоняю…».
- `aria-busy={inFlight}`.
- Disabled-вид — как в остальной панели: `surface-muted` + `ink-faint` + `cursor-not-allowed` (в `btn-secondary` уже зашито).
- Пока есть несохранённые правки, под кнопкой мета-текст: «код сохранится перед прогоном» (`text-[10px] text-ink-faint`).

### Блок результата (успех)

Рендерится, когда есть локальный ответ прогона (`lastRun?.ok`):

```
[мета] 128 мс · выход str · 830 симв. · вход 1 240 симв.
[verify] Проверки: 2/3 · не прошло: min_length — короче 200 символов
▸ Вход (input_preview)      ← <details>, свёрнут по умолчанию
▸ Выход (output_preview)    ← <details>, свёрнут по умолчанию
```

- Превью в `<pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-muted p-1.5 font-mono text-[11px] text-ink-muted">` — тот же приём, что «сырой JSON» в секции Steps.
- Пометка усечения: если превью оканчивается на `…[truncated]` или `len` больше длины превью — рядом с заголовком блока `badge-warning` «Усечено» и в мета-строке блока «показаны первые 2000 симв. из N».
- `verify` показываем только если `verify != null`: «Проверки: `passed`/`всего`», ниже список непрошедших (`check` + `reason`), `skipped` помечены как «пропущена».
- Если после прогона код правился (`dirty`), над блоком строка `text-[11px] text-warning-ink`: «Результат относится к предыдущей версии кода».

### Блок результата (ошибка)

- Контейнер `mt-2 rounded-md border border-danger-line bg-danger-soft px-2 py-1.5 text-[11px] text-danger-ink` (канон Error из style guide).
- Строка 1: «Ошибка на стадии: <стадия>» — `validate` → «проверка кода», `run` → «запуск», `verify` → «проверки результата».
- Строка 2: текст ошибки, `whitespace-pre-wrap break-words`.
- Строка 3 (если известен номер строки): монопространственная строка `N │ <source_line>` с подсветкой `bg-danger-soft`/`text-danger-ink` внутри контейнера + кнопка `btn-ghost` «Перейти к строке N».
- `id="script-dry-run-error"` добавляется в `aria-describedby` у textarea рядом с существующими `script-error` / `script-save-error`.
- Источник номера строки: `lastRun.line_no`; после перезагрузки — разбор текста сохранённой ошибки по шаблону `(line N: …)`, который формирует backend. Не разобрали — блок строки не показываем, текст ошибки остаётся.
- Если строка вне длины текущего черновика — кнопка перехода не рендерится.

### `ArtifactSummaryCard`

- В `<li>` строки «Скрипт», в правом слоте (там сейчас «готово» / «не требуется»), при `needScript && есть содержимое` — бейдж вместо «готово»: `badge-success` «Прогон ok» / `badge-danger` «Ошибка прогона» / `badge-warning` «Прогон устарел» / `badge-neutral` «Нужен прогон». `title` — полная фраза.
- Сводка не знает о несохранённых правках textarea (ей передают только `artifacts`), поэтому выводит состояние строго из payload — правила 2–5 выше.
- Строки «Настройки» / «Шаги» / «Промпт» и счётчик «Готово N из M» не меняются: dry-run не влияет на подсчёт готовности разделов.
- Превью и стадия в сводку не попадают.

### Шапка чата (`Chat`)

- Новый prop `buildBlockReason: string | null`.
- Кнопка «Создать скилл» остаётся активной: единственный источник истины по гейту — сервер (422), а клиентский вывод может расходиться в краевых случаях. Роль подсказки — предупредить, а не запретить.
- Подсказка рендерится строкой под существующим flex-рядом шапки: `mt-1 text-[11px] text-warning-ink`, `role="status"`, `id` связывается с кнопкой через `aria-describedby`.
- Тексты:
  - `kind=script`, нет прогона: «Сборка заблокирована: скрипт не прогнан — откройте черновик и нажмите «Прогнать».»
  - устарел: «Сборка заблокирована: прогон устарел — код менялся после прогона.»
  - ошибка: «Сборка заблокирована: последний прогон упал (<стадия>).»
  - `kind=pipeline`: «Сборка заблокирована: script-шаги без зелёного прогона: шаг 2, шаг 3.» (номер = `slot` `steps:<index>` + 1).
- Подсказка скрыта, когда гейт зелёный, `kind=agent`, script-шагов нет, `messages.length === 0`, идёт сборка (`buildingSkill`/`proposingTracks`) или уже показана ошибка `buildError`.

### loading / empty / error панели

Существующее поведение сохраняется: `artifactsLoading` → «Загружаю артефакты…», пустой список → текущая подсказка, `artifactsError` → `text-danger-ink`. Блок dry-run внутри секции `Script` рендерится всегда, когда секция видна; при отсутствии сессии панель по-прежнему показывает заглушку.

## Взаимодействия

- **Клик «Прогнать»:** `inFlightRef.current` — если `true`, обработчик выходит немедленно (второго запроса нет). Иначе: `inFlight = true` → при dirty `await onSaveScript(scriptDraft)` → `await onTryScript()` → `setLastRun(result)` → `finally { inFlight = false }`. Ошибка сети/HTTP пишется в отдельное поле состояния и показывается в том же блоке ошибки (`role="alert"` не нужен, блок уже под `aria-live="polite"`).
- **Ожидание:** серверный таймаут прогона — 5 с; отдельного клиентского таймера нет, кнопка остаётся в pending до ответа.
- **Клик «Перейти к строке N»:** `scriptRef.current.focus()`, `setSelectionRange(startOfLine, endOfLine)`, `scrollIntoView({ block: 'nearest' })`. Выделение строки — единственная подсветка внутри textarea (стилизовать отдельные строки в textarea нельзя), плюс продублированная подсвеченная строка в блоке ошибки.
- **Правка кода:** `dirty` → бейдж «Устарел»; `lastRun` не сбрасывается, но помечается как относящийся к предыдущей версии; блок ошибки остаётся доступным для навигации.
- **Кадр `session_artifacts` от модели:** бейдж и подсказка гейта пересчитываются автоматически (данные приходят в `artifacts`); локальный `lastRun` не трогаем — превью модельного прогона в UI нет и не обещаются.
- **Смена сессии:** `lastRun`, ошибка прогона и in-flight флаг сбрасываются в существующем `useEffect` по `sessionId`.
- **Крайние случаи:** пустой код → кнопка disabled; `streaming` → все элементы секции disabled как сейчас; `steps` c ошибкой парсинга → `dry_run` приходит `[]`, подсказка гейта по шагам не строится; несколько script-шагов → в подсказке перечисляются все незелёные.

## Стиль и токены

- Кнопка прогона — `btn-secondary` (вторичное действие рядом с `btn-primary` «Сохранить script»). Новых кнопочных классов не вводим.
- Статусы — только существующие `badge-success` / `badge-danger` / `badge-warning` / `badge-neutral`.
- Ошибка — `bg-danger-soft` + `border-danger-line` + `text-danger-ink`; предупреждения — `text-warning-ink`; мета — `text-ink-faint`.
- Типографика панели: заголовки секций `text-[11px] uppercase tracking-wide`, мета `text-[10px]`, тексты `text-[11px]`, код `font-mono text-[11px]`.
- Отступы: `mt-2` между блоками секции, `gap-2` внутри строк, `p-1.5` внутри `pre`, `px-2 py-1.5` в блоке ошибки.
- Disabled: `surface-muted` + `ink-faint` + `cursor-not-allowed`, без `opacity-50`. Focus-visible: `ring-2 ring-brand` (даётся примитивами).
- Сырые палитры Tailwind (`red-*`, `slate-*`, …) не используются. Новых CSS-переменных и правил в `index.css` не добавляем: сводка получает бейджи существующими утилитами.

## Доступность (a11y)

- Строка статуса: `role="status" aria-live="polite"` — обновление после прогона и после кадра от модели объявляется без перерисовки фокуса.
- Кнопка прогона: `aria-busy` в pending, осмысленный `title`/`aria-description` в disabled-состоянии, доступное имя меняется на «Прогоняю…».
- Блок ошибки: `id="script-dry-run-error"` в `aria-describedby` textarea; стадия и номер строки — текстом, не только цветом.
- Превью: нативные `<details>/<summary>`, `summary` фокусируем с клавиатуры, состояние раскрытия передаётся браузером; заголовки «Вход» / «Выход» уникальны в секции.
- «Перейти к строке N» — настоящая `<button>`, доступное имя содержит номер строки.
- Подсказка гейта: `role="status"`, связана с CTA через `aria-describedby`, так что screen reader читает причину до активации кнопки.
- Статус не передаётся одним цветом: бейдж всегда содержит текст.

## Контракты данных

- `POST /sessions/{id}/artifacts/script/try`, тело `{ code?, doc_ids?, step_index? }` (UI отправляет пустое тело: гоняется сохранённый артефакт `script` и документы сессии). Ответ — `ScriptTryOut`: `ok`, `stage: 'validate'|'run'|'verify'|null`, `error`, `input_preview`, `input_len`, `output_preview`, `output_len`, `output_kind: 'str'|'list'|null`, `duration_ms`, `verify: { passed, failures[], checks[{check, params, passed, reason, source, skipped}] } | null`, `line_no`, `source_line`.
- `GET /sessions/{id}/artifacts` и WS-кадр `session_artifacts` несут `dry_run`: для `script` — объект `{ slot, sha256, ok, stage, error, time }`, для `steps` — массив таких объектов по script-шагам (`slot = steps:<index>`), для остальных типов — `null`.
- `ok` на сервере уже учитывает совпадение `sha256` с текущим кодом слота, поэтому клиент хеш не считает.
- Превью и `line_no` в payload артефакта не хранятся — они только в ответе прогона; это и определяет «превью есть только для прогона, сделанного в этой сессии UI».
- Источники: план шага, ADR-0023 (п. 3, 4, 7), `backend/catalog/api/schemas.py` (`ScriptDryRunStatus`, `ScriptTryOut`).

## Критерии визуальной приёмки

- [ ] В секции `Script` под textarea есть строка статуса и кнопка «Прогнать» класса `btn-secondary`; «Сохранить script» остаётся `btn-primary`.
- [ ] Четыре состояния отображаются бейджами `badge-neutral` «Не прогонялся», `badge-success` «Прогон ok», `badge-danger` «Ошибка», `badge-warning` «Устарел»; текст статуса присутствует всегда, не только цвет.
- [ ] Кнопка disabled при пустом коде и во время прогона; в pending текст «Прогоняю…» и `aria-busy`.
- [ ] Повторный клик во время прогона не отправляет второй запрос.
- [ ] При ошибке видны стадия (RU-подпись), текст ошибки, строка `N │ <код>` с danger-подсветкой и кнопка «Перейти к строке N», которая фокусирует textarea и выделяет эту строку.
- [ ] При успехе `input_preview` и `output_preview` — свёрнутые `<details>`; видны длительность, тип и длина вывода, исходы verify; при усечении есть пометка.
- [ ] Несохранённые правки дают «Устарел» и подпись «код сохранится перед прогоном» у кнопки.
- [ ] В `ArtifactSummaryCard` строка «Скрипт» несёт тот же статус бейджем, без превью и стадии; счётчик «Готово N из M» не изменился.
- [ ] Под кнопкой «Создать скилл» видна причина блокировки сборки до клика; кнопка остаётся активной; при зелёном гейте и для `kind=agent` подсказки нет.
- [ ] Прогон модели меняет бейджи в панели и в сводке без перезагрузки страницы.
- [ ] Ни одной сырой палитры Tailwind и ни одного нового цвета/кнопочного класса; блоки ошибок используют `bg-danger-soft` + `border-danger-line` + `text-danger-ink`.
- [ ] Все интерактивные элементы блока доступны с клавиатуры и имеют видимый focus-ring `ring-2 ring-brand`.
