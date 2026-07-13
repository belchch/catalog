# План первого среза — шаги

Декомпозиция MVP «Каталог» на независимо проверяемые шаги. Каждый шаг — отдельный файл `step-NN-*.md` с целью, контрактами, командами и критерием приёмки.

| Шаг | Тема | Статус | Файл |
|-----|------|--------|------|
| 01 | Инициализация проекта (каркас монорепо) | Done | [step-01-initialization.md](step-01-initialization.md) |
| 02 | LLM-провайдер (OpenRouter: list_models, complete, tool-call) | Pending (нужен API-ключ) | [step-02-llm-provider.md](step-02-llm-provider.md) |
| 03 | Агент-луп (function-calling цикл, реестр инструментов, trace) | pending | — |
| 04 | Хранилище + инструменты документов (FS, SQLite, ingest, list/read) | pending | — |
| 05 | verify + apply_skill (реестр проверок, retry, результат=Document) | pending | — |
| 06 | Backend API (FastAPI: documents, planner WS, skill build/commit/apply, run streaming) | pending | — |
| 07 | UI (React: чат-планировщик, доки, создать/коммит/применить, результат + стриминг) | pending | — |
| 08 | Золотой прогон + полировка | pending | — |

## Ссылки
- Верхний план среза (контракты, схема БД, API, failure modes): `~/.local/share/kilo/plans/1783886041469-first-slice-skill-loop.md`.
- Решения: `../adr/README.md`.
- Реестр проверок: `../verification-checks.md`.

## Правила работы по шагам
- Шаг считается сделанным, когда пройден его **критерий приёмки** (команда + наблюдаемый результат), а не по факту написания кода.
- В рамках шага не меняем схему/контракты предыдущих без ADR.
- После шага: обновить статус в этой таблице и при необходимости дописать «как запустить» в корневой `README.md`.
