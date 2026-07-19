# CATALOG-57 — Дизайн UI

- **Источник:** docs/plan/next-shift/CATALOG-57-ui-stop-docs-refresh-loop.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

После успешного apply-скилла (run доходит до `finished`) пользователь остаётся на том же экране: боковая панель «Документы», RunView, чат/артефакты — **без новых контролов и без смены layout**. Ожидаемое поведение:

1. Завершается run (`run.finished === true`).
2. Список документов библиотеки и session documents обновляются **один раз на данный `activeRunId`** (HTTP `GET /documents` и/или `GET /sessions/{id}/documents` — не в петле).
3. При `status === 'ok'` и наличии `outputDocId` новый/обновлённый документ появляется в списке «Документы» (и при необходимости в session docs); RunView по-прежнему показывает «Документ создан…».
4. Повторный apply с **новым** run id снова даёт ровно один refresh-цикл; повторные рендеры при `finished === true` не дергают API снова.

Визуально экран не меняется по структуре — меняется только отсутствие «мигания» loading и flood-запросов после одного run.

## Дерево компонентов и файлы

Новых компонентов и зависимостей нет. Скоуп — поведение эффекта и стабильность колбэков.

- `frontend/src/App.tsx` — эффект после `run.finished`: deps только на стабильные колбэки (`docsRefresh` / `docs.refresh`, `refreshSessionDocuments`) и скаляры run/session; once-guard на `activeRunId` (`handledRunFinishRef`). **Не** класть весь объект `docs` в deps этого эффекта.
- `frontend/src/hooks/useDocuments.ts` — опционально: не менять UI-контракт; `refresh` остаётся стабильным `useCallback`. Мемоизация всего return-object не обязательна, если эффект не зависит от `docs`.
- `frontend/src/hooks/usePlannerSession.ts` — `refreshSessionDocuments` остаётся стабильным `useCallback` (deps: `sessionId`); UI-панели session docs без изменений разметки.
- `frontend/src/components/DocumentList.tsx`, `RunView.tsx`, панели сессий — **без** изменений layout/копирайта в этом шаге.

Не вводить polling, debounce-UI, toast «документы обновлены» или отдельные индикаторы «sync после run».

## Layout и состояния

**Layout:** без изменений относительно текущего `App` (header → notice → grid: aside с CollapsibleSection «Документы» / `DocumentList` + main с RunView при активном run).

**Поведенческие состояния после finish run (не новые экраны):**

| Состояние | Что видит пользователь | HTTP / эффект |
|-----------|------------------------|---------------|
| **run finished, ok + outputDocId** | Краткий (не более одного цикла) `docs.loading` на кнопке «Обновить» в секции Документы (`…` → «Обновить`); список может один раз перерисоваться с новым doc; RunView — блок «Документ создан…» | Один вызов `docs.refresh` + один `refreshSessionDocuments` на этот `activeRunId` |
| **run finished, без outputDocId / не ok** | Layout как сейчас; session docs могут один раз освежиться | Только `refreshSessionDocuments` один раз на `activeRunId`; библиотечный `docs.refresh` **не** вызывать |
| **run finished, повторный render** | Нет повторного мигания «…» на кнопке Обновить из-за того же finish | Эффект no-op: `handledRunFinishRef.current === activeRunId` |
| **новый run (новый activeRunId)** | Как первая строка таблицы для нового finish | Guard сбрасывает смысл по id: снова ровно один refresh-цикл |
| **loading / empty / error списка** | Как до шага: `DocumentList` / кнопка «Обновить» / `docs.error` без новых empty/error баннеров для post-run sync | Ошибки refresh не обязаны показывать отдельный notice; не раздувать UI |

Session docs по-прежнему могут приходить по WS (`session_docs`) — это не замена once-guard и не источник петли; петля — только из нестабильных deps эффекта.

## Взаимодействия

- **Авто-refresh после finish** — единственное целевое взаимодействие шага; пользователь ничего не кликает для синхронизации после успешного run с output.
- **Ручное «Обновить»** в секции Документы — без изменений: `docs.refresh()`, disabled при `docs.loading`.
- **Upload документа** — по-прежнему обновляет список (через `upload` / существующий путь); не ломать.
- **Смена / создание сессии** — session documents обновляются как сейчас (hydrate / WS / `refreshSessionDocuments`); не ломать.
- **Save result** (`handleSaveResult`) — отдельный путь: явный `docs.refresh` + `refreshSessionDocuments` после сохранения; не смешивать с once-guard finish-эффекта (guard только для эффекта `run.finished`).
- **Крайние случаи:**
  - `activeRunId` сменился до `finished` — guard привязан к id; старый finish не должен повторно дергать refresh после смены.
  - `run.finished` true при ремаунте с тем же id — допустимо один refresh при первом проходе эффекта; не цикл.
  - Параллельные рендеры при streaming → finished: один проход с записью в ref до вызова refresh.

Клавиатура, фокус, навигация панелей — без изменений.

## Стиль и токены

Без новых стилей и токенов. Сохранить существующие утилиты секции Документы:

- Кнопка «Обновить»: `rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-50`.
- Loading-лейбл кнопки: `…` при `docs.loading` (как сейчас).
- Не добавлять спиннеры, progress bars, badge «обновлено», glow/indigo акценты для sync.

Единственный допустимый визуальный артефакт фикса — отсутствие непрерывного чередования «Обновить» ↔ «…» после одного finished run.

## Доступность (a11y)

- Не менять роли/aria существующих контролов.
- Кнопка «Обновить» остаётся обычной `button`; при кратком `disabled` во время одного refresh фокус не обязан переноситься.
- Не вводить live region специально для post-run sync (избежать шума screen reader при каждом refresh).
- Контраст и фокус-кольца — как в текущей aside-панели.

## Контракты данных (если нужны)

Эффект в `App.tsx` (контракт поведения):

```ts
// deps: run.finished, run.status, run.outputDocId, activeRunId,
//       docsRefresh (= docs.refresh), refreshSessionDocuments
// once: handledRunFinishRef keyed by activeRunId
// if finished && activeRunId && not yet handled:
//   if status === 'ok' && outputDocId → docsRefresh()
//   always → refreshSessionDocuments()
```

API без изменений схемы:

- `GET /documents` — через `docs.refresh` / `listDocuments`
- `GET /sessions/{id}/documents` — через `refreshSessionDocuments` / `getSessionDocuments`
- Run stream: `finished`, `status`, `outputDocId` из `useRunStream`
- WS `session_docs` — существующий путь; не polling

Опциональная стабилизация return `useDocuments()` не меняет контракт `UseDocumentsResult` для `DocumentList`.

## Критерии визуальной приёмки

- [ ] После одного `run.finished` кнопка «Обновить» в секции Документы не мигает `…` / «Обновить» в бесконечном цикле; layout панелей без новых элементов.
- [ ] При успешном run с `outputDocId` документ появляется в списке (или список согласован с API) без повторных визуальных «штормов» перезагрузки.
- [ ] Повторный apply (новый run) снова даёт не более одного краткого цикла loading на кнопке Обновить, связанного с авто-refresh.
- [ ] Ручное «Обновить», upload и смена сессии визуально/функционально работают как до шага.
- [ ] RunView / копирайт «Документ создан…» и остальной chrome `App` не переработаны ради этого фикса.
)
