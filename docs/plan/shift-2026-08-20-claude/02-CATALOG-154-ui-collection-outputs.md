# CATALOG-154 — ui: коллекционные выходы в черновике и в результате прогона

- **Задача Plane:** [CATALOG-154](https://app.plane.so/belchch/projects/84997489-c485-4448-9ebe-0a06c4fa3cbc/issues/a63bcf77-f735-4aa3-9d2e-433f7220fddd) (id: `a63bcf77-f735-4aa3-9d2e-433f7220fddd`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 02 · предусловие: 01 (code, CATALOG-153) · по тексту ТЗ — после бэкенда коллекционных выходов
- **Цель:** Дать коллекционному выходу выражение в UI: переключатель «несколько документов» в строке `OutputsList`, одна вкладка-группа вместо N вкладок в `RunView`, честное число создаваемых документов до нажатия «Сохранить».

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: ui. Порядок: после бэкенда коллекционных выходов.

**Контекст.** CATALOG-146 уже дал каркас: `OutputsList` — отдельный переиспользуемый компонент со строками ключ/описание и перестановкой; `RunView` умеет вкладки по артефактам с клавиатурной навигацией (`RunView.tsx:76-107`) и переключает подпись кнопки по `multi` (`:110`).

Что ломается на коллекциях: `OutputDraft` (`api.ts:687-690`) — это `{key, description}` без кратности, а вкладка на каждый артефакт перестаёт работать, когда артефактов тридцать.

**Что сделать:**

1. **Типы.** `OutputDraft` получает `multiple?: boolean`; парсер артефакта `outputs` (`api.ts:703-730`) его читает и валидирует.
2. **`OutputsList`:** в строке переключатель «несколько документов» с пояснением, что число определяется при прогоне. Компонент уже используется в двух местах (карточка OUTPUTS в `ArtifactsPanel.tsx:906` и — после соседней задачи — форма сохранения), поэтому правка одна на обоих.
3. **`RunView` — группа вместо тридцати вкладок.** Коллекционный выход — **одна** вкладка с числом элементов в подписи; внутри — список элементов с заголовками, первый раскрыт. Клавиатурная навигация по вкладкам (`onTabKeyDown`) остаётся на уровне выходов, а не элементов — иначе Arrow-навигация становится бесполезной.
4. **Сколько будет создано — видно до нажатия.** Кнопка сохранения несёт число документов. Одно нажатие, создающее 30 документов в базе знаний, обязано сообщать об этом заранее. После успеха — сколько создано и куда перейти.
5. **Список созданных документов.** Чипы на 30 документов расползутся — сворачивать в «N документов» с раскрытием.
6. **Бейдж в списке скиллов.** У скилла с коллекционным выходом число документов до запуска неизвестно — бейдж по `outputs_count` должен показывать это честно, а не врать точным числом.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

**Предусловие.** Шаг опирается на бэкенд из CATALOG-153 (план `01-…`): значение артефакта приезжает как строка **или массив строк**, а декларация выхода несёт `multiple`. Без него переключатель некуда сохранять, а группировать в `RunView` нечего.

**Соседи по компоненту.** `OutputsList` правит ещё и CATALOG-155 (план `04-…`, блок «Выход» в форме сохранения) и CATALOG-157 (план `06-…`, потеря фокуса в поле «ключ»). Правка `OutputsList` здесь — одна на всех потребителей; форк компонента запрещён.

**Фактическое состояние кода** (проверено):

- `OutputDraft` — [frontend/src/api.ts:687](frontend/src/api.ts:687): `{ key: string; description: string }`. Рядом `OutputRowError` — [api.ts:692](frontend/src/api.ts:692), `RunArtifact` — [api.ts:697](frontend/src/api.ts:697) (`{ key, description?, text }`; поле `text` — то самое, что станет `string | string[]`).
- `parseOutputsArtifact` — [api.ts:703](frontend/src/api.ts:703): собирает `OutputDraft[]`, молча пропуская незнакомые поля. `serializeOutputs` — [api.ts:730](frontend/src/api.ts:730): пишет ровно `{key, description}` — сюда добавляется `multiple`. `validateOutputs` — [api.ts:739](frontend/src/api.ts:739). `MAX_SKILL_OUTPUTS = 8` — [api.ts:685](frontend/src/api.ts:685), `OUTPUT_KEY_RE` — [api.ts:683](frontend/src/api.ts:683).
- `OutputsList` — [frontend/src/components/OutputsList.tsx](frontend/src/components/OutputsList.tsx), 167 строк: строка = `ключ` + `описание` + колонка кнопок ↑ ↓ ✕; `add()` — [:60](frontend/src/components/OutputsList.tsx:60) пушит `{ key: '', description: '' }` (сюда добавится `multiple: false`); бейдж «основной» на `index === 0` — [:80](frontend/src/components/OutputsList.tsx:80).
- Потребитель №1 — карточка OUTPUTS в [frontend/src/components/ArtifactsPanel.tsx:906](frontend/src/components/ArtifactsPanel.tsx:906).
- `RunView` — [frontend/src/components/RunView.tsx](frontend/src/components/RunView.tsx): `multi = artifacts.length > 1` — [:69](frontend/src/components/RunView.tsx:69); состояние активной вкладки `activeKey` + сброс по `runId`/`artifactKeys` — [:74](frontend/src/components/RunView.tsx:74); `onTabKeyDown` (Arrow/Home/End по `artifacts`) — [:87](frontend/src/components/RunView.tsx:87); `saveLabel` — [:110](frontend/src/components/RunView.tsx:110), рендер кнопки — [:238](frontend/src/components/RunView.tsx:238); `createdDocIds` / чипы созданных документов — там же.
- Бейдж в списке скиллов: `outputs_count` в `SkillOut` — [api.ts:26](frontend/src/api.ts:26), рендер — в [frontend/src/components/SkillsPanel.tsx](frontend/src/components/SkillsPanel.tsx).
- Тесты, которые обязаны остаться зелёными: [frontend/src/components/RunView.test.tsx](frontend/src/components/RunView.test.tsx), [frontend/src/components/ArtifactsPanel.test.tsx](frontend/src/components/ArtifactsPanel.test.tsx).

**Ключевое ограничение навигации.** `onTabKeyDown` сегодня ходит по `artifacts` — то есть по выходам. После группировки список вкладок = список **выходов**, а не элементов; индексация внутри `onTabKeyDown` должна считаться по вкладкам, иначе Arrow начнёт перескакивать через 30 глав.

**Стиль.** Только токены и примитивы из [docs/ui-style-guide.md](docs/ui-style-guide.md); сырые палитры запрещены. Визуальная приёмка — по дизайн-спеке `02-CATALOG-154-ui-collection-outputs.design.md`, которую готовит `catalog-designer` перед реализацией.

## Затрагиваемые файлы

| Файл | Что делаем |
| --- | --- |
| [frontend/src/api.ts](frontend/src/api.ts) | `OutputDraft.multiple?: boolean`; чтение/валидация в `parseOutputsArtifact`; запись в `serializeOutputs`; `RunArtifact.text` → `string \| string[]` |
| [frontend/src/components/OutputsList.tsx](frontend/src/components/OutputsList.tsx) | переключатель «несколько документов» + пояснение; `add()` создаёт строку с `multiple: false` |
| [frontend/src/components/RunView.tsx](frontend/src/components/RunView.tsx) | вкладка-группа для коллекции; список элементов внутри; `onTabKeyDown` по выходам; число документов на кнопке сохранения; сворачивание чипов созданных документов |
| [frontend/src/components/SkillsPanel.tsx](frontend/src/components/SkillsPanel.tsx) | честный бейдж выходов, когда число неизвестно |
| [frontend/src/components/ArtifactsPanel.tsx](frontend/src/components/ArtifactsPanel.tsx) | правок по существу нет — проверить, что новая строка `OutputsList` встаёт в карточку OUTPUTS |
| [frontend/src/components/RunView.test.tsx](frontend/src/components/RunView.test.tsx), [frontend/src/components/ArtifactsPanel.test.tsx](frontend/src/components/ArtifactsPanel.test.tsx) | новые тесты + защита старого поведения |
| `docs/plan/shift-2026-08-20-claude/02-CATALOG-154-ui-collection-outputs.design.md` | дизайн-спека (создаёт `catalog-designer`) |

## План действий

1. Прочитать дизайн-спеку шага и [docs/ui-style-guide.md](docs/ui-style-guide.md); реализовывать по ним, а не по вольной трактовке.
2. **Типы.** `OutputDraft.multiple?: boolean` — [api.ts:687](frontend/src/api.ts:687). `parseOutputsArtifact` — [api.ts:703](frontend/src/api.ts:703) читает `multiple` только как настоящий `boolean` (чужой тип → ошибка строки, не «truthy»). `serializeOutputs` — [api.ts:730](frontend/src/api.ts:730) пишет `multiple` **только когда `true`**, чтобы JSON старых черновиков не менялся. `validateOutputs` — [api.ts:739](frontend/src/api.ts:739) дополнить проверкой типа.
3. **`RunArtifact.text`** — [api.ts:697](frontend/src/api.ts:697) расширить до `string | string[]` под новую форму из CATALOG-153; провести тип по потребителям, опираясь на `pnpm run typecheck`.
4. **`OutputsList`** — [OutputsList.tsx](frontend/src/components/OutputsList.tsx): в строку добавить переключатель «несколько документов» с коротким пояснением, что число определяется при прогоне; связать с `aria-describedby`, как сделаны существующие поля; `add()` — [:60](frontend/src/components/OutputsList.tsx:60) создаёт `{ key: '', description: '', multiple: false }`. Компонент не форкать — правка достаётся и карточке OUTPUTS, и форме сохранения из CATALOG-155.
5. **`RunView` — вкладки.** Строить список вкладок по **выходам**: обычный выход → как сейчас; коллекционный → одна вкладка с числом элементов в подписи. Внутри вкладки — список элементов с заголовками, первый раскрыт.
6. **`onTabKeyDown`** — [RunView.tsx:87](frontend/src/components/RunView.tsx:87): индексацию и `%` считать по списку вкладок (выходов), не по плоскому списку элементов. `id` фокусируемого элемента (`run-tab-${key}`) оставить на уровне выхода.
7. **Сброс активной вкладки** — [RunView.tsx:74](frontend/src/components/RunView.tsx:74): ключ пересчёта (`artifactKeys`) должен меняться при смене состава выходов, но **не** при изменении числа элементов внутри коллекции, иначе вкладка будет прыгать.
8. **Число документов до нажатия.** Посчитать сумму (элементы коллекций + обычные выходы) и вынести в подпись кнопки сохранения — [RunView.tsx:110](frontend/src/components/RunView.tsx:110), [:238](frontend/src/components/RunView.tsx:238). Формулировки — из дизайн-спеки. Повторное нажатие не должно дублировать (кнопка блокируется на время сохранения — сверить существующий `savingResult`).
9. **После успеха** — показать, сколько документов создано и куда перейти.
10. **Чипы созданных документов** — сворачивать в «N документов» с раскрытием, когда их много; порог взять из дизайн-спеки.
11. **Бейдж в списке скиллов** — [SkillsPanel.tsx](frontend/src/components/SkillsPanel.tsx): при коллекционном выходе не показывать точное число; формулировка — из дизайн-спеки. Потребуется признак «есть коллекционный выход» в `SkillOut`; если бэкенд из CATALOG-153 его не отдаёт — согласовать поле там же, а не выводить эвристикой на клиенте.
12. **Тесты** — [RunView.test.tsx](frontend/src/components/RunView.test.tsx): прогон с `[index, chapters×7]` даёт **две** вкладки; Arrow ходит по двум вкладкам; подпись кнопки несёт 8; прогон без коллекций рендерится как раньше. [ArtifactsPanel.test.tsx](frontend/src/components/ArtifactsPanel.test.tsx): переключатель сохраняется через PATCH, ошибка валидации видна на строке.
13. Прогнать все шесть команд из [CLAUDE.md](CLAUDE.md).

## Критерии приёмки (Definition of Done)

- [ ] В черновике выход помечается как коллекционный и это сохраняется через PATCH; ошибка валидации показана на строке.
- [ ] Прогон `split_by_chapters_with_index` на 7 глав показывает **две** вкладки (индекс и главы ×7), а не восемь; в подписи вкладки видно число элементов.
- [ ] Клавиатурная навигация по вкладкам ходит по выходам (две позиции), а не по девяти элементам.
- [ ] До нажатия сохранения видно число документов, которые будут созданы; повторное нажатие не дублирует.
- [ ] После успешного сохранения видно, сколько документов создано и куда перейти.
- [ ] Список созданных документов сворачивается в «N документов» с раскрытием.
- [ ] Бейдж в списке скиллов у скилла с коллекционным выходом не показывает точное число как достоверное.
- [ ] Прогон скилла без коллекций выглядит точно как до этой задачи; существующие тесты `RunView.test.tsx` зелёные.
- [ ] `serializeOutputs` для черновика без коллекций даёт прежний JSON.
- [ ] Только токены и примитивы [docs/ui-style-guide.md](docs/ui-style-guide.md), сырые палитры запрещены.
- [ ] Выполнены критерии визуальной приёмки из `02-CATALOG-154-ui-collection-outputs.design.md`.
- [ ] Frontend: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck`, `pnpm run test` — зелёные.
- [ ] Backend: `ruff check .`, `pytest` — зелёные.
