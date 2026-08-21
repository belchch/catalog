# Pipeline contract — Catalog

Контракт пайплайна `shift` (плагин `shift@belch`, маркетплейс `belch` →
`~/AIProjects/shift`). Всё проектное — здесь; промпты ролей проектного не знают.

Заголовки разделов фиксированы: роли ищут их по имени. Не переименовывать.

## Тикеты

- **Префикс:** `CATALOG`
- **Имя файла плана:** `NN-CATALOG-<n>-<type>-<slug>.md`
- **Каталог планов:** `docs/plan/` (прогон кладётся в подкаталог `<RUN_NAME>/`)

## Git

- **Базовая ветка:** `main`

## Команды проверок

Гонять **по всему коду**, не только по диффу. Непрогнанная проверка не считается зелёной.

| id | каталог | команда | блокирующая |
|---|---|---|---|
| ruff | `backend/` | `ruff check .` | да |
| pytest | `backend/` | `pytest` | да |
| build | `frontend/` | `pnpm run build` | да |
| lint | `frontend/` | `pnpm run lint` | да |
| typecheck | `frontend/` | `pnpm run typecheck` | да |
| test | `frontend/` | `pnpm run test` | да |

`pnpm run test` (`vitest run`) — такая же обязательная проверка, как остальные три
фронтовых.

## UI

- **Пути UI-кода:** `frontend/src/`
- **Стек:** React 19 + Vite + TypeScript + Tailwind v3
- **Стайлгайд:** `docs/ui-style-guide.md`
- **Расширение файлов в `location`:** `.tsx`

## Документы

- **ADR:** `docs/adr/` (индекс — `docs/adr/README.md`)
- **Конвенции:** `AGENTS.md`, `CLAUDE.md`, `docs/verification-checks.md`

## Дополнительные критерии DoD

- новый инструмент или проверка зарегистрированы в соответствующем реестре;
- значимое архитектурное решение оформлено ADR и добавлено в индекс `docs/adr/README.md`;
- тест проверяет заявленное на продовом пути данных: зелёный тест, обходящий
  нормализацию или иной боевой слой, — замечание, а не приёмка;
- ключи LLM — только переменные окружения или глобальная база настроек, в коде,
  промптах и файлах состояния их нет.

## Трекер

- **Тип:** Plane
- **Workspace:** `belchch`
- **Project id:** `84997489-c485-4448-9ebe-0a06c4fa3cbc`
- **Project identifier:** `CATALOG`
- **Статусы:** брать `Todo`, переводить в `In Progress`
- **Ключ API:** `mcpServers.plane.env.PLANE_API_KEY` в `~/.claude.json`
