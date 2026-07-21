# CATALOG-65 — Поддержка ingest PDF / CSV / XLSX: загрузка, извлечение текста, доступ агенту и script-скилам

- **Задача Plane:** [CATALOG-65](https://app.plane.so/belchch/projects/catalog-app/work-items/65) (id: `ac31e9bf-e44a-498d-8b7a-9d9eaed4c225`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** Обновить UI загрузки документов, чтобы пользователь мог выбирать файлы `.pdf`, `.csv`, `.xlsx` в дополнение к `.md` и `.docx`.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — комментариев к задаче не было)_

**Frontend scope (этот план):**
- `DocumentList`: `accept` и подпись кнопки — `.md,.docx,.pdf,.csv,.xlsx`.
- Список/карточка документа корректно показывает kind (если kind где-то отображается — не ломать).

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

Текущий UI жёстко ограничивает выбор файлов:
- `frontend/src/components/DocumentList.tsx:33` — текст кнопки: `+ Загрузить .md / .docx`
- `frontend/src/components/DocumentList.tsx:37` — `accept=".md,.docx"`
- `frontend/src/components/DocumentList.tsx:57-59` — badge `kind` рендерится динамически из `d.kind` (uppercase), новые kinds `PDF`, `CSV`, `XLSX` отобразятся автоматически без изменений

Этот план зависит от code-плана `docs/plan/next-shift/CATALOG-65-code-pdf-csv-xlsx-ingest.md` (backend должен принимать новые форматы до того, как UI начнёт их отправлять).

## Затрагиваемые файлы

- `frontend/src/components/DocumentList.tsx` — расширить `accept` и обновить текст кнопки

## План действий

1. В `frontend/src/components/DocumentList.tsx:37` изменить `accept=".md,.docx"` на `accept=".md,.docx,.pdf,.csv,.xlsx"`.
2. В `frontend/src/components/DocumentList.tsx:33` обновить текст кнопки: заменить `+ Загрузить .md / .docx` на `+ Загрузить документ`.
3. Убедиться, что badge kind (`d.kind` на строке 58) рендерится корректно для новых значений — это работает автоматически (строка выводится как есть, uppercase), изменений не требуется.
4. Запустить `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` из `frontend/` — всё зелёное.

## Критерии приёмки (Definition of Done)

- [ ] `accept` включает `.md,.docx,.pdf,.csv,.xlsx`
- [ ] Текст кнопки не перечисляет форматы (или перечисляет все пять)
- [ ] Kind-badge корректно показывает `PDF`, `CSV`, `XLSX` для загруженных документов
- [ ] `pnpm run build` зелёный
- [ ] `pnpm run lint` зелёный
- [ ] `pnpm run typecheck` зелёный
- [ ] md/docx без регрессии (загрузка и отображение работают как раньше)