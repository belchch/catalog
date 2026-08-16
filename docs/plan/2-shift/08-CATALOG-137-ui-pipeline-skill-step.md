# CATALOG-137 — ui: шаг skill в панели STEPS и вложенный запуск в трейсе

- **Задача Plane:** [CATALOG-137](https://app.plane.so/belchch/projects/catalog-app/work-items/137) (id: `0d2424ab-7cc9-4ebe-b1b1-3c0b81b01b22`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 08 · blocked_by CATALOG-136
- **Цель:** Шаг `skill` виден в STEPS (бейдж, имя, пин) без подсказок «нужен код/промпт»; вложенный запуск раскрывается в трейсе без регрессии дерева.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

После рантайма шага `skill` (CATALOG-136).

1. `StepsList.tsx`: три типа, бейдж SKILL; в «подробнее» — имя, `kind`, короткий `config_hash`.
2. `api.ts`: `PipelineStepType` и `PipelineStepDraft` — третий тип и новые поля; `normalizePipelineStep` терпит шаги без них.
3. Подсказки в `ArtifactsPanel`: PROMPT для pipeline — промпт первого пустого llm-шага, не «нужен промпт» на skill-шаге.
4. Трейс: вложенный запуск — `TraceRunNode` + `foldNestedRuns` (CATALOG-119/129); имя, глубина, цена.
5. Карточка скилла / `ArtifactSummaryCard`: счётчик и готовность не ломаются на шаге без `code` и `system_prompt`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/2-shift/07-CATALOG-136-code-pipeline-skill-runtime.md` (событие трейса).

- `frontend/src/components/StepsList.tsx:38-39,49` — тернарник script/llm; skill уйдёт в ветку «промпт не задан».
- `frontend/src/api.ts:597-611,650-666` — `PipelineStepType = 'script' | 'llm'`; неизвестный type становится `script`.
- `frontend/src/components/ArtifactsPanel.tsx:727` — placeholder «System prompt скилла…».
- `frontend/src/components/ArtifactSummaryCard.tsx:28-35` — готовность steps = валидный JSON с ≥1 шагом; prompt/script считаются отдельно.
- `frontend/src/components/TraceSteps.tsx` / `frontend/src/lib/traceSegments.ts:362` — `TraceRunNode`, `foldNestedRuns`.

## Затрагиваемые файлы
- `frontend/src/api.ts` — тип, поля, нормализация.
- `frontend/src/components/StepsList.tsx` — бейдж SKILL и подробности.
- `frontend/src/components/ArtifactsPanel.tsx` — подпись PROMPT для pipeline.
- `frontend/src/components/ArtifactSummaryCard.tsx` — готовность с skill-шагами.
- `frontend/src/components/TraceSteps.tsx` / `traceSegments.ts` — узел вложенного запуска шага.
- Тесты StepsList / TraceRunNode / normalize.

## План действий
1. Расширить типы; `normalizePipelineStep` не кастит `skill` в `script`.
2. STEPS: бейдж, имя, kind, короткий пин; без «нужен код/промпт».
3. Пояснить PROMPT в pipeline; skill-шаг не требует промпта.
4. Трейс: переиспользовать fold/node; состояния загрузки/не найден/повторить на месте.
5. Готовность черновика не требует code/prompt у skill-шага.
6. Только токены `docs/ui-style-guide.md`.

## Критерии приёмки (Definition of Done)
- [ ] Шаг `skill` в STEPS с бейджем, именем и пином.
- [ ] Нет подсказок «нужен код» / «нужен промпт» на skill-шаге.
- [ ] Счётчик шагов и готовность черновика работают.
- [ ] Вложенный запуск раскрывается в трейсе; дерево 119/129 без регрессии.
- [ ] Дизайн-спека и визуальные критерии выполнены.
- [ ] `pnpm run build`, `lint`, `typecheck`, `test` из `frontend/`.
