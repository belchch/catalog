# CATALOG-118 — Дизайн UI

- **Источник:** `docs/plan/day-shift/04-CATALOG-118-ui-tools-popover.md`
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Пользователь в чате решает, какие скиллы планировщик может вызывать как инструменты в этой сессии.

1. В нижней панели композера (слот из CATALOG-116) пользователь видит иконку-ключ; если инструменты уже включены — на ней бейдж-счётчик.
2. Клик по иконке открывает поповер **над** панелью, привязанный к кнопке. Фокус сразу в поле поиска.
3. Пользователь видит список скиллов: включённые закреплены сверху, у каждого — имя, бейджи `ai`/`python`, описание одной строкой и строка гарантии (`script` / `agent` / `pipeline`).
4. Тумблер справа включает/выключает скилл как инструмент. Изменение видно мгновенно (оптимистично), счётчик на иконке обновляется синхронно.
5. Шеврон рядом с тумблером уводит в карточку скилла в сайдбаре (тот же путь, что при выборе скилла в секции «Скиллы»), поповер при этом закрывается.
6. Внизу поповера — «Создать скилл», дублирующая действие из хедера чата.
7. Escape / клик мимо / смена сессии / начало генерации закрывают поповер.

Скиллы `kind != 'script'` показываются, но включить их нельзя: backend регистрирует тулом только frozen script (`build_session_skill_tools`). Тумблер у них выключен, в строке гарантии — пояснение. Это осознанное решение: молча прикреплять скилл, который никогда не станет тулом, хуже, чем показать причину.

## Дерево компонентов и файлы

- `frontend/src/components/ToolsPopover.tsx` — **новый**, презентационный. Без собственных запросов: получает данные и колбэки пропсами.
  - Props: `open`, `onClose`, `skills: SkillOut[]`, `attachedIds: string[]`, `pendingIds?: string[]`, `onToggle(skillId, enabled)`, `onCreateSkill?`, `createDisabled?`, `onOpenSkillCard?(skillId)`, `loading?`, `error?: string | null`, `id?`.
  - Внутреннее состояние — только `query` (строка поиска); сбрасывается при закрытии.
- `frontend/src/components/Chat.tsx` — рендерит `ToolsPopover` внутри одной `relative`-обёртки вместе с кнопкой-ключом (кнопка и поповер — общий контейнер, чтобы клик по триггеру не считался «кликом вне»).
  - Новые пропсы (в дополнение к `attachedSkillCount`, `onOpenTools` из CATALOG-116): `toolsOpen?`, `onCloseTools?`, `availableSkills?: SkillOut[]`, `attachedSkillIds?: string[]`, `pendingToolIds?: string[]`, `onToggleTool?`, `toolsLoading?`, `toolsError?: string | null`, `onOpenSkillCard?`.
  - Кнопка-ключ получает `aria-haspopup="dialog"`, `aria-expanded={toolsOpen}`, `aria-controls` = id поповера.
- `frontend/src/App.tsx` — владелец состояния: `toolsOpen`, `sessionTools: SkillOut[]`, `pendingToolIds: string[]`, `toolsLoading`, `toolsError`. Загрузка привязанных тулов при смене `sessionId`, toggle attach/detach, сброс при смене сессии/воркспейса. Список доступных скиллов берётся из уже загруженного `skillsHook.skills` (второй `listSkills()` не нужен).
- `frontend/src/api.ts` — `getSessionTools`, `attachSessionTools`, `removeSessionTool` + тип `SessionToolsAttachResult`.
- `frontend/src/components/SkillsPanel.tsx` — опциональные пропсы `focusSkillId?: string | null` и `onFocusHandled?: () => void`: при появлении id панель выделяет скилл (как при клике), скроллит к нему (`scrollIntoView({ block: 'nearest' })`) и сообщает наверх. Больше ничего в панели не меняется.
- `frontend/src/components/ToolsPopover.test.tsx` — рядом с `Chat.test.tsx`.

## Layout и состояния

Геометрия поповера (привязка к кнопке-ключу):

```
absolute bottom-full left-0 z-30 mb-2 w-80 max-w-[calc(100vw-2rem)]
overflow-hidden rounded-card border border-line bg-surface shadow-card
```

Секции сверху вниз:

1. **Шапка** — `border-b border-line px-3 py-2`:
   - заголовок «Инструменты» — `text-xs font-medium text-ink`;
   - подпись «Планировщик может вызывать включённые скиллы» — `text-[11px] text-ink-faint`;
   - поиск: `<input type="search" class="field mt-2 text-xs">`, `placeholder="Поиск…"`, `aria-label="Поиск инструментов"`, `autoFocus`.
2. **Список** — `max-h-72 overflow-y-auto py-1`, `role="list"`. Две группы: сначала включённые (в порядке ответа `GET /tools`, т.е. по времени привязки), затем остальные (в порядке `listSkills()`). Если обе группы непусты — перед каждой мелкий заголовок `px-3 pb-0.5 pt-1.5 text-[10px] uppercase tracking-wide text-ink-faint`: «Включены» и «Доступны». Если одна из групп пуста — заголовки не рендерим.
3. **Футер** — `border-t border-line px-3 py-2`, кнопка «Создать скилл» — `btn-secondary w-full`.

Строка скилла (`li`, `flex items-start gap-2 px-3 py-2 hover:bg-surface-hover`):

- левая колонка `min-w-0 flex-1`:
  - ряд 1: имя (`truncate text-xs text-ink`) + бейджи `python` → `badge-info`, `ai` → `badge-accent` (порядок фиксированный: python, затем ai);
  - ряд 2: описание — `truncate text-[11px] text-ink-faint`; при пустом описании «Без описания»;
  - ряд 3 (гарантия) — `text-[11px] text-ink-faint`: `script` / `agent` / `pipeline` по `skill.kind`; для не-`script` дополняется « · не вызывается как инструмент».
- правая колонка `flex shrink-0 items-center gap-1`:
  - шеврон — `btn-icon-ghost`, `aria-label="Открыть карточку <имя>"`, рендерится только если передан `onOpenSkillCard`;
  - тумблер (см. ниже).

Тумблер: трек `h-5 w-9 rounded-full transition-colors motion-reduce:transition-none`, включён — `bg-brand`, выключен — `bg-surface-muted`; бегунок `h-4 w-4 rounded-full bg-surface shadow transition-transform motion-reduce:transition-none`, смещение `translate-x-4` / `translate-x-0.5`. Недоступный тумблер — `bg-surface-muted` + `cursor-not-allowed` (без `opacity-50`).

Состояния экрана:

| Состояние | Что показываем |
|---|---|
| `loading` (грузим привязанные тулы) | строка `px-3 py-2 text-xs text-ink-faint` «Загрузка…»; поиск и футер активны |
| Скиллов нет вообще | «Скиллов пока нет — создайте из сессии планировщика» (`text-xs text-ink-faint`), футер остаётся |
| Поиск ничего не нашёл | «Ничего не найдено» + кнопка `btn-secondary text-[11px]` «Сбросить» (очищает `query`, фокус возвращается в поиск) |
| Ошибка attach/detach/загрузки | в шапке под поиском блок `role="alert"` `mt-2 rounded border border-danger-line bg-danger-soft px-2 py-1 text-[11px] text-danger-ink`; список остаётся видимым |
| Успех | тумблер в новом положении, счётчик на иконке-ключе совпадает с числом включённых |
| Строка в процессе запроса | `aria-busy="true"` на `li`, тумблер `disabled` (только эта строка, остальные кликабельны) |

## Взаимодействия

- **Открытие/закрытие.** Клик по иконке-ключу переключает `toolsOpen`. Закрытие: `Escape` (фокус возвращается на иконку-ключ), `mousedown` вне общего контейнера «кнопка + поповер», выбор «Создать скилл», клик по шеврону, смена `sessionId`, переход `streaming` в `true`. При закрытии `query` сбрасывается.
- **Поиск.** Фильтр по имени и описанию, регистронезависимо, по подстроке. Фильтрация не меняет группировку: включённые остаются сверху.
- **Тумблер (оптимистично).**
  - Включение: локально добавляем id в `attachedIds`, id попадает в `pendingIds`; `POST /sessions/{id}/tools` с `{ skill_ids: [id] }`; ответ `skills` становится новым состоянием привязанных.
  - Если id вернулся в `skipped_skill_ids` — откат, ошибка «Скилл не найден — обновите список скиллов» и `skillsHook.refresh()`.
  - Выключение: локально убираем id; `DELETE /sessions/{id}/tools/{skill_id}`; `404 skill not attached` считаем успехом (клиент уже так делает для документов).
  - Любая другая ошибка — откат к предыдущему состоянию + текст ошибки из `extractApiDetail`.
  - Повторные клики по строке в состоянии `pending` игнорируются.
- **Счётчик.** `attachedSkillCount` = длина `attachedSkillIds` (оптимистичного). Бейдж скрыт при нуле — поведение CATALOG-116 не меняем.
- **Шеврон.** Закрывает поповер → `App` открывает секцию «Скиллы» (`setOpenSkills(true)`) и передаёт `focusSkillId` в `SkillsPanel`, та выделяет скилл и скроллит к нему. Ниже `lg` сайдбар скрыт (`.catalog-sidebar { display: none }`), поэтому `App` передаёт `onOpenSkillCard` только при `isLg` — на узком экране шеврона нет вовсе, мёртвых кнопок не появляется.
- **«Создать скилл».** Закрывает поповер и вызывает тот же `onCreateSkill`, что кнопка в хедере чата; `disabled` по тому же предикату (`buildingSkill || proposingTracks || messages.length === 0`).
- **Крайние случаи.**
  - Сессии нет (`sessionId == null`): иконка-ключ уже `disabled` (CATALOG-116), поповер не открывается.
  - Скилл удалён из воркспейса, пока поповер открыт: строка исчезает после `skillsHook.refresh()`, счётчик пересчитывается по пересечению `attachedIds` с существующими скиллами.
  - Скилл `kind != 'script'`: тумблер `disabled`, `title`/`aria-description` — «Инструментом может стать только script-скилл».
  - Длинное имя/описание — `truncate` + `title` с полным текстом.
  - Поповер не должен выходить за пределы колонки чата: суммарная высота ограничена `max-h-72` у списка.

## Стиль и токены

- Только семантические утилиты из `docs/ui-style-guide.md`: `bg-surface`, `bg-surface-muted`, `bg-surface-hover`, `border-line`, `border-danger-line`, `bg-danger-soft`, `text-ink`, `text-ink-faint`, `text-danger-ink`, `bg-brand`, `rounded-card`, `shadow-card`. Сырые палитры Tailwind (`slate-*`, `red-*`, …) запрещены.
- Примитивы переиспользуем: `.field` (поиск), `.btn-secondary` (футер, «Сбросить»), `.btn-icon-ghost` (шеврон), `.badge-info` / `.badge-accent` (теги). Новые классы в `index.css` не заводим.
- Типографика как в остальном UI: заголовок и имена — `text-xs`, вторичные строки — `text-[11px]`, бейджи — из примитивов (`text-[10px]`).
- Ритм: padding строк `px-3 py-2`, зазоры `gap-1` / `gap-2`, разделители секций — `border-line`.
- Иконки: шеврон добавляется в `frontend/src/components/icons.tsx` (`ChevronRightIcon`, 16×16, тот же `iconBase`, `stroke="currentColor"`), в проекте его пока нет. Новых зависимостей не вводим.

## Доступность (a11y)

- Поповер — `role="dialog"` + `aria-label="Инструменты сессии"`, **без** `aria-modal` (это не модалка, фон остаётся рабочим). Фокус не запираем.
- Триггер: `aria-haspopup="dialog"`, `aria-expanded`, `aria-controls`; `aria-label` уже содержит число включённых (`Инструменты, включено N`) — счётчик-бейдж остаётся `aria-hidden`.
- При открытии фокус уходит в поиск; при закрытии по `Escape` или выбору действия — возвращается на кнопку-ключ.
- Тумблер: `role="switch"`, `aria-checked`, `aria-label` «Включить <имя> как инструмент» / «Отключить <имя>»; `disabled` для не-`script`.
- Список — `role="list"`, строки — `li`; заголовки групп связаны со списком визуально и не перехватывают фокус.
- Ошибка — `role="alert"`; блок загрузки — `aria-busy` на списке.
- Фокус-видимость везде через `focus-visible:ring-2 focus-visible:ring-brand` (в примитивах уже есть).
- Анимации тумблера гасятся `motion-reduce:transition-none`.

## Контракты данных

REST из CATALOG-117 (как реализовано на `pipeline/day-shift`):

- `GET /sessions/{id}/tools` → `SkillOut[]` (порядок = порядок привязки).
- `POST /sessions/{id}/tools`, тело `{ "skill_ids": ["<id>"] }` → `{ "skipped_skill_ids": string[], "skills": SkillOut[] }`.
- `DELETE /sessions/{id}/tools/{skill_id}` → `204`; `404` с `skill not attached` трактуем как успех.
- Список доступных скиллов — существующий `listSkills()` (`SkillOut`: `name`, `description`, `kind`, `tags`, `status`).

Бейджи берутся из `tags` (`compute_tags`): `python` — детерминированный код, `ai` — LLM. Строка гарантии — из `kind`.

**Отклонение от ТЗ (осознанное):** пункт «`script` или N проверок» реализуем только в части `script`. `SkillOut` не отдаёт `verify_checks` (backend считает их лишь в описании тула, `skill_tools.py`), а расширение схемы — backend-изменение вне списка затрагиваемых файлов этого UI-шага. Число проверок не выдумываем и не запрашиваем дополнительными запросами; когда поле появится в `SkillOut`, строка гарантии станет `script · N проверок` без переработки вёрстки.

## Критерии визуальной приёмки

- [ ] Клик по иконке-ключу открывает поповер над панелью композера, привязанный к кнопке; повторный клик закрывает.
- [ ] Ширина поповера `w-80`, скругление `rounded-card`, рамка `border-line`, тень `shadow-card`, фон `bg-surface`.
- [ ] Шапка содержит заголовок, подпись и поле поиска; при открытии фокус в поиске.
- [ ] Включённые скиллы идут первыми; при обеих непустых группах есть заголовки «Включены» / «Доступны».
- [ ] В строке видны: имя, бейджи `python` (`badge-info`) и/или `ai` (`badge-accent`), описание одной строкой, строка гарантии по `kind`.
- [ ] Тумблер — `role="switch"` с `aria-checked`; включённый трек `bg-brand`, выключенный `bg-surface-muted`.
- [ ] У скилла с `kind != 'script'` тумблер выключен (`cursor-not-allowed`, без `opacity-50`) и есть пояснение в строке гарантии.
- [ ] Переключение отражается мгновенно, а счётчик на иконке равен числу включённых; при ошибке состояние откатывается и появляется блок `role="alert"` в токенах danger.
- [ ] Поиск фильтрует по имени и описанию; пустой результат даёт «Ничего не найдено» + «Сбросить».
- [ ] Пустой список скиллов и состояние загрузки показывают текст в `text-ink-faint`, футер «Создать скилл» остаётся на месте.
- [ ] Шеврон закрывает поповер, раскрывает секцию «Скиллы» и выделяет нужный скилл; ниже `lg` шеврон не рендерится.
- [ ] «Создать скилл» в футере закрывает поповер и запускает то же действие, что кнопка в хедере чата, и блокируется в тех же условиях.
- [ ] Escape закрывает поповер и возвращает фокус на иконку-ключ; клик вне закрывает; начало генерации и смена сессии закрывают.
- [ ] В диффе нет сырых палитр Tailwind и новых классов в `index.css`; используются только токены и примитивы style guide.
