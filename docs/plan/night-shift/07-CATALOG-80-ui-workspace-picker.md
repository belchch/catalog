# CATALOG-80 — UI: пикер и переключение воркспейсов, ре-скан с отчётом

- **Задача Plane:** [CATALOG-80](https://app.plane.so/belchch/projects/catalog-app/work-items/80) (id: `19adb538-8c00-47f4-ad5e-baf6b21e8f9c`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** Дать пользователю выбрать и переключить папку-воркспейс, увидеть ре-скан с отчётом и пустое состояние «воркспейс не открыт». Upload по-прежнему кладёт файл в открытую папку.

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — комментариев не было)_

Фронт для модели «воркспейс = папка» поверх API воркспейсов.

- Пикер: дерево через `GET /fs/browse`, список недавних из реестра; три состояния: пустая папка → «создать воркспейс»; папка с файлами → отчёт + «сделать воркспейсом и проиндексировать»; невалидная → отказ с объяснением.
- Индикатор активного воркспейса (путь) + переключатель; при активных ранах — понятное сообщение о блокировке (409).
- Кнопка «пересканировать» с отчётом added/updated/renamed/removed/skipped.
- Пустое состояние приложения «воркспейс не открыт».
- `frontend/src/api.ts`, `App.tsx`, `DocumentList.tsx` — новые эндпоинты; upload остаётся.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

Предусловие: CATALOG-79 (HTTP API). Дизайн-спека — фаза `catalog-designer` → `CATALOG-80.design.md`.

## Контекст

Сейчас воркспейс зашит на бэкенде. UI показывает статичный «проект»:

- `App.tsx:463–464` — `.catalog-project-title` с текстом «Catalog»;
- `App.tsx:541–543` — футер «Catalog workspace».

Хуки при маунте сразу бьют в бизнес-API: `useDocuments` (`hooks/useDocuments.ts:36–38`), аналогично сессии и скиллы. После 77/79 без открытой папки это будет **409**. Нужно: не рефрешить документы/сессии/скиллы, пока `GET /workspaces/current` пустой; 409 в списке документов не показывать как «ошибка сети».

`ApiError` (`api.ts:56–67`) уже несёт `status` и `detail` — 409 от open можно показать текстом бэкенда.

`jsonFetch` (`api.ts:193–199`) — сюда добавить обёртки: `listWorkspaces`, `getCurrentWorkspace`, `openWorkspace(path, confirm)`, `rescanWorkspace`, `browseFs(path)`. Типы — по схемам 79.

`DocumentList.tsx` — upload через `docs.upload` (`POST /documents`). После смены модели файл пишется в папку воркспейса (78); UI upload оставить. Рядом — кнопка ре-скана (либо в actions `CollapsibleSection` «Документы», `App.tsx:502–510`).

Пикер: нативного `<input type="folder">` в браузере нет как системного folder-picker к произвольному `$HOME`. ТЗ явно: дерево через `/fs/browse` + недавние. Модалка в духе `SkillTrackPicker` / `SessionTimeoutModal` (оверлей + панель).

Пустое состояние: main/chat не должен притворяться, что сессия живая, пока папка не открыта — заглушка с CTA «Открыть папку».

## Затрагиваемые файлы

- `frontend/src/api.ts` — типы и клиент workspaces/fs/rescan.
- `frontend/src/hooks/useWorkspace.ts` (новый) — current, recents, open/confirm, browse, rescan, ошибка 409.
- `frontend/src/components/WorkspacePicker.tsx` (новый) — дерево + недавние + три состояния open.
- `frontend/src/components/WorkspaceBar.tsx` (новый, опционально) — индикатор пути, открыть пикер, rescan.
- `frontend/src/App.tsx` — встроить бар вместо статичного «Catalog»; empty state; не грузить docs/sessions/skills без current.
- `frontend/src/components/DocumentList.tsx` — не ломать upload; при необходимости прокинуть rescan/отчёт.
- `frontend/src/hooks/useDocuments.ts` / `useSessions.ts` / `useSkills.ts` — не дергать API при отсутствии воркспейса (проп/флаг из App или общий guard).

Backend не трогать.

## План действий

1. **API-клиент.** Типы `WorkspaceOut`, `WorkspaceOpenResult` (`ok` | `needs_init` | `needs_confirm`), `ScanReport`, `FsEntry`. Методы под 79. 409 → `ApiError`.
2. **Хук `useWorkspace`.** На старте `GET /workspaces/current` + `GET /workspaces`. `open(path, confirm)` обрабатывает три status. После успешного open — колбек, чтобы App рефрешнул docs/sessions/skills.
3. **Пикер.** Модалка: недавние сверху; дерево `browse(path)` с навигацией вверх (не выше корня API). Клик по папке → `open(confirm=false)`:
   - `needs_init` → кнопка «Создать воркспейс» (`confirm=true`);
   - `needs_confirm` → показать preview скана + «Сделать воркспейсом и проиндексировать»;
   - ошибка схемы/пути → текст, без кнопки подтверждения;
   - `ok` → закрыть, обновить current.
4. **Индикатор.** Заменить `.catalog-project-title`: путь current или «Папка не открыта»; клик открывает пикер. 409 на switch — баннер/notice с `detail` (не молчаливый fail).
5. **Ре-скан.** Кнопка у секции «Документы» или в баре. Показать отчёт (added/updated/renamed/removed/skipped); затем `docs.refresh()`.
6. **Empty state.** Если current нет: сайдбар-секции сессий/доков/скиллов пустые или скрыты, main — CTA открыть пикер. Хуки не спамят 409.
7. Upload без изменений контракта, disabled пока нет current.
8. `pnpm run build` / `lint` / `typecheck`. Визуал по `CATALOG-80.design.md`.

## Критерии приёмки (Definition of Done)

- [ ] Можно выбрать папку с документами в пикере, подтвердить индексацию — список документов заполняется.
- [ ] Недавние воркспейсы открываются без повторного обхода дерева.
- [ ] Пустая папка предлагает «создать воркспейс»; невалидная — объясняет отказ.
- [ ] Переключение на другую папку и обратно: документы/сессии соответствуют папке.
- [ ] При 409 (активный ран) пользователь видит понятное сообщение, текущая папка не сбрасывается.
- [ ] «Пересканировать» показывает отчёт added/updated/renamed/removed/skipped.
- [ ] Без открытого воркспейса — явное пустое состояние, нет сырых 409 в списках.
- [ ] Upload документа работает в открытой папке.
- [ ] Из `frontend/`: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` зелёные.
- [ ] Визуальная приёмка — по `CATALOG-80.design.md`.
