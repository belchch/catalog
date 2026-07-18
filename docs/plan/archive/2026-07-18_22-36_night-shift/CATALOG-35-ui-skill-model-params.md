# CATALOG-35 — Параметры модели в скиле (UI)

- **Задача Plane:** [CATALOG-35](https://app.plane.so/belchch/projects/catalog-app/work-items/35) (id: `1877d641-2893-422a-88d0-024c5895adc7`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Предпосылки:** `CATALOG-35-code-skill-model-params-api.md`
- **Цель:** На карточке скила показывать провайдер, модель, рассуждения.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

У скила нужно отображать также параметры — провайдер, модель, рассуждения.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- `SkillsPanel.tsx:49-83` — name/description/tags/status; параметров модели нет.
- Данные появятся в `SkillOut` из code-плана.

## Затрагиваемые файлы

- `frontend/src/api.ts` — поля в `SkillOut`.
- `frontend/src/components/SkillsPanel.tsx` — компактный вывод provider/model/reasoning.

## План действий

1. Расширить тип `SkillOut`.
2. Рендер параметров на карточке (без карточного шума — одна строка метаданных).
3. Для script-скилов без модели — не показывать пустые поля или показать «—».

## Критерии приёмки (Definition of Done)

- [ ] В списке скилов видны provider, model, reasoning (если заданы).
- [ ] `pnpm run build/lint/typecheck` зелёные.
