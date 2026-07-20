# CATALOG-53 — Дизайн UI

- **Источник:** docs/plan/next-shift/CATALOG-53-ui-session-artifacts-panel.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Пользователь в чате планировщика видит и правит черновик скилла (meta / prompt / script) **до** нажатия «Создать скилл», без модалки и без простыни в сообщениях. Панель-канвас справа от чата — основной носитель черновика; чат остаётся диалогом.

Сценарий:
1. Пользователь ведёт диалог → планировщик вызывает `save_skill_*` / `set_skill_meta` → по WS `session_artifacts` панель обновляется live (без перезагрузки).
2. Пользователь открывает секцию Prompt / Script / Meta, правит текст или поля, жмёт «Сохранить» → `PATCH`; статус `is_valid` / `error` / `source` отображается сразу.
3. Пока планировщик стримит (`streaming`) — редактирование и Save заблокированы; live-обновления от tools всё ещё применяются к не-dirty секциям.
4. Пользователь жмёт «Создать скилл из сессии». При 422 (пустой/битый артефакт) — понятный notice + подсветка нужной секции в панели (на узком экране панель открывается автоматически). При успехе — как сейчас: `SkillSettingsModal` для model/provider/reasoning (вне скоупа артефактов).
5. Смена сессии / edit-сессия — панель гидратится из `GET /sessions/{id}/artifacts` (edit seed уже на бэке).

RunView не затрагивается: при активном run main целиком занят `RunView`, панель артефактов скрыта.

## Дерево компонентов и файлы

Новый:

- `frontend/src/components/ArtifactsPanel.tsx`
  - Канвас черновика: заголовок, три секции (Meta / Prompt / Script), локальные draft-поля, Save per section, статусы, подсветка ошибки build.
  - Props: артефакты + callbacks save + `streaming` + `highlightType` + `sessionId` (null → empty).

Изменяемые:

- `frontend/src/App.tsx`
  - Layout main: Chat + ArtifactsPanel (сплит / toggle); wiring state панели, highlight при 422, проброс props из planner.
  - `handleCreateSkill`: при ошибке build разобрать detail → `setNotice` + `setArtifactHighlight` + на узком экране показать панель.
- `frontend/src/hooks/usePlannerSession.ts`
  - State `artifacts: SessionArtifact[]`; hydrate GET при смене `sessionId`; обработка WS `session_artifacts`; экспорт `savePrompt` / `saveScript` / `saveMeta` (или единый `saveArtifact`) + `artifactsError`.
  - `resetLocal` очищает артефакты.
- `frontend/src/ws.ts`
  - В `ServerEvent` добавить кадр `{ type: 'session_artifacts'; artifacts: SessionArtifact[] }`.
- `frontend/src/api.ts`
  - Типы `SessionArtifact`, `SkillMetaPatch`; `getSessionArtifacts`, `patchArtifact(sessionId, type, content)`, `patchSkillMeta(sessionId, meta)`.
- `frontend/src/components/Chat.tsx`
  - Опционально: prop `onOpenArtifacts?: () => void` не обязателен; связь с 422 — через App (notice + highlight). В скоупе шага Chat менять только если нужен явный CTA «Открыть черновик» в notice — предпочтительно держать notice в App-баннере и авто-открытие панели.

Новых UI-библиотек / редакторов кода не вводим: `textarea` + monospace для script (как `<pre>` в `TraceSteps`).

## Layout и состояния

### Размещение в App

Текущий main (`overflow-hidden`) при отсутствии `activeRunId`:

```
┌─────────────────────────────────────────────────────────┐
│ [toggle на <lg: Чат | Черновик]                         │  ← только < lg
├──────────────────────────────┬──────────────────────────┤
│ Chat                         │ ArtifactsPanel           │
│ (flex-1, min-w-0)            │ (w-full / lg:w-[420px]   │
│                              │  border-l slate-800)     │
└──────────────────────────────┴──────────────────────────┘
```

- **`lg` и шире (`lg:flex`):** горизонтальный сплит Chat | ArtifactsPanel. Панель всегда видна при наличии `sessionId`; без сессии — правая колонка с empty-state.
- **Ниже `lg`:** один из двух видов на весь main; переключатель в тонкой полоске над контентом (`text-xs`, сегменты как arity-кнопки в `SkillSettingsModal`: активный `bg-indigo-600`, неактивный `bg-slate-800`). По умолчанию — «Чат». При build-422 с указанием секции — принудительно вид «Черновик».
- **`activeRunId`:** только `RunView` на весь main (как сейчас); toggle и панель не рендерятся.

Ширина панели на desktop: фиксированная `lg:w-[420px] lg:shrink-0`, не resizable (вне скоупа).

### Структура ArtifactsPanel

Сверху вниз, скролл всей панели (`overflow-y-auto`, `h-full`):

1. **Заголовок:** «Черновик скилла» (`text-sm font-semibold text-slate-200`) + при `streaming` бейдж «планировщик пишет…» (`text-[10px] text-amber-400`).
2. **Секция Meta** (form).
3. **Секция Prompt** (textarea).
4. **Секция Script** (monospace textarea).

Каждая секция — карточка-блок:

```
┌ Meta                          source · updated     ┐
│ [поля формы]                                      │
│ [ошибка is_valid=false]                           │
│                              [Сохранить meta]     │
└───────────────────────────────────────────────────┘
```

Секции **не** используют `CollapsibleSection` из сайдбара (там другой контекст); внутри панели — всегда раскрыты, чтобы канвас был обозрим. Заголовок секции: `text-[11px] uppercase tracking-wide text-slate-500`.

**Meta — поля (через `PATCH .../skill-meta`, не raw JSON):**
- Имя (`name`) — text input, обязательное при save.
- Описание (`description`) — textarea, 2–3 строки.
- Kind — radiogroup `agent` | `script` (паттерн кнопок как arity в `SkillSettingsModal`).
- Вход (`input_arity`) — те же опции: «1 документ» / «2 документа» / «Список» (`1` | `2` | `null`).
- `allowed_tools` — одна строка input, значения через запятую (trim/split); для `kind=script` поле disabled + подпись «не используется для script».
- `verify_checks` — textarea JSON-массива объектов (как в API) **или** одна строка id проверок через запятую, маппящаяся в `[{check: id}]`. Выбрать **строку id через запятую** (проще для среза); пустая → `[]`.

**Prompt / Script:** полноширинный `textarea` (`min-h-[8rem]` prompt, `min-h-[10rem]` script; `font-mono text-xs` для script). Плейсхолдеры: «System prompt скилла…» / «Python-скрипт скилла…».

Акцент по `kind` из meta (если meta есть):
- `kind=agent` — секция Prompt визуально основная (обычная рамка); Script — приглушённая подпись «нужен только для kind=script».
- `kind=script` — наоборот.
- Без meta — все секции равнозначны.

### Состояния панели / секций

| Состояние | Что видно |
|-----------|-----------|
| **no session** (`sessionId == null`) | Центр: `text-sm text-slate-500` «Выберите сессию или начните новый чат — здесь появится черновик скилла.» Полей нет. |
| **loading (hydrate)** | Краткий скелетон или `text-xs text-slate-500` «Загружаю артефакты…» один раз при смене сессии; без блокировки чата. |
| **empty artifacts** | Секции с пустыми полями; micro-copy под заголовком: «Планировщик сохранит черновик инструментами, или заполните вручную.» |
| **hydrated / live** | Поля = server content; бейджи `source` (`planner` / `user`) и относительное/ISO `updated_at` мелким `text-[10px] text-slate-500`. |
| **invalid section** | `is_valid === false`: рамка секции `border-red-500/50`, текст `error` под полями `text-[11px] text-red-400`. Save всё равно доступен (повторная попытка). |
| **dirty** | Локальные правки отличаются от последнего server snapshot секции; кнопка Save активна (если не streaming). Incoming WS **не** перетирает dirty-секцию; не-dirty обновляются. |
| **saving** | Кнопка секции «Сохраняю…», `disabled`; остальные секции доступны. |
| **streaming lock** | Все inputs/radios/Save `disabled` (`opacity-50`); бейдж в шапке. |
| **save error** | Текст ошибки под кнопкой секции `text-xs text-red-400` (сеть / 422 PATCH); server snapshot не меняем. |
| **build highlight** | Секция с `type === highlightType`: `ring-1 ring-red-400/60` + при необходимости `scrollIntoView` при появлении highlight. Снимается при успешном save этой секции, смене сессии или ручном редактировании поля. |
| **success save** | Краткий `text-[10px] text-emerald-400` «Сохранено» ~1.5s у кнопки; обновление полей из ответа PATCH. |

## Взаимодействия

- **Save Meta:** валидация имени (trim non-empty) на клиенте; вызов `patchSkillMeta`; ответ → обновить artifact `meta` в state; сбросить dirty meta.
- **Save Prompt / Script:** `patchArtifact(sessionId, 'prompt'|'script', content)`; ответ содержит `is_valid`/`error` — показать сразу (invalid script не откатывает content).
- **WS `session_artifacts`:** полный список артефактов сессии → merge в state; для каждой секции: если не dirty — принять server content в draft; если dirty — оставить draft, обновить только «server snapshot» для последующего сравнения (или показать дискретную пометку «есть обновление от планировщика» + кнопка «Взять с сервера» — **минимальный вариант среза:** тихо не перетирать dirty, без баннера; пользователь может отменить dirty сбросом поля вручную / перезагрузкой сессии).
- **Смена `sessionId`:** сброс drafts + highlight + GET hydrate.
- **Create skill 422:** App парсит `detail` (строка):
  - содержит `meta` → highlight `meta`;
  - содержит `prompt` → highlight `prompt`;
  - содержит `script` → highlight `script`;
  - иначе highlight не ставим, notice всё равно показываем.
  Текст notice = detail бэка (как сейчас для прочих ошибок). На `<lg` переключить main на «Черновик».
- **Create skill success:** без изменений — открыть `SkillSettingsModal`; панель артефактов остаётся с текущими данными.
- **Крайние случаи:**
  - Двойной Save: второй клик игнор, пока `saving`.
  - Пустой prompt save: бэк может вернуть `is_valid=false` — показать error, не блокировать UI.
  - Нет сети при hydrate: панель empty + ошибка в `planner.error` или локальный `artifactsError` строкой под заголовком панели.
  - Reconnect WS: повторный GET артефактов не обязателен, если кадры приходят; при смене сессии GET обязателен.

## Стиль и токены

Консистентность с App/Chat/SkillSettingsModal: тёмный slate + indigo accent. Новых цветов/шрифтов/зависимостей нет.

- Панель: `flex h-full flex-col border-l border-slate-800 bg-slate-950`.
- Внутренние отступы: `p-3 gap-3` между секциями.
- Секция-блок: `rounded-md border border-slate-800 bg-slate-900/50 p-3`.
- Поля: как modal — `w-full rounded bg-slate-800 px-2 py-1 text-xs text-slate-100`.
- Labels: `text-[11px] text-slate-400`.
- Primary Save: `rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50`.
- Secondary/ghost не нужны.
- Toggle (mobile): ряд кнопок `rounded px-2 py-1 text-[11px]`, активная indigo.
- Script textarea: `font-mono text-xs leading-relaxed`.
- Invalid/highlight: красные токены как ошибки чата (`text-red-400`, `border-red-500/50`, `ring-red-400/60`).
- Не использовать карточки с тенями/`shadow-xl` в панели (модалка — исключение); только border + фон.

## Доступность (a11y)

- Панель: `role="region"`, `aria-label="Черновик скилла"`.
- Toggle Чат/Черновик: `role="tablist"` + кнопки `role="tab"` / `aria-selected`, либо radiogroup с `aria-label="Область main"` — выбрать **tablist** (два таба). Панель/чат получают `role="tabpanel"` только на `<lg`; на `lg+` оба видны — tablist скрыт (`hidden lg:hidden` на toggle), регионы без tab-ролей.
- Kind и input_arity: `role="radiogroup"` + `role="radio"` + стрелки (как в `SkillSettingsModal`).
- Ошибки секции: связать с полями через `aria-describedby` на контейнере ошибки; `aria-invalid` на textarea/input при `!is_valid` или клиентской ошибке имени.
- При `streaming` disabled-поля корректно выпадают из tab order.
- После build-422 и подсветки — `focus()` на первое поле проблемной секции (name / prompt textarea / script textarea).
- Контраст: основной текст `slate-100`/`slate-300` на `slate-950`; вспомогательный `slate-500` только для meta-меток.

## Контракты данных (если нужны)

Источник: ADR-0015, code-план `CATALOG-53-code-session-artifacts.md`, backend уже отдаёт:

**REST**
- `GET /sessions/{id}/artifacts` → `SessionArtifact[]`
- `PATCH /sessions/{id}/artifacts/{type}` body `{ content: string }` → `SessionArtifact` (`type`: `prompt` | `script` | `meta`)
- `PATCH /sessions/{id}/skill-meta` body `SkillMetaPatch` (`name`, `description`, `kind`, `input_arity`, `allowed_tools`, `verify_checks`) → `SessionArtifact` (type=meta)
- `POST /sessions/{id}/skills` — build; 422 `detail: string` при битых/пустых артефактах

**Тип артефакта (зеркало `SessionArtifactOut`):**
```ts
type SessionArtifact = {
  type: 'prompt' | 'script' | 'meta'
  content: string
  is_valid: boolean
  error: string | null
  source: string
  updated_at: string
}
```
Meta `content` — JSON-строка `{ name, description, kind, input_arity, allowed_tools, verify_checks }`; UI для редактирования meta использует structured PATCH, а для отображения парсит `content` при hydrate/WS.

**WS**
- `{ type: 'session_artifacts', artifacts: SessionArtifact[] }` — полный снимок списка (как `session_docs`).

**Хук:** по аналогии с `sessionDocuments` — hydrate GET + live WS; save-методы вызывают api и обновляют локальный список из ответа.

## Критерии визуальной приёмки

- [ ] При открытой сессии без `activeRunId` на `lg+` справа от чата видна панель «Черновик скилла» с секциями Meta, Prompt, Script.
- [ ] На ширине `<lg` есть переключатель «Чат» / «Черновик»; по умолчанию чат; RunView по-прежнему занимает весь main без панели.
- [ ] После tool-save планировщика содержимое панели обновляется без перезагрузки страницы (WS).
- [ ] Ручное сохранение каждой секции уходит в PATCH; при `streaming` поля и Save недоступны.
- [ ] Невалидный script показывает `error` в секции Script (красная рамка/текст).
- [ ] Пустая сессия (`sessionId == null`) даёт empty-state панели, а не пустые инпуты «в никуда».
- [ ] Build 422 показывает notice с текстом ошибки и подсвечивает соответствующую секцию; на узком экране открывается вид «Черновик».
- [ ] Стили панели согласованы с Chat/Modal (slate + indigo, `text-xs` поля, без новых зависимостей и без теневых карточек).
- [ ] Клавиатура: radiogroup kind/arity, фокус на проблемной секции после 422, регион панели именован для a11y.
)