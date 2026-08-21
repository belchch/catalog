# CATALOG-155 — ui: блок «Выход» в форме сохранения скилла

- **Задача Plane:** [CATALOG-155](https://app.plane.so/belchch/projects/84997489-c485-4448-9ebe-0a06c4fa3cbc/issues/ca4f2f93-b6aa-4e73-bb5b-299fe9868e6c) (id: `ca4f2f93-b6aa-4e73-bb5b-299fe9868e6c`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 04 · предусловие: 03 (code того же тикета)
- **Цель:** Добавить блок «Выход» в `SkillSettingsModal` сразу после «Вход», переиспользовав `OutputsList` без форка: выходы видно и можно править в последний дешёвый момент перед заморозкой конфига.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было; тикет `code + ui`, разбит на два плана — `03-CATALOG-155-code-…` и этот)_

Тип: code + ui. Родитель: CATALOG-142. Порядок: независима от CATALOG-150, но её `OutputsList` потом подхватит флаг `multiple` автоматически.

**Контекст.** `SkillSettingsModal` — это точка, где человек подтверждает контракт скилла перед коммитом (CATALOG-6, `App.tsx:1087`). Сейчас в ней есть Имя, **Вход**, Провайдер, Модель, Режим рассуждений — и **нет Выхода**. Асимметрия бросается в глаза: `input_arity` настраивается именно здесь, а ровно симметричная ему декларация выходов — только в карточке OUTPUTS в панели артефактов (`ArtifactsPanel.tsx:906`), куда ещё надо догадаться зайти.

Хорошая новость: фронтенд к этому готов — CATALOG-146 вынес `OutputsList` отдельным компонентом с `value`/`onChange`/`rowErrors`, то есть он уже переиспользуем.

**Почему это не косметика.** Декларацию выходов пишет модель через `set_skill_outputs`. Если она ошиблась в описании или перепутала порядок (а порядок — это primary!), человек узнает об этом только после коммита и первого прогона. После коммита конфиг заморожен, и правка требует edit-сессии. Форма сохранения — последний момент, когда поправить дёшево.

**Что сделать (фронтенд-часть):**

5. `configureSkill` (`frontend/src/api.ts:537-552`) прокидывает `outputs`; `SkillPreview` в `api.ts:146-155` его читает.
6. **Блок «Выход» в модалке.** Сразу после «Вход» — вход и выход читаются парой. Внутри — `<OutputsList>` без форка компонента. Первая строка помечена как основной выход — порядок здесь смысл, а не оформление. Пустой список — нормальное состояние с пояснением «один документ», а не ошибка.
7. **Блокировка сохранения.** Кнопка «Сохранить» блокируется при невалидных выходах так же, как сейчас при пустом имени (`nameInvalid`).

_(Пункты 1–4 ТЗ — бэкенд; они в плане `03-CATALOG-155-code-…`.)_

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

**Предусловие.** Парный бэкенд-план `03-CATALOG-155-code-outputs-in-preview-and-configure.md` добавляет `outputs` в `SkillPreview` и приём `outputs` в ручке configure. Без него читать в форме нечего и отправлять некуда.

**Соседи по компоненту.** `OutputsList` — общий для карточки OUTPUTS ([ArtifactsPanel.tsx:906](frontend/src/components/ArtifactsPanel.tsx:906)) и этой формы. Его же правят CATALOG-154 (план `02-…`, переключатель «несколько документов») и CATALOG-157 (план `06-…`, потеря фокуса в поле «ключ»). Форк компонента запрещён: флаг `multiple` должен подхватиться в форме автоматически, без второй реализации.

**Фактическое состояние кода** (проверено):

- [frontend/src/components/SkillSettingsModal.tsx](frontend/src/components/SkillSettingsModal.tsx), 239 строк. Состояния — [:42-51](frontend/src/components/SkillSettingsModal.tsx:42); `nameInvalid` — [:51](frontend/src/components/SkillSettingsModal.tsx:51); `handleSave` зовёт `configureSkill(skillId, {model, provider, reasoning, input_arity, name})` — [:70](frontend/src/components/SkillSettingsModal.tsx:70); блок «Вход» (radiogroup со стрелочной навигацией) — [:118](frontend/src/components/SkillSettingsModal.tsx:118); дальше Провайдер — [:163](frontend/src/components/SkillSettingsModal.tsx:163), Модель — [:180](frontend/src/components/SkillSettingsModal.tsx:180); кнопка сохранения с `disabled={saving || nameInvalid}` — [:231](frontend/src/components/SkillSettingsModal.tsx:231).
- Точка монтирования — [frontend/src/App.tsx:1087](frontend/src/App.tsx:1087).
- `OutputsList` — [frontend/src/components/OutputsList.tsx](frontend/src/components/OutputsList.tsx): пропсы `value`, `onChange`, `disabled`, `rowErrors`, `firstKeyRef`; бейдж «основной» на первой строке уже есть — [:80](frontend/src/components/OutputsList.tsx:80); лимит и тултип «максимум 8 выходов» — [:159](frontend/src/components/OutputsList.tsx:159).
- Клиентская валидация: `validateOutputs` — [frontend/src/api.ts:739](frontend/src/api.ts:739) возвращает `{ok, rowErrors}`; `serializeOutputs` — [api.ts:730](frontend/src/api.ts:730); `MAX_SKILL_OUTPUTS` — [api.ts:685](frontend/src/api.ts:685).
- `configureSkill` — [frontend/src/api.ts:537](frontend/src/api.ts:537); тип `SkillPreview` на клиенте — [api.ts:146](frontend/src/api.ts:146).

**Порядок = смысл.** Первая строка — primary. Кнопки ↑ ↓ в `OutputsList` уже переставляют строки; в форме это должно реально менять primary в замороженном конфиге, а не только вид.

**Пустой список — не ошибка.** Скилл без объявленных выходов легитимен (один документ, сегодняшнее поведение). Блок показывает пояснение, а не красную строку, и сохраняется без изменений.

**Стиль.** Только токены и примитивы из [docs/ui-style-guide.md](docs/ui-style-guide.md). Визуальная приёмка — по дизайн-спеке `04-CATALOG-155-ui-output-block-settings-modal.design.md` от `catalog-designer`.

## Затрагиваемые файлы

| Файл | Что делаем |
| --- | --- |
| [frontend/src/api.ts](frontend/src/api.ts) | `SkillPreview.outputs` в клиентском типе; `configureSkill` прокидывает `outputs` |
| [frontend/src/components/SkillSettingsModal.tsx](frontend/src/components/SkillSettingsModal.tsx) | состояние выходов из `preview.outputs`; блок «Выход» после «Вход»; `<OutputsList>`; валидация и блокировка «Сохранить»; отправка в `configureSkill` |
| [frontend/src/components/OutputsList.tsx](frontend/src/components/OutputsList.tsx) | правок по существу нет — переиспользование как есть |
| `frontend/src/components/SkillSettingsModal.test.tsx` | **новый** (или дополнение существующего) — тесты формы |
| `docs/plan/shift-2026-08-20-claude/04-CATALOG-155-ui-output-block-settings-modal.design.md` | дизайн-спека (создаёт `catalog-designer`) |

## План действий

1. Прочитать дизайн-спеку шага и [docs/ui-style-guide.md](docs/ui-style-guide.md).
2. **Клиентский тип.** Добавить `outputs` в `SkillPreview` — [api.ts:146](frontend/src/api.ts:146), в форме, которую отдаёт бэкенд из плана `03-…`.
3. **`configureSkill`** — [api.ts:537](frontend/src/api.ts:537): принимать и отправлять `outputs`. Поле слать **только когда оно осознанно задано** — семантика ручки «отсутствует = не трогать»; для формы это значит: если блок отрисован, поле шлём всегда (человек его видел), а не «только при изменении».
4. **Состояние в модалке** — [SkillSettingsModal.tsx:42](frontend/src/components/SkillSettingsModal.tsx:42): `outputs` инициализируются из `preview.outputs`, рядом `outputsRowErrors`. Инициализация — как у `inputArity` ([:45](frontend/src/components/SkillSettingsModal.tsx:45)).
5. **Блок «Выход»** — сразу после блока «Вход» ([:118-160](frontend/src/components/SkillSettingsModal.tsx:118)), тем же визуальным паттерном (подпись `text-[11px] text-ink-faint`, отступ `mb-2`). Внутри — `<OutputsList value={outputs} onChange={…} disabled={saving} rowErrors={outputsRowErrors} />`, без форка.
6. **Пустое состояние** — когда выходов нет, показать пояснение «один документ» (формулировка из дизайн-спеки) над/под списком; не подсвечивать как ошибку.
7. **Валидация и блокировка.** Считать `outputsInvalid` через `validateOutputs` — [api.ts:739](frontend/src/api.ts:739); кнопка «Сохранить» — [:231](frontend/src/components/SkillSettingsModal.tsx:231) — `disabled={saving || nameInvalid || outputsInvalid}`. Ошибки строк отдавать в `rowErrors`.
8. **Ошибки бэкенда.** 422 от configure разложить обратно по строкам, если сообщение адресное; иначе показать в существующем блоке `error` — [:47](frontend/src/components/SkillSettingsModal.tsx:47).
9. **`handleSave`** — [:70](frontend/src/components/SkillSettingsModal.tsx:70): добавить `outputs` в тело запроса рядом с `input_arity`.
10. **Тесты** (`SkillSettingsModal.test.tsx`): форма показывает выходы из preview с описаниями и пометкой основного; добавление/удаление/переименование/перестановка работают; перестановка первого меняет порядок в теле запроса; скилл без выходов показывает пояснение и сохраняется; дубль ключа / ключ не по шаблону / пустое описание / 9-й выход блокируют «Сохранить» и показывают ошибку на строке.
11. Прогнать все шесть команд из [CLAUDE.md](CLAUDE.md).

## Критерии приёмки (Definition of Done)

- [ ] Форма показывает выходы, объявленные планировщиком, с описаниями и пометкой основного.
- [ ] Блок «Выход» стоит сразу после «Вход» и читается с ним парой.
- [ ] Можно добавить, удалить, переименовать и **переставить** выход; перестановка первого действительно меняет primary в замороженном конфиге.
- [ ] Скилл без объявленных выходов показывает пустой блок с пояснением «один документ» и сохраняется без изменений — старый сценарий не сломан.
- [ ] Дубль ключа, ключ не по шаблону, пустое описание и 9-й выход показывают ошибку на строке и не дают сохранить.
- [ ] `OutputsList` переиспользован без форка — флаг `multiple` из CATALOG-154 подхватится в форме автоматически.
- [ ] 422 от бэкенда виден человеку, а не теряется молча.
- [ ] Только токены и примитивы [docs/ui-style-guide.md](docs/ui-style-guide.md), сырые палитры запрещены.
- [ ] Выполнены критерии визуальной приёмки из `04-CATALOG-155-ui-output-block-settings-modal.design.md`.
- [ ] Frontend: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck`, `pnpm run test` — зелёные.
- [ ] Backend: `ruff check .`, `pytest` — зелёные.
