# CATALOG-128 — ToolsPopover: включить agent и pipeline, показать цену скилла

- **Задача Plane:** [CATALOG-128](https://app.plane.so/belchch/projects/catalog-app/work-items/128) (id: `9d17a9db-6361-4456-be54-a445f71f1eda`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 07 · blocked_by CATALOG-127
- **Цель:** Свичи активны у всех трёх `kind`. В строке скилла видна цена с бэкенда. Заблокированная кнопка инструментов объясняет, почему она серая.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: ui. После CATALOG-127.

1. Убрать `!isScript` из `switchDisabled` — остаётся `pending`.
2. Удалить `SCRIPT_ONLY_HINT` и связанный title.
3. Оценка стоимости в строке: script — «без LLM»; agent/pipeline — «до N LLM-вызовов». N из `SkillOut`, формулу во фронте не дублировать.
4. `guaranteeLine(skill.kind)` — про гарантию и цену, не про запрет.
5. Обновить `ToolsPopover.test.tsx:158-175`.
6. `Chat.tsx:409`: живой `title` — «Отправьте сообщение, чтобы начать сессию» / «Идёт генерация».

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/1-shift/06-CATALOG-127-code-agent-pipeline-session-tools.md` добавляет цену в `SkillOut`.

- `frontend/src/components/ToolsPopover.tsx:5` — `SCRIPT_ONLY_HINT`.
- `frontend/src/components/ToolsPopover.tsx:30-33` — `guaranteeLine` говорит «не вызывается как инструмент».
- `frontend/src/components/ToolsPopover.tsx:91-92,131-132` — свич только для script.
- `frontend/src/api.ts` — `SkillOut` без поля цены (появится в 127).
- `frontend/src/components/Chat.tsx:409` — `disabled={streaming || !sessionId}`, title статичный.

Токены — `docs/ui-style-guide.md`.

## Затрагиваемые файлы
- `frontend/src/api.ts` — поле цены на `SkillOut`.
- `frontend/src/components/ToolsPopover.tsx` — свичи, цена, `guaranteeLine`.
- `frontend/src/components/ToolsPopover.test.tsx` — новое поведение.
- `frontend/src/components/Chat.tsx` — живой title кнопки инструментов.

## План действий
1. Пробросить поле цены из API в строку скилла.
2. Свич: disabled только `pending`.
3. Удалить script-only hint; обновить `guaranteeLine`.
4. Title кнопки в Chat по `!sessionId` / `streaming`.
5. Поправить тесты, которые закрепляют старый запрет.

## Критерии приёмки (Definition of Done)
- [ ] Свичи активны у agent/script/pipeline; блокирует только pending.
- [ ] У agent и pipeline видна оценка стоимости до прикрепления.
- [ ] Серая кнопка гаечного ключа объясняет причину.
- [ ] Только токены/примитивы из `docs/ui-style-guide.md`.
- [ ] `pnpm run build`, `lint`, `typecheck`, `test` из `frontend/`.
