# CATALOG-119 — UI: дерево трейса для вложенных вызовов скиллов

- **Задача Plane:** [CATALOG-119](https://app.plane.so/belchch/projects/catalog-app/work-items/119) (id: `94d73a20-b0c3-403f-a9f6-c2208b98177d`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 05 · blocked_by CATALOG-117
- **Цель:** Трейс сессии показывает дерево по `parent_run_id`: основной запуск → вызовы скиллов → их verify. Узел раскрывается (вход, результат, причина провала).

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: ui. Шаг 6 из 7. Зависит от CATALOG-117.

- Отдавать `parent_run_id` и дочерние запуски в API (`schemas.py`, `repo_run.py`, `api/runs.py`) и в `frontend/src/api.ts`.
- `traceSegments.ts` / `TraceSteps.tsx`: сейчас плоско по `step_id`; нужна вложенность по `parent_run_id`.

Токены: `docs/ui-style-guide.md`. Референс: `backup-pre-revert-0234`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/day-shift/03-CATALOG-117-code-skill-as-tool.md` (`parent_run_id` в БД и запись при вызове).

- `frontend/src/lib/traceSegments.ts:7-22` — `segmentTraceSteps` группирует подряд идущие шаги с одним `stepId`.
- `frontend/src/components/TraceSteps.tsx` — рендер flat/group.
- `frontend/src/components/TraceSteps.test.ts` — плоскость.
- API запусков ещё не отдаёт дерево детей (колонка появится в 117).

Небольшой backend-хвост (отдать поле в JSON) допустим в этом UI-шаге, если 117 записал колонку, но не прокинул её в response.

## Затрагиваемые файлы
- `backend/catalog/api/schemas.py`, `backend/catalog/storage/repo_run.py`, `backend/catalog/api/runs.py` — `parent_run_id` + children.
- `frontend/src/api.ts` / `frontend/src/hooks/useRunStream.ts` — типы.
- `frontend/src/lib/traceSegments.ts` — дерево.
- `frontend/src/components/TraceSteps.tsx` — раскрываемый узел.
- `frontend/src/components/TraceSteps.test.ts` — вложенность.

## План действий
1. Прокинуть `parent_run_id` и список дочерних run в API, если 117 этого не сделал.
2. Заменить плоскую группировку на дерево: корень = run без parent, дети по `parent_run_id`.
3. Узел: вход, результат, verify failures; раскрытие.
4. Тесты сегментации: вложенный вызов не сливается в плоский `tool_result`.

## Критерии приёмки (Definition of Done)
- [ ] Вызов скилла раскрывается в дочерний запуск с шагами и verify.
- [ ] Плоский `tool_result` без дерева — не считается готовым.
- [ ] Только токены style guide.
- [ ] `pnpm run build`, `lint`, `typecheck`, `test`; backend тесты если менялся API.
