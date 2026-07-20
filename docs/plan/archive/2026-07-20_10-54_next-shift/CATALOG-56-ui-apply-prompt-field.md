# CATALOG-56 — Промпт параметр для скила типа AI

- **Задача Plane:** [CATALOG-56](https://app.plane.so/belchch/projects/catalog-app/work-items/56) (id: `25b3557d-4d22-4b0b-9bd7-106755a44719`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** В панели скиллов для AI (`kind`/tag agent) показать необязательное поле «Промпт» и передавать его в apply. Для PYTHON/script — скрыть. Предусловие: `CATALOG-56-code-apply-runtime-prompt.md`.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи)_

Доп. раздел — Промпт. Только для скилла типа AI. Для PYTHON не нужно. Необязательный промпт для коррекции работы готового скилла.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

Apply UI: `SkillsPanel.tsx` — выбор документов + кнопки persist/preview (`:423-439`). `onApply(skillId, docIds, mode)` → `App.handleApply` → `skillsHook.apply` → `api.applySkill` (`api.ts:210+`) — body сейчас `{ doc_ids, persist, session_id }`.

Теги AI/python: `SkillsPanel.tsx` (~267+), `kind`/`tags` на skill.

## Затрагиваемые файлы

- `frontend/src/components/SkillsPanel.tsx` — textarea «Промпт» для AI; state per skill или общий draft
- `frontend/src/api.ts` — `applySkill(..., prompt?: string)`
- `frontend/src/hooks/useSkills.ts` — прокинуть prompt
- `frontend/src/App.tsx` — сигнатура `handleApply` / `onApply`

## План действий

1. **Поле UI.** Для карточки/блока AI-скилла — textarea «Промпт» (placeholder про уточнение). Для script — не рендерить.
2. **Прокинуть в apply.** Расширить `onApply` / `applySkill` optional `prompt`; слать в JSON только если непустой.
3. **UX.** Поле не блокирует apply пустым; значение можно очистить между запусками (локальный state).
4. **Проверки.** lint/typecheck/build; ручной: AI с промптом → run учитывает; script — поля нет.

## Критерии приёмки (Definition of Done)

- [ ] У AI-скилла видно необязательное поле «Промпт».
- [ ] У PYTHON/script поля нет.
- [ ] Непустой промпт уходит в `POST apply`.
- [ ] Пустой промпт не ломает apply.
- [ ] `frontend/`: `pnpm run lint`, `typecheck`, `build` зелёные.
- [ ] Соответствие дизайн-спеке UI-шага.
