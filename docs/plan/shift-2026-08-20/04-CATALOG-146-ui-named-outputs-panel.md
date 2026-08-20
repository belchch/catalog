# CATALOG-146 — ui: панель выходов в черновике и несколько результатов прогона

- **Задача Plane:** [CATALOG-146](https://app.plane.so/belchch/projects/catalog-app/work-items/146) (id: `82a2aa15-aecc-47e8-ac38-f04c32644cbc`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 04 · blocked_by CATALOG-143 · blocked_by CATALOG-144 · blocked_by CATALOG-145 · blocked_by CATALOG-147
- **Цель:** Показать объявленные выходы в черновике и несколько результатов прогона. Backend-контракт уже есть в 144/145/147 — здесь только frontend.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: ui. Порядок: после рантайма и персиста.

`RunView` показывает одно полотно и одну кнопку «Сохранить как новый документ» (`RunView.tsx:126`). `useRunStream` берёт текст из кадра `finish` (`useRunStream.ts:193-199`). `RunOut` в `api.ts:33-37` знает только `output_doc_id` и `result_text`. В `ArtifactsPanel` карточки выходов нет.

Что сделать:

1. Карточка OUTPUTS в `ArtifactsPanel`: список «ключ — описание», правка через PATCH, ошибка валидации на карточке (как script). Первый в списке помечен как основной.
2. `RunView`: вкладки по артефактам, primary первый, подписи из описаний. Один выход — вкладок нет.
3. Сохранение: кнопка пишет всю пачку («Сохранить как новые документы» при N > 1). После успеха — сколько документов и куда перейти.
4. После прогона «в док»: чипы/карточки созданных документов вместо ссылки на один.
5. `api.ts` / `useRunStream.ts`: `output_doc_ids` и артефакты в `RunOut` и в `finish`; старые прогоны без новых полей — как раньше.
6. Список скиллов: бейдж с числом выходов при N > 1.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

Предусловия: `CATALOG-144` (артефакт + REST), `CATALOG-145` (`RunOut` / save пачки / WS finish), `CATALOG-147` (agent тоже пишет тот же контракт). Парного code-плана у этого тикета нет — backend в соседних тикетах.

- `frontend/src/api.ts:11-26` — `SkillOut` без числа выходов (бейдж потребует поле с backend `SkillOut` в `api/schemas.py:75+`, иначе считать не из чего).
- `frontend/src/api.ts:28-39` — `RunOut` без `output_doc_ids` и артефактов.
- `frontend/src/api.ts:619` — `ArtifactType` без `outputs`; `patchArtifact` (`859`) типизирован тем же union.
- `frontend/src/components/ArtifactsPanel.tsx:36-48, 206+` — карточки meta/prompt/script/steps; колбэки `onSavePrompt` / `onSaveScript` / `onSaveMeta`.
- `frontend/src/components/RunView.tsx:31-36, 112-151` — одно полотно, одна кнопка save, один `outputDocId`.
- `frontend/src/hooks/useRunStream.ts:193-199` — из `finish` читает `output_doc_id` и `result_text`.
- `frontend/src/ws.ts:66-73` — кадр `finish` без пачки.
- `frontend/src/components/SkillsPanel.tsx:434-492` — бейджи `tags` + arity; места под число выходов нет.
- `frontend/src/App.tsx:871, 1017` — монтирует `RunView` и `ArtifactsPanel`.
- `docs/ui-style-guide.md` — только токены и примитивы, сырые палитры запрещены.

Тесты-якоря: `frontend/src/components/ArtifactsPanel.test.tsx`, `frontend/src/hooks/useRunStream.ts` (если есть тест), `RunView` / `SkillsPanel` тесты — добавить при наличии соседей.

## Затрагиваемые файлы
- `frontend/src/api.ts` — `ArtifactType`, `RunOut`, `SkillOut`, типы артефактов прогона.
- `frontend/src/ws.ts` — поля кадра `finish`.
- `frontend/src/hooks/useRunStream.ts` — принять пачку.
- `frontend/src/components/ArtifactsPanel.tsx` (+ тест) — карточка OUTPUTS.
- `frontend/src/components/RunView.tsx` — вкладки, save пачки, чипы документов.
- `frontend/src/components/SkillsPanel.tsx` — бейдж N>1.
- `frontend/src/App.tsx` — прокинуть save/patch выходов.
- `backend/catalog/api/schemas.py` — только если `SkillOut` ещё не отдаёт число/список выходов (минимальный контракт для бейджа; основное API — 144/145).

## План действий
1. Расширить клиентские типы: `outputs` в `ArtifactType`; `output_doc_ids` + артефакты в `RunOut` и `finish`; опциональное поле числа выходов в `SkillOut` (если backend 145 его ещё не отдал — добавить в схему, не изобретать клиентский парсинг `config_json`).
2. Карточка OUTPUTS по образцу script: список ключ/описание, PATCH, `is_valid`/`error` на карточке, пометка primary на первом.
3. `useRunStream`: читать новые поля; отсутствие полей = один `result_text`.
4. `RunView`: N=1 — текущий вид; N>1 — вкладки (primary открыт), кнопка «Сохранить как новые документы», после persist — чипы всех документов.
5. `SkillsPanel`: бейдж с числом выходов только при N>1, токены из style-guide.
6. Тесты карточки, вкладок, save пачки, регресс одного выхода.

## Критерии приёмки (Definition of Done)
- [ ] В черновике видны объявленные выходы с описаниями и правятся вручную; ошибка валидации показана на карточке.
- [ ] Прогон с двумя выходами показывает оба результата с подписями; primary открыт по умолчанию.
- [ ] Сохранение создаёт все документы за одно нажатие; повторное нажатие не дублирует.
- [ ] Прогон старого скилла с одним выходом выглядит точно как раньше — без лишних вкладок и бейджей.
- [ ] Только токены и примитивы `docs/ui-style-guide.md`, сырые палитры запрещены.
- [ ] Frontend: `pnpm run build`, `lint`, `typecheck`, `test` зелёные.
