# CATALOG-118 — UI: поповер инструментов для выбора скиллов

- **Задача Plane:** [CATALOG-118](https://app.plane.so/belchch/projects/catalog-app/work-items/118) (id: `069f711f-8195-4c68-899b-d3be6a23a46c`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 04 · blocked_by CATALOG-116 · blocked_by CATALOG-117
- **Цель:** Иконка инструментов из CATALOG-116 открывает поповер: поиск, тумблеры, включённые сверху, бейджи ai/python, «Создать скилл» внизу. Attach/detach через REST CATALOG-117.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: ui. Шаг 5 из 7. Зависит от CATALOG-116 и CATALOG-117.

- Список-тумблеры: имя, описание, бейдж `ai`/`python` из `compute_tags`, шеврон в карточку скилла.
- Поиск сверху; включённые закреплены в начале; внизу «Создать скилл».
- Вместо «Auto · Medium» — `script` или «N проверок».
- Данные: `listSkills()` + эндпоинты `/sessions/{id}/tools` (или актуальный путь из 117).
- Состояние в `App.tsx`; кнопка/счётчик в `Chat.tsx`.

Токены: `docs/ui-style-guide.md`. Референс: `backup-pre-revert-0234`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловия: `docs/plan/day-shift/02-CATALOG-116-ui-composer-slim.md` (слот кнопки) и `docs/plan/day-shift/03-CATALOG-117-code-skill-as-tool.md` (REST).

- `frontend/src/api.ts` — `listSkills()` есть; клиентов attach session tools нет (добавить).
- `frontend/src/App.tsx` — нет `toolsOpen` / `sessionTools` (сняты revert'ом 79f5fef).
- `ToolsPopover.tsx` отсутствует — создать заново.
- `compute_tags` — искать в backend/frontend скиллов (карточка скилла уже показывает теги).

## Затрагиваемые файлы
- `frontend/src/components/ToolsPopover.tsx` — новый.
- `frontend/src/App.tsx` — загрузка, toggle attach/detach.
- `frontend/src/api.ts` — get/attach/remove session tools.
- `frontend/src/components/Chat.tsx` — открытие поповера, счётчик (слот 116).
- Тест поповера по возможности рядом с `Chat.test.tsx`.

## План действий
1. Клиент API под контракт CATALOG-117.
2. `ToolsPopover`: поиск, сортировка (enabled first), тумблеры, бейджи, гарантия, footer «Создать скилл».
3. Подключить к слоту CATALOG-116; счётчик = число прикреплённых.
4. Шеврон ведёт в существующую карточку скилла (тот же путь, что сайдбар).

## Критерии приёмки (Definition of Done)
- [ ] Поповер открывается с иконки композера.
- [ ] Тумблер прикрепляет/открепляет; счётчик совпадает.
- [ ] Поиск фильтрует; включённые сверху.
- [ ] Только токены style guide.
- [ ] `pnpm run build`, `lint`, `typecheck`, `test`.
