# CATALOG-84 — Pipeline-скилы: движок + создание из чата (этап 1)

- **Задача Plane:** [CATALOG-84](https://app.plane.so/belchch/projects/catalog-app/work-items/84) (id: `b8fb8b18-86c4-4c4c-a6f8-aef9296e0ebb`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 04 · предусловие: 03 (code того же тикета)
- **Цель:** Показать pipeline как структуру: артефакт `steps` в панели черновика и группировка ленты прогона по `step_id`. Модалка настроек модели на шаге — вне scope.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

UI-часть этапа 1: `RunView` рисует шаги как структуру; создание из чата видно в панели артефактов (`steps`). Переопределение модели в модалке — не делать.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/2-shift/03-CATALOG-84-code-pipeline-engine.md` — события с `step_id`, артефакт типа `steps`, `kind=pipeline`.

Сейчас `ArtifactType` / карточка только `meta | prompt | script` (`frontend/src/components/ArtifactSummaryCard.tsx:11-17`). `ArtifactsPanel` `SkillKind = 'agent' | 'script'` (`ArtifactsPanel.tsx:9`, `KIND_OPTIONS:40-43`); prompt гасится для script и наоборот (`:339-340`). `TraceSteps` плоский список без группировки (`TraceSteps.tsx:39-46`). `RunStep` в `useRunStream.ts:18` — проверить поле `step_id` после backend.

## Затрагиваемые файлы
- `frontend/src/api.ts` — `ArtifactType` += `steps`; типы meta kind.
- `frontend/src/components/ArtifactSummaryCard.tsx` — четвёртый тип.
- `frontend/src/components/ArtifactsPanel.tsx` — kind `pipeline`, секция steps (readonly JSON или список id/type), не гасить prompt/script слепо.
- `frontend/src/hooks/useRunStream.ts` — прокинуть `stepId` из событий.
- `frontend/src/components/TraceSteps.tsx` / `RunView.tsx` — группы по шагу pipeline (заголовок id + вложенные script/llm события).

## План действий
1. Расширить типы артефакта и kind.
2. Карточка саммари: `steps` виден, когда артефакт есть.
3. Панель: при `kind=pipeline` показать блок шагов; prompt/script не помечать нерелевантными только из-за верхнего kind.
4. Лента: если у событий есть `stepId` — секции «шаг {id}»; иначе плоский список (agent/script без регрессии).
5. Не трогать модалку настроек скила. Проверки frontend.

## Критерии приёмки (Definition of Done)
- [ ] Артефакт `steps` виден в саммари и панели после `save_skill_steps`.
- [ ] `kind=pipeline` выбирается/отображается в meta.
- [ ] Прогон pipeline в `RunView` группирует события по шагам; agent/script лента без регрессии.
- [ ] Зелёные: `pnpm run build`, `lint`, `typecheck`, `test` из `frontend/`.
