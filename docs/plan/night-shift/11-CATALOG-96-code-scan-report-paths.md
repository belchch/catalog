# CATALOG-96 — Показывать имя файла в отчёте о сканировании

- **Задача Plane:** [CATALOG-96](https://app.plane.so/belchch/projects/catalog-app/work-items/96) (id: `b9edfb7e-7f1d-405b-89f3-1454a726b9e9`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 11 · независимый
- **Цель:** Привести `ScanReport` к одному типу значений — относительным путям файлов от корня воркспейса — во всех группах (`added`, `updated`, `renamed`, `removed`), убрав внутренние id документов из отчёта. Отдельно решить и покрыть тестом контракт `POST /documents/reconcile`, который сейчас переиспользует `report.removed`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи; комментариев нет)_

### Отчёт скана: показывать пути файлов вместо id документов

**Проблема.** В модалке «Отчёт пересканирования» группы «Добавлено / Обновлено / Переименовано / Удалено» показывают внутренние id документов (`1a2db6143459436faa418883a6ed197d`), а «Пропущено» — относительные пути. Пользователю id ничего не говорит: он думает в терминах файлов в своей папке.

Дополнительно поле `added` неконсистентно между кодовыми путями:

- `preview_workspace` (пикер, `status=needs_confirm`) кладёт в `added` **пути**;
- `scan_workspace` (`POST /workspaces/rescan`) кладёт в `added` **id**.

Одно поле контракта несёт два разных типа значений.

**Решение.** `ScanReport` — везде относительные пути файлов от корня воркспейса.

- `added` / `updated` — `rel_path`;
- `removed` — путь удалённого документа (`deleted.path`);
- `renamed` — `"<старый путь> → <новый путь>"` (старый путь захватить до `update_document`, иначе он уже перезаписан);
- `skipped` — без изменений.

Тип схемы остаётся `list[str]` — фронтенд `ScanReportView` менять не нужно.

**Объём.**

- `backend/catalog/documents/scan.py` — `scan_workspace`: заменить `.append(*.id)` на пути; для renamed сохранить старый путь до апдейта.
- `backend/catalog/api/documents.py:56–62` — `POST /documents/reconcile` отдаёт `report.removed`, т.е. контракт меняется с id на пути. Либо принять смену (и поправить тест), либо перестать переиспользовать поле отчёта и собирать id для reconcile отдельно. Решение зафиксировать в задаче/PR.
- Тесты: `backend/tests/test_scan.py` (ассерты на `report.added`/`updated`/`renamed`/`removed` как на id, включая `get_document(db, i).path`), `backend/tests/test_api.py` (`test_workspaces_rescan_endpoint` мапит `body["added"]` в `/documents`; `test_documents_reconcile*` на `removed`), `backend/tests/test_workspace.py` (`manager.last_scan.added`).
- Фронтенд: кода не касается; проверить, что модалка и preview выглядят одинаково.

**Вне объёма.**

- Причина пропуска в графе «Пропущено» (скрытый / неподдерживаемый формат / нет доступа) — отдельная задача.
- Переход на структурированные элементы отчёта (`{ id, path, reason }`).

### Критерии приёмки
Перенесены в раздел ниже.

## Предыстория
_нет — комментариев к задаче не было._

## Контекст
- `ScanReport` — `backend/catalog/documents/scan.py:21-36`: пять полей `list[str]` и `as_dict()`. Тип менять не нужно, меняется только содержимое.
- Расхождение подтверждено. `preview_workspace` (`scan.py:115-123`) кладёт в `added` относительные пути (`:122`, `e.rel_path`), а `scan_workspace` — id: `report.updated.append(existing.id)` (`:166`), `report.renamed.append(rename_candidate.id)` (`:204`), `report.added.append(row.id)` (`:217`), `report.removed.append(deleted.id)` (`:228`). `skipped` в обоих путях — пути (`:121`, `:133`).
- Замены прямолинейные: в ветке обновления доступен `entry.rel_path` (`:141-167`); при создании — тот же `entry.rel_path` (`:207-217`); при удалении — `deleted.path` (`:226-228`).
- Единственное место, требующее аккуратности, — `renamed` (`:194-205`): `update_document(..., path=entry.rel_path, ...)` (`:195-202`) перезаписывает путь, поэтому старый путь надо взять из `rename_candidate.path` **до** вызова и сложить строку `"<старый> → <новый>"`. Кандидат берётся из среза `docs`, снятого до цикла (`:135`), так что значение в объекте доступно.
- Единственный потребитель отчёта, у которого сейчас контракт «id», — `POST /documents/reconcile`: `backend/catalog/api/documents.py:56-62` возвращает `{"removed": report.removed}`. После правки поле станет путями. Варианты: (а) принять смену контракта и обновить тест; (б) собрать id удалённых отдельно, не переиспользуя поле отчёта (например, вернуть из `scan_workspace` дополнительные данные или сделать отдельный проход). Решение обязательно зафиксировать в PR.
- Второй потребитель — `POST /workspaces/rescan` (отдаёт отчёт целиком) и `WorkspaceManager.last_scan`, который используется в тестах (`backend/tests/test_workspace.py:60-65`).
- Фронтенд действительно не требует правок: `ScanReportView` рендерит строки. Проверить только визуальное совпадение preview из пикера и модалки ре-скана.
- Тесты, которые придётся править (все ассерты сейчас построены на id):
  - `backend/tests/test_scan.py` — `:31` (`len(report.added) == 2`), `:34` (`{get_document(db, i).path for i in report.added}` — этот маппинг после правки становится ненужным и должен превратиться в прямое сравнение путей), `:58-59`, `:81`, `:97-99` (`report.renamed == [row.id]`), `:112` (`report.updated == [row.id]`), `:130-131`, `:150-152`, `:166` (`report.removed == [gone.id]`).
  - `backend/tests/test_api.py` — `test_reconcile_documents_endpoint` (`:330`), `test_workspaces_rescan_endpoint` (`:346`, мапит `body["added"]` в `/documents`).
  - `backend/tests/test_workspace.py` — `:60-65` (`manager.last_scan.added`).
- Пересечение: [CATALOG-91](docs/plan/night-shift/06-CATALOG-91-ui-picker-result-panel-loader.md) меняет отображение отчёта скана в модалке пикера (высота, скролл). Форматы значений там не затрагиваются, конфликтов по файлам нет — задачи независимы.
- Проверки: `ruff check .` и `pytest` из `backend/`; `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` из `frontend/` (для подтверждения, что фронт не тронут и не сломан).

## Затрагиваемые файлы
- `backend/catalog/documents/scan.py` — `scan_workspace`: `report.updated` (`:166`), `report.renamed` (`:204`), `report.added` (`:217`), `report.removed` (`:228`) переводятся на пути; для `renamed` старый путь захватывается до `update_document` (`:195`).
- `backend/catalog/api/documents.py` — `reconcile_documents_endpoint` (`:56-62`): реализовать выбранное решение по контракту `removed` (пути либо отдельный сбор id).
- `backend/tests/test_scan.py` — ассерты переводятся на пути, маппинг через `get_document(...).path` (`:34`) убирается; добавляется проверка формата `renamed` («старый → новый»).
- `backend/tests/test_api.py` — `test_reconcile_documents_endpoint` (`:330`) под выбранный контракт, `test_workspaces_rescan_endpoint` (`:346`) — сравнение путей вместо маппинга id.
- `backend/tests/test_workspace.py` — `:60-65`, `manager.last_scan.added` как пути.

## План действий
1. В `scan_workspace` заменить `report.updated.append(existing.id)` на `entry.rel_path` (`scan.py:166`).
2. Заменить `report.added.append(row.id)` на `entry.rel_path` (`:217`).
3. Заменить `report.removed.append(deleted.id)` на `deleted.path` (`:228`).
4. Для `renamed` (`:194-205`): до вызова `update_document` сохранить `rename_candidate.path` в локальную переменную, после апдейта добавить в отчёт строку `f"{old_path} → {entry.rel_path}"`. Разделитель — стрелка `→` из ТЗ, зафиксировать её как единственный формат.
5. Принять решение по `POST /documents/reconcile` (`documents.py:56-62`): либо контракт меняется с id на пути (тогда обновить тест и явно описать это в PR), либо собрать id удалённых документов отдельно, не переиспользуя `report.removed`. Записать решение и причину в описание PR.
6. Проверить остальные потребители отчёта (`POST /workspaces/rescan`, `WorkspaceManager.last_scan`) — убедиться, что нигде значения не используются как идентификаторы для последующих запросов.
7. Обновить `backend/tests/test_scan.py`: заменить ассерты на пути, убрать маппинг `get_document(db, i).path` (`:34`), добавить проверку формата строки `renamed`.
8. Обновить `backend/tests/test_api.py::test_workspaces_rescan_endpoint` (`:346`) и `test_reconcile_documents_endpoint` (`:330`) под выбранный контракт.
9. Обновить `backend/tests/test_workspace.py` (`:60-65`) на сравнение путей.
10. Вручную сверить: модалка ре-скана и preview в пикере показывают значения одного формата, hex-id нигде не осталось.
11. Прогнать из `backend/`: `ruff check .`, `pytest`. Из `frontend/`: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck`.

## Критерии приёмки (Definition of Done)
- [ ] В модалке ре-скана все группы показывают пути файлов, ни одного hex-id.
- [ ] «Переименовано» показывает старый и новый путь в формате `<старый> → <новый>`.
- [ ] Preview в пикере и отчёт ре-скана дают одинаковый формат значений.
- [ ] `skipped` не изменился.
- [ ] Тип полей схемы остался `list[str]`; фронтенд `ScanReportView` не изменён.
- [ ] Контракт `POST /documents/reconcile` явно решён, решение зафиксировано в PR и покрыто тестом.
- [ ] Тесты `test_scan.py`, `test_api.py`, `test_workspace.py` переведены на пути; маппинг id → path в тестах не нужен.
- [ ] Структурированные элементы отчёта (`{ id, path, reason }`) и причина пропуска не добавлялись (вне объёма).
- [ ] `ruff check .` и `pytest` из `backend/` зелёные; `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` из `frontend/` зелёные.
