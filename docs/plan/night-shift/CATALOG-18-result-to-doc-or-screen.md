# CATALOG-18 — Выполнять в док или в окно (продумать способ вывода выполнения)

- **Задача Plane:** [CATALOG-18](https://app.plane.so/belchch/projects/catalog-app/work-items/18) (id: `4f719c1e-54d7-45c3-ab0f-3a633ee237a0`, state: In Progress)
- **Статус плана:** Analyzed
- **Цель:** Дать пользователю контроль над тем, куда попадает текстовый результат выполнения скилла. Реализовать два сценария применения скилла с **отдельными кнопками**: (1) «двухэтапный» — результат сначала выводится на экран, а документ создаётся по кнопке «Сохранить как новый документ»; (2) «сразу в док» — результат сразу сохраняется в документ, а на экран выводится подтверждение «документ создан» + путь/заголовок.

## Контекст

Сейчас применение скилла устроено так:

- `SkillsPanel.tsx:58-82` — для `committed`-скилла рисуется `<select>` выбора целевого (входного) документа и одна кнопка **«Применить»**, вызывающая `onApply(skillId, docId)`.
- `App.tsx:59-70` `handleApply` → `useSkills.apply` (`useSkills.ts:38-41`) → `applySkill(skillId, docId)` (`api.ts:90-96`) `POST /skills/{id}/apply` с `{ doc_id }`. Возвращает `run_id`, который кладётся в `activeRunId`.
- `App.tsx:91-92` — при `activeRunId` рисуется `RunView` (сплит: слева `TraceSteps`, справа результат).
- `useRunStream.ts:38-94` стримит WS-события прогона; на `finish` (`useRunStream.ts:84-87`) **читается только `status` и `finished`**.

Ключевой пробел — результат **уже сохраняется бэкендом, но фронт это игнорирует**:

- `apply.py:184-199` `_apply_core` при успехе **всегда** создаёт выходной документ: `create_document(kind="result_md", path="results/{out_id}.md")`, пишет туда `last_text` и выставляет `output_doc_id`. То есть «сценарий 2 (сразу в док)» фактически уже работает на сервере.
- `runs.py:123-129` `finish`-фрейм WS несёт `output_doc_id` (поле описано в `ws.ts:20-25`, но `useRunStream.ts` его не сохраняет).
- `GET /runs/{id}` (`runs.py:47-64`, `RunOut.output_doc_id`, `schemas.py:31`) тоже отдаёт `output_doc_id`.
- `GET /documents` (`documents.py:36-43`) возвращает **все** документы, включая `kind="result_md"` — т.е. результатные доки уже видны в `DocumentList`/`useDocuments`, но без подписи «это результат прогона».

Чего не хватает и почему «не удалось получить текстовый результат»:

1. Фронт не показывает `output_doc_id` и не даёт действий с результатом (`RunView.tsx:49-58` — только рендер `resultText`).
2. Нет способа **не** сохранять результат автоматически (для «двухэтапного» сценария): бэкенд всегда пишет `result_md`. Нужен флаг режима на apply.
3. Нет эндпоинта «создать документ из текста» для кнопки «Сохранить как новый документ»: `POST /documents` (`documents.py:16-33`) принимает только `UploadFile`, а `useDocuments` (`useDocuments.ts:30-34`) умеет только `upload(file)`.

## Затрагиваемые файлы

**Backend:**
- `backend/app/skills/apply.py` — параметр режима персиста (`persist: bool = True`) в `apply_skill`/`_apply_core`/`apply_skill_collect`; при `persist=False` пропускать блок `apply.py:184-199` (не создавать `result_md`), но всё равно отдавать `result_text` в `finish`/`ApplyResult`.
- `backend/app/api/runs.py` — прокинуть режим из запроса в `apply_skill(...)` (`runs.py:107-116`); эндпоинт **«сохранить превью в документ»** `POST /runs/{run_id}/save` (или `POST /documents/from-text`), создающий `result_md` из `result_text` прогона и возвращающий `DocumentOut`.
- `backend/app/api/schemas.py` — расширить `ApplyRequest` полем `persist: bool = True` (или `mode: Literal["persist","preview"]`); добавить `DocumentFromTextRequest { title, content }` (альтернатива для `save`).
- `backend/app/api/documents.py` — (вариант) добавить `POST /documents/text` для создания документа из строки (`create_document`, `repo_document.py:37`).
- `backend/tests/test_apply.py`, `backend/tests/test_api.py` — кейсы: apply с `persist=False` не создаёт `output_doc_id`; `POST /runs/{id}/save` создаёт документ с текстом результата.

**Frontend:**
- `frontend/src/api.ts` — `applySkill(skillId, docId, mode: 'persist' | 'preview')` (`api.ts:90-96`); новые обёртки `saveRunResult(runId)` / `createDocumentFromText(title, content)`; тип `ApplyRequest`.
- `frontend/src/hooks/useSkills.ts` — `apply(skillId, docId, mode)` (`useSkills.ts:38-41`).
- `frontend/src/hooks/useRunStream.ts` — в `finish` сохранять `output_doc_id` (`useRunStream.ts:84-87`); отдавать его в `UseRunStreamResult` (`useRunStream.ts:14-21`).
- `frontend/src/hooks/useDocuments.ts` — метод `createFromText`/оповещение `refresh()` после сохранения.
- `frontend/src/components/SkillsPanel.tsx` — **две кнопки** применения вместо одной (`SkillsPanel.tsx:58-82`): «Применить (в док)» и «Применить (на экран)»; прокидывать `mode` в `onApply`.
- `frontend/src/components/RunView.tsx` — в панели «Результат» (`RunView.tsx:48-59`): для режима `preview` кнопку **«Сохранить как новый документ»** (видна, когда `run.finished && status==='ok' && !outputDocId`); для режима `persist` — подтверждение «Документ создан: {title}» со ссылкой/выбором в `DocumentList`.
- `frontend/src/App.tsx` — `handleApply(skillId, docId, mode)` (`App.tsx:59-70`); обработчик `onSaveResult(runId)` → создать док → `docs.refresh()` + подсветить новый `currentDocId`; передать `mode`/`outputDocId` в `RunView`.

## План действий

1. **Бэкенд — режим персиста.** В `apply.py` добавить `persist: bool = True` в `_apply_core`/`apply_skill`/`apply_skill_collect`; обернуть блок `apply.py:184-199` в `if persist:`. В `schemas.py` расширить `ApplyRequest` (`persist: bool = True`). В `runs.py:107-116` передавать `persist=req.persist`. В обоих случаях `result_text` остаётся в `ApplyResult`/`finish`.
2. **Бэкенд — материализация превью в документ.** Добавить `POST /runs/{run_id}/save` (`runs.py`): прочитать `result_text` прогона (из `get_run`/trace или отдельного поля), через `create_document(kind="result_md", path="results/{new_id}.md", ...)` + запись файла создать документ, выставить `output_doc_id` в `skill_run`, вернуть `DocumentOut`. Альтернатива/дополнение — `POST /documents/text` (`documents.py`) для произвольного текста.
3. **Бэкенд — тесты.** `test_apply.py`: `apply_skill_collect(..., persist=False)` → `output_doc_id is None`, `result_text` заполнен. `test_api.py`: `POST /skills/{id}/apply` с `{persist:false}` → `finish.output_doc_id is None`; затем `POST /runs/{run_id}/save` → 200, документ появляется в `GET /documents`.
4. **Фронт — API-слой.** В `api.ts` обновить `applySkill` сигнатурой `mode` (→ `{ persist: mode==='persist' }`), добавить `saveRunResult(runId): Promise<DocumentOut>` и (опц.) `createDocumentFromText`. В `useSkills.apply` пробросить `mode`.
5. **Фронт — стрим.** В `useRunStream.ts` в `finish` ловить `output_doc_id`, добавить поле `outputDocId` в интерфейс и сбрасывать его вместе с остальным стейтом в эффекте (`useRunStream.ts:96-104`).
6. **Фронт — две кнопки.** В `SkillsPanel.tsx` для `committed`-скилла рисовать две кнопки: «Применить в док» (`onApply(s.id, docId, 'persist')`) и «Применить на экран» (`onApply(s.id, docId, 'preview')`). `onApply`-пропс получает третий аргумент `mode`.
7. **Фронт — панель результата.** В `RunView.tsx` принять `mode`/`onSaveResult`: при `preview && finished && status==='ok' && !outputDocId` показывать кнопку «Сохранить как новый документ» → `onSaveResult(runId)`; после сохранения (или сразу в `persist`) показывать «Документ создан: {title}» и обновлять список документов.
8. **Фронт — связка в App.** `handleApply(skillId, docId, mode)` запомнить `mode` прогона; `onSaveResult` создаёт документ, вызывает `docs.refresh()`, ставит `currentDocId` на новый. Передать `mode`, `outputDocId`, `onSaveResult` в `RunView`.
9. **Проверка end-to-end вручную.** Запустить `backend` + `frontend dev`, применить committed-скилл обеими кнопками: в `persist` — на экране «документ создан», док в списке; в `preview` — результат на экране, кнопка сохранения создаёт док и он появляется в списке.

## Критерии приёмки (Definition of Done)

- [ ] В `SkillsPanel` для каждого committed-скилла есть **две** отдельные кнопки применения: «в док» и «на экран».
- [ ] Режим «в док» (`persist`): после завершения прогона на экране видно подтверждение создания документа (заголовок/путь), а сам документ появляется в `GET /documents` и `DocumentList`.
- [ ] Режим «на экран» (`preview`): бэкенд **не** создаёт `result_md` автоматически (`output_doc_id is None` в `finish` и `GET /runs/{id}`), текстовый результат отображается в `RunView`.
- [ ] В режиме `preview` кнопка «Сохранить как новый документ» создаёт документ из результата и он появляется в `DocumentList` (без повторного прогона скилла).
- [ ] `finish`-фрейм корректно доносит `output_doc_id` (для `persist`) или `null` (для `preview`), и фронт его отображает.
- [ ] `backend`: `pytest backend/tests -k "apply or api"` зелёные, добавлены кейсы для `persist=False` и материализации превью.
- [ ] `backend`: `ruff check backend` и `mypy`/`pytest` проходят (см. `backend/pyproject.toml`).
- [ ] `frontend`: `npm run typecheck` (или `tsc --noEmit`) и `npm run lint` (если настроены в `frontend/`) проходят без ошибок.
- [ ] Ручная проверка двух сценариев на локальном стенде успешна.
