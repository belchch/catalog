# CATALOG-26 — Удаление скила (UI)

- **Задача Plane:** [CATALOG-26](https://app.plane.so/belchch/projects/catalog-app/work-items/26) (id: `b3916b33-ba95-4b77-a929-4559e6de6d9e`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Предпосылки:** `CATALOG-26-code-delete-skill.md`
- **Цель:** Кнопка удаления скила в панели с подтверждением.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Сделать функцию удаления скила.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- `SkillsPanel.tsx` — edit/commit/apply, без delete.
- `useSkills.ts` / `api.ts` — нет `deleteSkill`.

## Затрагиваемые файлы

- `frontend/src/api.ts` — `deleteSkill`.
- `frontend/src/hooks/useSkills.ts` — метод delete + refresh.
- `frontend/src/components/SkillsPanel.tsx` — кнопка + confirm.

## План действий

1. Клиент `DELETE /skills/{id}`.
2. Кнопка «Удалить» (draft и committed) с `confirm`.
3. После успеха — обновить список.

## Критерии приёмки (Definition of Done)

- [ ] Из UI можно удалить скил; он исчезает из списка.
- [ ] Есть подтверждение перед удалением.
- [ ] `pnpm run build/lint/typecheck` зелёные.
