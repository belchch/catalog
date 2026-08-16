# CATALOG-121 — Verify: список всех проверок в трейсе

- **Задача Plane:** [CATALOG-121](https://app.plane.so/belchch/projects/catalog-app/work-items/121) (id: `04f9fdde-9114-4b0b-b6fe-08ff6e91ffb5`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 01 · предусловие: 00 (code того же тикета)
- **Цель:** В живом стриме и в сохранённом трейсе verify-шаг показывает полный список проверок: пройденные, упавшие с причиной, пропущенные. Старые трейсы без `checks` рендерятся как сейчас.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Frontend-часть CATALOG-121 (backend — парный `00-CATALOG-121-code-verify-check-outcomes.md`):

- `useRunStream.ts` (~142) и `traceSegments.ts` (`runTraceToSteps`, ~125): пробросить `checks` в шаг `verify`.
- `TraceSteps.tsx`: у verify-шага список всех проверок — зелёная строка, красная с причиной, приглушённая с пометкой skipped. Сводку «✓ проверки пройдены» заменить на «✓ N из M» с раскрываемым списком.
- Старые трейсы без `checks` — как сейчас.

DoD: в живом прогоне и при открытии сохранённого запуска виден список всех проверок со статусом.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: code-план того же тикета кладёт `checks` в WS и трейс.

Сейчас UI знает только сводку:

- `frontend/src/ws.ts:27-33` — `verify` без `checks`.
- `frontend/src/hooks/useRunStream.ts:137-149` — в шаг идут `passed`/`failures`.
- `frontend/src/lib/traceSegments.ts:124-136` — то же из сохранённого трейса.
- `frontend/src/components/TraceSteps.tsx:87-109` — упавшие `failures` одной строкой; пройденные не перечисляются.
- `frontend/src/components/TraceSteps.tsx:394-397` — сводка «проверки пройдены» / список failures у вложенного узла.

Токены и примитивы — только из `docs/ui-style-guide.md`.

## Затрагиваемые файлы
- `frontend/src/ws.ts` — тип `checks` в `verify`.
- `frontend/src/hooks/useRunStream.ts` — поле на `RunStep`.
- `frontend/src/lib/traceSegments.ts` — проброс из трейса.
- `frontend/src/components/TraceSteps.tsx` — список исходов + «N из M».
- `frontend/src/components/TraceSteps.test.ts` / `TraceRunNode.test.tsx` — новый рендер и fallback без `checks`.

## План действий
1. Добавить тип исхода проверки и опциональное `checks` в WS / `RunStep` / `runTraceToSteps`.
2. В `TraceSteps` для verify: заголовок «✓ N из M» (или «✗ N из M»), раскрываемый список; цвета — success/danger/faint.
3. Нет `checks` — прежний рендер (`failures` только при fail, без списка пройденных).
4. То же для вложенного узла запуска, если там сводка verify.
5. Тесты: полный список; skipped; старый трейс без `checks`.

## Критерии приёмки (Definition of Done)
- [ ] Живой стрим и сохранённый трейс показывают все проверки со статусом.
- [ ] Пройденные видны явно, упавшие — с причиной, пропущенные — с пометкой.
- [ ] Трейсы без `checks` не ломаются.
- [ ] Только токены/примитивы из `docs/ui-style-guide.md`.
- [ ] `pnpm run build`, `lint`, `typecheck`, `test` из `frontend/`.
