# CATALOG-57 — Бесконечный HTTP-refresh документов после завершения run

- **Задача Plane:** [CATALOG-57](https://app.plane.so/belchch/projects/catalog-app/work-items/57) (id: `9e901535-c470-4f94-8ab5-9cbbd8ce1294`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** Убрать петлю `GET /documents` + `GET /sessions/{id}/documents` после `run.finished`: эффект должен сработать **один раз на run**, зависимости — стабильные (`docs.refresh`), не весь объект `docs`.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи)_

После успешного run фронт уходит в петлю запросов `GET /documents` и `GET /sessions/{id}/documents`.

**Причина:** в `App.tsx` эффект после `run.finished` зависит от всего объекта `docs` (`useDocuments()`). Объект новый на каждый рендер → `docs.refresh()` / `refreshSessionDocuments()` → setState → снова эффект, пока `run.finished === true`.

**Фикс:** в deps — стабильный `docs.refresh` (и аналогично остальные), не весь `docs`.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

- `useDocuments()` возвращает новый object literal каждый рендер (`useDocuments.ts:40`), хотя `refresh` стабилен через `useCallback` (`:18-28`).
- Working tree уже содержит черновик фикса (`App.tsx:71-87`):
  - `const docsRefresh = docs.refresh`
  - `handledRunFinishRef` — once per `activeRunId`
  - deps: `[run.finished, run.status, run.outputDocId, activeRunId, docsRefresh, refreshSessionDocuments]`
- Session docs также приходят по WS (`session_docs`); flood — баг deps, не polling.

Если фикс уже в ветке — задача сводится к **довести/проверить** и закрыть DoD; не изобретать второй механизм.

## Затрагиваемые файлы

- `frontend/src/App.tsx` — эффект после finish run (стабильные deps + once-guard)
- При необходимости: `frontend/src/hooks/useDocuments.ts` — не возвращать новый object без нужды (опционально, не обязательно если deps уже на `refresh`)
- `frontend/src/hooks/usePlannerSession.ts` — убедиться, что `refreshSessionDocuments` стабилен

## План действий

1. **Проверить текущий `App.tsx`.** Если фикс уже есть — не откатывать; убедиться, что `docs` не в deps и есть once-per-run guard.
2. **Стабильность колбэков.** `refreshSessionDocuments` / `docs.refresh` — `useCallback` с корректными deps.
3. **Ручная проверка.** Успешный run с `outputDocId`: в Network / backend-логе **один** (или малый константный) refresh, не сотни. Повторный run с новым id — снова один refresh.
4. **Регрессия.** Upload документа и смена сессии по-прежнему обновляют списки.
5. **Проверки.** lint/typecheck/build.

## Критерии приёмки (Definition of Done)

- [ ] После `run.finished` нет бесконечной петли HTTP на `/documents` и session documents.
- [ ] В deps эффекта нет нестабильного объекта `docs`.
- [ ] Refresh библиотеки документов при успешном run с новым output — ровно один раз на `activeRunId`.
- [ ] `frontend/`: `pnpm run lint`, `typecheck`, `build` зелёные.
- [ ] Ручная проверка: backend-лог не забит сотнями одинаковых 200 OK после одного run.
