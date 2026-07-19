# CATALOG-40 — Дизайн UI

- **Источник:** `docs/plan/night-shift/CATALOG-40-ui-save-to-document-broken.md`
- **Статус дизайна:** Ready

> **Важно для генератора/ревьюера:** первичный фикс `DocumentCombobox` (удаление `onBlur` на root div) уже выполнен в шаге CATALOG-28 (коммит `aaee19e`) и слит в текущую ветку. Логика `RunView` корректна: `outputDocId = run.outputDocId ?? savedDoc?.id ?? null` (`RunView.tsx:30`), `canSaveResult = run.finished && statusOk && !outputDocId && !!run.resultText` (`RunView.tsx:34`), а `useRunStream.ts:170` выставляет `outputDocId` только если бэк прислал `output_doc_id` в finish-фрейме. Этот шаг CATALOG-40 — **regression-only + end-to-end приёмка** сценария «сохранить в документ». Правки кода не планируются. Если regression-проверка вскроет баг на стороне бэка (например, бэк ошибочно шлёт `output_doc_id` для preview-режима) — это отдельный backend-план, не этот шаг.

## Цель и пользовательский путь

Сценарий — пользователь применяет committed-скил к документу(ам) и получает результат в виде документа или текста на экране. Два режима применения, каждый проходит end-to-end:

- **Persist (кнопка «В док»):** выбрать документы в слотах `SkillsPanel` → кнопка активируется → клик → `handleApply('persist')` (`App.tsx:187`) → `setActiveRunId(runId)` → открывается `RunView` → бэк выполняет скил, в finish-фрейме шлёт `output_doc_id` → `RunView` показывает блок «Документ создан: …», **кнопка «Сохранить как новый документ» НЕ показывается** (нечего сохранять — уже сохранено).
- **Preview (кнопка «На экран»):** тот же флоу, но `handleApply('preview')` → `RunView` открывается → бэк в finish-фрейме **НЕ** шлёт `output_doc_id` → `outputDocId=null` → `canSaveResult=true` → **кнопка «Сохранить как новый документ» видна** → клик → `handleSaveResult(runId)` (`App.tsx:201`) → `saveRunResult(runId)` создаёт документ → `setSavedResultDoc(doc)` → `outputDocId = savedDoc?.id` → `canSaveResult` становится `false`, кнопка скрывается, появляется блок «Документ создан: …».

Регрессионные сценарии (без правок кода):

- **CATALOG-28/39 regression:** выбор документа в слоте `DocumentCombobox` не ломается (фикс `onBlur` остался на месте), кнопки «В док» / «На экран» активируются после выбора.
- **CATALOG-18 regression:** повторные сохранения работают для нескольких прогонов подряд; `savedResultDoc` сбрасывается в `handleApply` (`App.tsx:190`) перед новым прогоном.

Шаги пользователя для обоих режимов расписаны в разделе «Взаимодействия».

## Дерево компонентов и файлы

Новых компонентов нет. Изменения в коде **не планируются** (логика корректна после CATALOG-28); компоненты перечислены ниже как контракты для regression- и end-to-end-приёмки.

- `frontend/src/components/SkillsPanel.tsx` — **не меняется**. Слоты `input_arity ∈ {1, 2, null}` отрисовываются корректно (`:362-422`); валидность через `isSelectionValid` (`:44-55`); кнопки «В док» / «На экран» привязаны к `disabled={!valid || documents.length === 0}` (`:425-440`); `onApply(s.id, docIds, 'persist' | 'preview')` (`:428, :436`). Проверяется: после выбора документа кнопки активируются, клик запускает apply.
- `frontend/src/components/DocumentCombobox.tsx` — **не меняется**. Фикс CATALOG-28 на месте: `onBlur` на корневом `<div>` отсутствует, outside-listener на `mousedown` (`:39-49`), Escape на триггере (`:116-121`) и listbox (`:137-143`). Проверяется: клик по option не отменяется до `onChange`.
- `frontend/src/App.tsx` — **не меняется**. `handleApply` (`:187-199`) сбрасывает `savedResultDoc` (`:190`), вызывает `skillsHook.apply(...)` и выставляет `activeRunId`. `handleSaveResult` (`:201-217`) вызывает `saveRunResult(runId)`, кладёт результат в `savedResultDoc`, рефрешит список документов, переключает `currentDocId` на новый.
- `frontend/src/components/RunView.tsx` — **не меняется**. Контракт рендера:
  - `outputDocId = run.outputDocId ?? savedDoc?.id ?? null` (`:30`).
  - `canSaveResult = run.finished && statusOk && !outputDocId && !!run.resultText` (`:34`).
  - Блок «Документ создан: …» — `outputDocId && (...)` (`:113-117`), emerald-палитра.
  - Кнопка «Сохранить как новый документ» — `canSaveResult && (...)` (`:118-126`), indigo, `disabled={savingResult}`, `onClick → onSaveResult(runId)`.
  - Плейсхолдер результата — `run.resultText ? <markdown> : «Ожидание результата…» / «Нет текстового результата.»` (`:127-135`).
- `frontend/src/hooks/useRunStream.ts` — **не меняется**. На finish-фрейме: `if (e.output_doc_id !== undefined) setOutputDocId(e.output_doc_id)` (`:170`) — поле выставляется **только если бэк его прислал**. На монтировании/смене `runId` всё сбрасывается (`:189-197`), включая `setOutputDocId(null)`.

> Если end-to-end-проверка вскроет необходимость правки — она ограничивается `RunView.tsx` или `useRunStream.ts` и должна быть **минимальной**. Если выяснится, что бэк ошибочно шлёт `output_doc_id` для preview-режима — это backend-план, этот шаг не правит.

## Layout и состояния

Структура экрана «Прогон» в `RunView` (не меняется, контекст для приёмки):

```
<div class="flex h-full flex-col">
  ├─ header: "Прогон <id8> [status]"   [← К чату]   [Стоп (если !run.finished)]
  └─ grid 2 cols (md), 1 col (mobile):
       ├─ left col "Лента шагов":
       │    ├─ meta (model/provider/kind/docs/system prompt)
       │    ├─ TraceSteps
       │    ├─ error / closed warnings
       │    └─
       └─ right col "Результат":
            ├─ if outputDocId:   «Документ создан: «<title>»»  ← persist-режим или после save
            ├─ if canSaveResult: [Сохранить как новый документ] ← preview-режим, ещё не сохранён
            └─ run.resultText ? <ReactMarkdown> : placeholder
```

Состояния правой колонки «Результат» — основной фокус приёмки:

| Состояние | `run.finished` | `run.status` | `run.outputDocId` | `savedDoc` | `run.resultText` | Что рисуется |
|---|---|---|---|---|---|---|
| **Persist выполнен** | `true` | `'ok'` | `<id>` (из finish-фрейма) | `null` | есть | «Документ создан: …» + текст. Кнопки save **нет**. |
| **Preview выполнен, не сохранён** | `true` | `'ok'` | `null` | `null` | есть | **Кнопка** «Сохранить как новый документ» + текст. Блока «Документ создан» **нет**. |
| **Preview выполнен + save в процессе** | `true` | `'ok'` | `null` | `null` | есть | Кнопка `disabled`, подпись «Сохраняю…» |
| **Preview выполнен + сохранён** | `true` | `'ok'` | `null` | `<doc>` | есть | «Документ создан: …» (через `savedDoc?.id`), кнопка скрывается. |
| **Run failed** | `true` | `'error'` | — | — | — | Бейдж `error` красным, текст «Нет текстового результата.» Кнопки save **нет**. |
| **Run в процессе** | `false` | — | — | — | опц. | Текст «Ожидание результата…» или стримящийся `resultText`. Кнопки save **нет** (`run.finished=false`). |
| **Нет текстового результата** | `true` | `'ok'` | `null` | `null` | `''` | Плейсхолдер «Нет текстового результата.» Кнопки save **нет** (`!run.resultText`). |

Loading-состояние отдельное не нужно — его роль играет плейсхолдер «Ожидание результата…» + бейдж статуса в header. Error-состояние уровня прогона — `run.error` рисуется в левой колонке (`RunView.tsx:106`), плюс красный бейдж `run.status` в header. Состояние `run.closed && !run.finished` — amber-предупреждение «Соединение закрыто» (`:107-109`).

## Взаимодействия

Все механизмы уже реализованы; ниже — end-to-end-сценарии для приёмки.

### Сценарий E2E-1 — Persist (кнопка «В док»)

1. В `SkillsPanel` выбрать committed-скил. Заполнить слоты документами согласно `input_arity` (см. сценарии A/B/C в `CATALOG-39.design.md`).
2. Убедиться, что кнопка «В док» активировалась (`disabled=false`).
3. Кликнуть «В док» → `onApply(s.id, docIds, 'persist')` → `handleApply('persist')` → `skillsHook.apply(...)` возвращает `runId` → `setActiveRunId(runId)` → `RunView` открывается.
4. Дождаться `run.finished=true` (бэк выполнит скил, пришлёт finish-фрейм с `output_doc_id`).
5. В правой колонке «Результат»:
   - **Виден** блок «Документ создан: «<title>»» (emerald).
   - **Не видна** кнопка «Сохранить как новый документ».
   - Под блоком — текст результата (`ReactMarkdown`).
6. В списке документов (вне `RunView`) появляется новый документ с этим `id`.

**Приёмка:** шаг 5 выполняется ровно так; новый документ присутствует в `GET /documents`. Повторный прогон того же скила в `persist` создаёт второй документ.

### Сценарий E2E-2 — Preview + save (кнопка «На экран»)

1. В `SkillsPanel` заполнить слоты, как в E2E-1.
2. Кликнуть «На экран» → `onApply(s.id, docIds, 'preview')` → `handleApply('preview')` → `setActiveRunId(runId)` → `RunView` открывается.
3. Дождаться `run.finished=true`. Бэк в finish-фрейме **не** шлёт `output_doc_id` → `run.outputDocId=null`.
4. В правой колонке «Результат»:
   - **Не виден** блок «Документ создан».
   - **Видна** кнопка «Сохранить как новый документ» (indigo), `disabled=false`.
   - Под кнопкой — текст результата.
5. Кликнуть кнопку → `onSaveResult(runId)` → `handleSaveResult(runId)`:
   - `setSavingResult(true)` → подпись кнопки «Сохраняю…», кнопка `disabled`.
   - `saveRunResult(runId)` возвращает `doc` → `setSavedResultDoc(doc)` → `outputDocId = savedDoc.id` → `canSaveResult=false`.
   - Кнопка скрывается, появляется блок «Документ создан: «<title>»».
   - `docs.refresh()` обновляет список документов, `setCurrentDocId(doc.id)` переключает активный документ.

**Приёмка:** шаг 4 → кнопка присутствует; шаг 5 → после клика кнопка исчезает, блок «Документ создан» появляется, новый документ виден в списке и становится активным.

### Сценарий E2E-3 — Регрессия DocumentCombobox (CATALOG-28/39)

1. Повторить сценарии A/B/C из `CATALOG-39.design.md` (выбор документа в single/multi-слотах `SkillsPanel`).
2. Убедиться, что после выбора кнопки «В док» / «На экран» активируются — то есть симптом 1 («apply из левого меню ничего не делает») не воспроизводится.

**Приёмка:** выбор в `DocumentCombobox` работает во всех трёх `input_arity`; клики по option доходят до `onChange`, `slots` заполняются, `valid=true`, кнопки активны.

### Сценарий E2E-4 — Регрессия повторных прогонов (CATALOG-18)

1. Выполнить E2E-2 (preview + save).
2. Не закрывая `RunView`, вернуться в `SkillsPanel` (кнопка «← К чата» или другой скил) и запустить новый прогон того же скила в любом режиме.
3. `handleApply` (`App.tsx:190`) вызывает `setSavedResultDoc(null)` — `outputDocId` нового прогона не «прилипает» к результату старого.
4. В новом прогоне `RunView` показывает корректное состояние (для нового `runId`), без блока «Документ создан» от предыдущего save.

**Приёмка:** при смене `runId` состояние `savedResultDoc` сбрасывается, кнопка save в новом preview-прогоне появляется с нуля.

### Граничные случаи

- **`run.status='error'` после прогона** — `canSaveResult=false` (`statusOk=false`), кнопка save **не показывается**, даже если `resultText` есть. Покрыто состоянием «Run failed».
- **Прогон завершился без `resultText`** (только tool-вызовы) — `canSaveResult=false` (`!run.resultText`), кнопка save **не показывается**. Покрыто состоянием «Нет текстового результата».
- **WS закрылся до finish** (`run.closed=true && !run.finished`) — amber-предупреждение в левой колонке, `canSaveResult=false`, кнопки save **нет**.
- **`savedResultDoc` от предыдущего прогона** — должен сбрасываться в `handleApply` (`App.tsx:190`); иначе в новом preview-прогоне блок «Документ создан» появится ложно и кнопка save будет скрыта. Проверяется в E2E-4.
- **`saveRunResult` завершился ошибкой** — `setNotice(e.message)` (App.tsx:211), `savingResult=false`, `savedResultDoc` остаётся `null`, кнопка save остаётся видимой и активной. Пользователь может повторить клик.
- **Бэк ошибочно шлёт `output_doc_id` для preview** — это проявится как «кнопка save не видна в preview-режиме». Корень проблемы на бэке; в этом шаге **не чинится**, эскалируется в backend-план. На стороне фронта логика верна: `useRunStream.ts:170` доверяет finish-фрейму, иного источника `outputDocId` нет.
- **Persist-прогон не вернул `output_doc_id`** (бэк забыл прислать) — `outputDocId=null` → `canSaveResult=true` → в persist-режиме появится кнопка save. Это аномалия бэка; regression-чек фиксирует поведение фронта (он честен: нет `output_doc_id` → показывает save), но создавать документ через save в этом случае — допустимый fallback (CATALOG-18).

## Стиль и токены

Стек — Tailwind v3 (ADR-0011). Новых зависимостей и токенов нет. Изменений визуала не планируется — все end-to-end-чеки сверяются с **уже существующим** визуальным языком `RunView` + `SkillsPanel` + `DocumentCombobox`.

Контрольные классы (для UI-ревьюера, что должно остаться как есть):

- Header `RunView`: `flex items-center justify-between border-b border-slate-800 px-4 py-2`; бейдж статуса — emerald для `'ok'`, red для прочего (`:42-51`).
- Кнопка «Стоп» (только при `!run.finished`): `rounded bg-red-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50` (`:62`).
- Колонки grid: `grid flex-1 grid-cols-1 gap-3 overflow-hidden p-3 md:grid-cols-2` (`:71`).
- Панель «Лента шагов»: `overflow-y-auto rounded-md border border-slate-800 bg-slate-900/40 p-3` (`:72`); meta — `rounded border border-slate-800 bg-slate-950/40 p-2 font-mono text-[10px] text-slate-400` (`:76`).
- Панель «Результат»: та же обёртка (`:111`); заголовок `text-xs font-semibold uppercase text-slate-500` (`:112`).
- Блок «Документ создан»: `mb-2 rounded border border-emerald-800 bg-emerald-950/40 px-2 py-1 text-xs text-emerald-300` (`:114`).
- Кнопка «Сохранить как новый документ»: `mb-2 rounded bg-indigo-600 px-2 py-1 text-xs text-white disabled:opacity-50` (`:120`).
- Markdown результата: `run-markdown text-sm text-slate-200` (`:128`).
- Плейсхолдер: `text-xs text-slate-500` (`:132`).
- Кнопки в `SkillsPanel` «В док» / «На экран»: `rounded bg-indigo-600 px-2 py-1 text-[11px] text-white disabled:opacity-50` и `rounded bg-slate-700 px-2 py-1 text-[11px] text-slate-200 disabled:opacity-50` (`:425, :433`).

Консистентность с существующим UI: те же `slate-800/900/950`, `border-slate-800`, `text-xs/text-[11px]`, `indigo-600` для primary, `emerald-800/950/300` для позитивного результата. Отклонений нет.

## Доступность (a11y)

Минимум для среза — без расширения относительно текущего кода. Всё перечисленное уже реализовано, регрессия не должна его ломать:

- Кнопки в `RunView` — обычные `<button type="button">` (не `role="button"`): «← К чату», «Стоп», «Сохранить как новый документ». Семантика `<button>` + текстовая подпись дают корректное имя для AT.
- Бейдж статуса — `<span>` с текстом `run.status` uppercase. Дублирования через `aria-label` нет, но текстовое содержимое читается.
- Блок «Документ создан» — `<p>`, текст доступен для AT.
- **Фокус:** при открытии `RunView` фокус остаётся в Layout (явной авто-фокусировки нет, как и раньше). Кнопка «← К чата» первой в header-секции доступна через Tab. После save кнопка пропадает, фокус возвращается в естественный порядок (на следующий кликабельный элемент или document body) — текущее поведение, без изменений.
- **Клавиатура:**
  - Tab — естественный порядок: «← К чата» → «Стоп» (если есть) → (внутри `SkillsPanel`/прочих) … → «Сохранить как новый документ» (если видна).
  - Enter на кнопке save — триггерит `onClick` (нативное поведение `<button>`).
  - Escape — не обрабатывается явно в `RunView`; закрывает listbox-ы, если открыты (в `SkillsPanel`/`Chat`).
- **Контраст** — без новых пар; `slate-100/200/300` на `slate-800/900/950`, `emerald-300` на `emerald-950/40`, `indigo-600` с `text-white` — все прошли визуальный приём в CATALOG-16/18.
- Дежурное: `disabled={savingResult}` на кнопке save + `disabled={run.cancelling}` на «Стоп» — блокируют повторные срабатывания.

## Контракты данных (если нужны)

Без изменений. Перечислено как контракт для end-to-end-приёмки:

- `RunView` получает `run: UseRunStreamResult`, `runId: string | null`, `documents: DocumentOut[]`, `onSaveResult: (runId: string) => void`, `savingResult: boolean`, `savedDoc: DocumentOut | null`.
- `UseRunStreamResult` (`useRunStream.ts:41-54`): `outputDocId: string | null` — выставляется finish-фреймом через `setOutputDocId(e.output_doc_id)` **только если поле присутствует** (`:170`). Источник — WS-стрим бэка.
- WS finish-фрейм (`ServerEvent.finish`): `{ type: 'finish', status?: string, output_doc_id?: string, result_text?: string }`. Для `persist` — `output_doc_id` присутствует, `result_text` опционально. Для `preview` — `output_doc_id` отсутствует, `result_text` есть.
- `saveRunResult(runId): Promise<DocumentOut>` (`App.tsx:206`) — POST-вызов на бэк, возвращает созданный документ. Используется только для preview-режима (через кнопку save).
- `SkillsPanel` `onApply(skillId, docIds, 'persist' | 'preview')` — контракт не меняется (см. CATALOG-39).
- `App.tsx` `setSavedResultDoc(null)` в `handleApply` (`:190`) — инвариант: каждый новый прогон начинается с чистого `savedResultDoc`, иначе `outputDocId` «протекает» между прогонами.

Дизайн **не вводит** новых типов, эндпоинтов или WS-контрактов. Весь UI-контракт остаётся как в CATALOG-18 (введение save-кнопки) + CATALOG-28 (фикс `DocumentCombobox`) + CATALOG-16 (meta/run view).

## Критерии визуальной приёмки

- [ ] **Слоты `SkillsPanel` активируют кнопки** для всех трёх `input_arity` (`1`, `2`, `null`) после выбора документа(ов) — регрессия CATALOG-28/39 (симптом 1 не воспроизводится).
- [ ] **E2E-1 (persist):** клик «В док» открывает `RunView`; после finish в правой колонке показан блок «Документ создан: «<title>»», кнопка «Сохранить как новый документ» **скрыта**; новый документ появляется в списке документов.
- [ ] **E2E-2 (preview):** клик «На экран» открывает `RunView`; после finish кнопка «Сохранить как новый документ» **видна** (indigo, активна); блока «Документ создан» нет.
- [ ] **E2E-2 (save flow):** клик по кнопке save переводит её в состояние «Сохраняю…» (`disabled`), после ответа — кнопка скрывается, появляется блок «Документ создан: «<title>»», документ попадает в список и становится активным.
- [ ] **E2E-3 (DocumentCombobox regression):** выбор в single/multi-слотах `SkillsPanel` не блокируется, клик по option доходит до `onChange`; composer чата (CATALOG-28) также работает.
- [ ] **E2E-4 (повторные прогоны):** после preview+save и запуска нового прогона (любой режим) — новый `RunView` не показывает блок «Документ создан» от прошлого save (`savedResultDoc` сброшен в `handleApply`).
- [ ] **`run.status='error'`:** кнопка save **не показывается** (даже при наличии `resultText`); бейдж статуса красный; в ленте показан `run.error`.
- [ ] **Прогон без `resultText`:** после finish с пустым `resultText` кнопка save **не показывается**; в правой колонке текст «Нет текстового результата.»
- [ ] **WS закрылся до finish:** amber-предупреждение «Соединение закрыто» в левой колонке; `run.finished=false`; кнопка save **не показывается**.
- [ ] **Persist без `output_doc_id` от бэка (аномалия):** фронт честно показывает кнопку save (fallback CATALOG-18). Зафиксировать как наблюдение, но не блокер приёмки этого шага (бэк-проблема — отдельный план).
- [ ] **Preview c ошибочно присланным `output_doc_id` (аномалия):** фронт честно скрывает кнопку save и показывает «Документ создан». Зафиксировать как блокер; эскалировать в backend-план.
- [ ] **Save с ошибкой сети/бэка:** кнопка возвращается в активное состояние, `notice` показывает сообщение об ошибке; пользователь может повторить клик.
- [ ] **Визуал без регрессий:** `RunView` header/бейджи/кнопки/блок «Документ создан»/`ReactMarkdown`-результат соответствуют контрольным Tailwind-классам выше; `SkillsPanel` кнопки «В док» / «На экран» без изменений.
