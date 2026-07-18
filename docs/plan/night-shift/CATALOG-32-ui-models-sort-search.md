# CATALOG-32 — Сортировка и поиск моделей

- **Задача Plane:** [CATALOG-32](https://app.plane.so/belchch/projects/catalog-app/work-items/32) (id: `8f5918e1-eb82-4eb4-89f0-60892954fc53`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** Удобный выбор модели: алфавитная (или стабильная) сортировка + поиск/фильтр по списку.

## Постановка задачи (актуальное ТЗ)
_(источник: название задачи; описание пустое)_

Список моделей не отсортирован и нет поиска. Неудобно искать.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- `ModelSelector.tsx:32-60` — сырой `<select>`, порядок as-is с API.
- `SkillSettingsModal.tsx:99-115` — тот же паттерн.
- Backend `list_models` не сортирует — `openai_compatible.py` / `models.py`.

## Затрагиваемые файлы

- `frontend/src/components/ModelSelector.tsx` — sort + search filter.
- `frontend/src/components/SkillSettingsModal.tsx` — тот же UX для выбора модели.
- Опционально shared helper `sortAndFilterModels`.

## План действий

1. Сортировать модели по `name`/`id` перед рендером.
2. Поле поиска, фильтрующее options (или combobox вместо голого select).
3. Применить в ModelSelector и в модалке настроек скила.
4. Ручная проверка на длинном каталоге OpenRouter.

## Критерии приёмки (Definition of Done)

- [ ] Список моделей отсортирован предсказуемо.
- [ ] Есть поиск/фильтр по имени или id.
- [ ] Работает в селекторе настроек приложения и в модалке скила.
- [ ] `pnpm run build/lint/typecheck` зелёные.
