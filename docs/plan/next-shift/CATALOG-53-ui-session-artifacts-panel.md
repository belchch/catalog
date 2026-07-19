# CATALOG-53 — Скрипт и prompt хранить отдельным артефактом и показывать в чате

- **Задача Plane:** [CATALOG-53](https://app.plane.so/belchch/projects/catalog-app/work-items/53) (id: `cd4eaadf-fbca-47c5-a732-7748b87dcd07`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** Панель-канвас артефактов сессии (prompt / script / meta): live из WS, ручное редактирование, понятные ошибки при build. Предусловие: code-план `CATALOG-53-code-session-artifacts.md`.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — часть Frontend)_

UI — панель-канвас справа от чата с inline-редактированием. Live-обновления по WS `session_artifacts`. Кнопка «Создать скилл» при 422 показывает, что дозаполнить в панели. Ручное сохранение блокируется на время streaming планировщика.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

Полное ТЗ и backend-часть — в описании Plane и в `CATALOG-53-code-session-artifacts.md`.

## Контекст

Сейчас правая область (`frontend/src/App.tsx` ~main): Chat **или** RunView. Prompt/code до build не видны; после build — только `SkillSettingsModal` без показа prompt/code (`SkillPreview` в schemas).

Паттерны:

- Session docs live: `usePlannerSession.ts` + WS `session_docs` (`ws.ts`)
- Settings UI: `SkillSettingsModal.tsx`
- Code display: `TraceSteps.tsx` (`<pre>`)

Backend API/WS должны уже существовать из code-шага: `GET/PATCH` artifacts, event `session_artifacts`.

## Затрагиваемые файлы

- `frontend/src/components/ArtifactsPanel.tsx` — **новый** канвас
- `frontend/src/App.tsx` — layout Chat + Artifacts (сплит/переключатель), wiring
- `frontend/src/hooks/usePlannerSession.ts` — state артефактов, WS frame, hydrate GET
- `frontend/src/ws.ts` — тип `session_artifacts`
- `frontend/src/api.ts` — get/patch artifacts, patch meta
- `frontend/src/components/Chat.tsx` — при необходимости связь с ошибкой build / подсветка

## План действий

1. **API + WS типы.** `getSessionArtifacts`, `patchArtifact`, `patchSkillMeta`; `ServerEvent` + обработка в `usePlannerSession`.
2. **ArtifactsPanel.** Секции prompt / script / meta; статусы `is_valid`/`error`/`source`; Save → PATCH; disabled при `streaming`.
3. **Layout.** Рядом с Chat: переключатель или сплит на широком экране (не ломая RunView).
4. **Hydration.** При смене `sessionId` — GET; во время диалога — WS updates.
5. **Build UX.** 422 → notice с указанием пустой/невалидной секции; подсветка нужного блока.
6. **Проверки.** lint / typecheck / build; ручной сценарий: tool сохранил prompt → панель обновилась → правка руками → build.

## Критерии приёмки (Definition of Done)

- [ ] Панель показывает текущие prompt/script/meta сессии.
- [ ] Live-обновление по WS при tool-save планировщика.
- [ ] Ручная правка сохраняется через PATCH; при streaming — заблокирована.
- [ ] Невалидный script показывает error; build не «висит» молча (понятный notice при 422).
- [ ] `frontend/`: `pnpm run lint`, `typecheck`, `build` зелёные.
- [ ] Соответствие дизайн-спеке UI-шага (`CATALOG-53.design.md` из pipeline).
