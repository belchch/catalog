# CATALOG-27 — UI: выбор трека операции перед сборкой скилла

- **Задача Plane:** [CATALOG-27](https://app.plane.so/belchch/projects/catalog-app/work-items/27) (id: `76fb7636-7660-4a86-8bc0-1ef07eee3e52`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** Перед `SkillSettingsModal` вставить шаг дизамбигуации: вызвать `proposeSkillTracks`, при >1 треке показать выбор (name + rationale), при 1 — авто-скип; записать выбранный трек user-сообщением в сессию и продолжить существующий build → settings. Edit-flow фазу A не запускает. Backend-контракт — в предусловии `CATALOG-27-code-skill-tracks-anti-domain.md`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Frontend-часть двухфазной сборки:

- `proposeSkillTracks` в `api.ts`, тип `SkillTrack`;
- шаг выбора трека **перед** `SkillSettingsModal` (модалка или кнопки в духе suggestions): при >1 — выбор, при 1 — авто-скип;
- отправка выбранного трека user-сообщением («Собери скилл по этой операции: …»), затем существующий build-флоу;
- Edit-flow (CATALOG-17): фаза A по умолчанию пропускается.

Критерии UI из ТЗ: однозначная сессия → ровно один трек, шаг выбора не показывается; сбой фазы A не блокирует сборку; edit не запускает фазу A.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

**Предусловие:** выполнен code-план `docs/plan/next-shift/CATALOG-27-code-skill-tracks-anti-domain.md` (`POST /sessions/{id}/skill-tracks`, тихая запись выбора, контракт skip/fallback).

Текущий UI-флоу создания скилла:

1. `Chat.tsx` → `onCreateSkill` (`~279–289`).
2. `App.tsx` `handleCreateSkill` (`249–273`): сразу `buildSkill(sessionId)` → `setSettingsSkill` → `SkillSettingsModal` (`537–549`, компонент `SkillSettingsModal.tsx`).
3. Edit: `handleEditSkill` (`223–234`) → `startEditSession`, без build/tracks.

Suggestions-паттерн для ориентира по UX кнопок: `Chat.tsx` (`visibleSuggestions`, `~226+`) + кадр `suggestions` в `usePlannerSession.ts` / `ws.ts`.

**Нельзя** писать выбор трека через `planner.send` / WS user-frame — это запускает ход планировщика (`sessions.py` WS loop). Нужен API тихой записи из code-плана, затем `buildSkill`.

## Затрагиваемые файлы

- `frontend/src/api.ts` — тип `SkillTrack`, `proposeSkillTracks(sessionId)`, при необходимости `selectSkillTrack(sessionId, track)` / аналог quiet-append.
- `frontend/src/App.tsx` — расширить `handleCreateSkill`: tracks → (picker | auto) → persist intent → `buildSkill` → `SkillSettingsModal`; не вызывать tracks в edit-flow; при fallback/ошибке фазы A — сразу build.
- `frontend/src/components/SkillTrackPicker.tsx` (новый) или модалка рядом с settings — список треков: название + rationale, выбор одного, cancel/abort без build.
- При необходимости лёгкие правки `Chat.tsx` (loading «подбираем варианты операции…» на этапе tracks) — без смены planner-flow.
- `SkillSettingsModal.tsx` — по возможности не трогать (остаётся configure после успешного build).

## План действий

1. Добавить в `api.ts` типы и `proposeSkillTracks` → `POST /sessions/${id}/skill-tracks`; клиент для тихой фиксации выбора (контракт из code-шага).
2. Вынести UI выбора: компактный picker (модалка или chip/кнопки как suggestions) — `name` + `rationale`; без карточного дашборда; один CTA на трек.
3. В `handleCreateSkill` (только create, не edit):
   - вызвать `proposeSkillTracks`;
   - `tracks.length === 0` или флаг fallback/skip → сразу `buildSkill` → settings (как сейчас);
   - `tracks.length === 1` → без UI записать intent → `buildSkill` → settings;
   - `tracks.length > 1` → показать picker → по выбору записать intent → `buildSkill` → settings;
   - ошибка сети/5xx фазы A → не блокировать: fallback на одношаговый `buildSkill`.
4. Состояния loading/error: отдельный флаг «предлагаем треки» vs `buildingSkill`; закрытие picker без выбора не создаёт скилл.
5. Убедиться, что `handleEditSkill` / `editingSkill != null` путь «собрать снова» не вызывает phase A (если rebuild из edit идёт через тот же handler — гейт по `editingSkill` или ответу API skip).
6. Ручная проверка кейсов из ТЗ + `pnpm run build`, `lint`, `typecheck` в `frontend/`.

## Критерии приёмки (Definition of Done)

- [ ] В `api.ts` есть `SkillTrack` и `proposeSkillTracks`; вызов соответствует backend-контракту.
- [ ] При >1 треке пользователь видит выбор (name + rationale) **до** `SkillSettingsModal`; после выбора идёт quiet persist + `buildSkill` + settings.
- [ ] При ровно 1 треке шаг выбора не показывается (авто-скип).
- [ ] Сбой/fallback фазы A не блокирует сборку — открывается обычный build → settings.
- [ ] Edit-сессия существующего скилла не показывает phase A.
- [ ] Выбор трека не уходит в planner WS `send` (нет лишнего хода ассистента).
- [ ] Из `frontend/`: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` зелёные.
- [ ] Визуальная приёмка — по дизайн-спеке `CATALOG-27.design.md` (фаза catalog-designer на UI-шаге pipeline).
