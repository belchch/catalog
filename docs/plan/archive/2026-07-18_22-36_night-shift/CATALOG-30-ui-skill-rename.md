# CATALOG-30 — Редактирование имени скила (UI)

- **Задача Plane:** [CATALOG-30](https://app.plane.so/belchch/projects/catalog-app/work-items/30) (id: `04bacb19-c59b-45b2-8638-991405998716`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Предпосылки:** `CATALOG-30-code-skill-rename.md`
- **Цель:** Поле имени в модалке сохранения; редактирование имени у сохранённых скилов в панели.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Имя скила можно править при сохранении и редактировать у сохранённых скилов.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- `SkillSettingsModal.tsx:80` — имя read-only.
- `SkillsPanel.tsx:54` — имя как `<span>`, без inline edit.

## Затрагиваемые файлы

- `frontend/src/components/SkillSettingsModal.tsx` — input имени → configure.
- `frontend/src/api.ts` — проброс `name` / rename helper.
- `frontend/src/components/SkillsPanel.tsx` — edit имени (input + save) для списка.
- `frontend/src/hooks/useSkills.ts` — вызов rename/refresh.

## План действий

1. Модалка: editable name, уходит в configure.
2. Панель: действие «переименовать» или inline edit для committed/draft.
3. После save — обновить список.

## Критерии приёмки (Definition of Done)

- [ ] При сохранении скила имя можно изменить в модалке.
- [ ] У сохранённого скила имя можно отредактировать в UI.
- [ ] `pnpm run build/lint/typecheck` зелёные.
