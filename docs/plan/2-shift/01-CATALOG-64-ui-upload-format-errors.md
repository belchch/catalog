# CATALOG-64 — Загрузка файлов: проверять содержимое и давать внятную ошибку формата (.xls / .ods / .tsv)

- **Задача Plane:** [CATALOG-64](https://app.plane.so/belchch/projects/catalog-app/work-items/64) (id: `25aa4eec-1564-4016-8896-e1146283941e`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 01 · предусловие: 00 (code того же тикета)
- **Цель:** Дать выбрать `.xls`/`.ods`/`.tsv` в пикере и показать пользователю человекочитаемый `detail` с бэкенда (подсказка пересохранить / битый файл), а не сырой `Error.message`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

Frontend-часть того же тикета:

1. Добавить `.xls`, `.ods`, `.tsv` в `accept`, чтобы файл можно было выбрать и получить внятный ответ вместо «файла не видно».
2. Проверить, что `detail` из ответа доходит до UI и показывается пользователю (`DocumentList.tsx:28-29` кладёт `message` в состояние).

Критерии: текст подсказки виден в UI; валидные форматы грузятся как раньше; `pnpm run build / lint / typecheck / test`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/2-shift/00-CATALOG-64-code-upload-content-validation.md` — бэкенд отдаёт 400 с человекочитаемым `detail`.

`accept` сейчас `".md,.docx,.pdf,.csv,.xlsx"` (`frontend/src/components/DocumentList.tsx:52`) — совпадает с whitelist, поэтому `.xls` в пикере не виден.

Ошибка upload: `setErr(e instanceof Error ? e.message : String(e))` (`DocumentList.tsx:28-29`). У `ApiError` (`frontend/src/api.ts:57-67`) `message` = `"400 Bad Request: {json}"`, а чистый текст лежит в `e.detail`. Для этого уже есть `extractApiDetail` (`api.ts:104-116`) — им пользуются `useWorkspace` и `WorkspacePicker`, `DocumentList` нет.

`docs.upload` типизирован в `frontend/src/hooks/useDocuments.ts:10`.

## Затрагиваемые файлы
- `frontend/src/components/DocumentList.tsx` — расширить `accept`; показывать `extractApiDetail(e)`.
- При необходимости короткий тест на разбор ошибки, если в фронте уже есть паттерн для `DocumentList` / `extractApiDetail`; иначе ручная проверка достаточна (единственный автотест фронта — `usePlannerSession.test.ts`).

## План действий
1. `accept=".md,.docx,.pdf,.csv,.xlsx,.xls,.ods,.tsv"`.
2. В `catch` писать в `err` результат `extractApiDetail(e)`, не `e.message`.
3. Не менять раскладку списка и disabled-состояния.
4. Проверки из `frontend/`: build, lint, typecheck, test.

## Критерии приёмки (Definition of Done)
- [ ] В пикере можно выбрать `.xls` / `.ods` / `.tsv`.
- [ ] После отказа бэкенда под плашкой виден текст `detail` (подсказка пересохранить / битый файл), не сырой JSON.
- [ ] Успешная загрузка поддерживаемых форматов без регрессии UI.
- [ ] Зелёные: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck`, `pnpm run test` из `frontend/`.
