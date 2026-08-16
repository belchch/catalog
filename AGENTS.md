# Catalog — контекст для разработки

Catalog — локальное приложение для создания и выполнения переиспользуемых процессов обработки документов.

## Стек

| Слой | Технология |
|---|---|
| Backend | Python 3.11+, FastAPI, WebSocket, httpx, pydantic |
| LLM | OpenRouter и z.ai через общий provider-слой |
| Хранилище | Файлы воркспейса и `.catalog/index.db` |
| Frontend | React, Vite, TypeScript, Tailwind CSS |
| Движок | Один function-calling agent loop |

## Основные решения

- Планировщик и выполнение agent-скилла используют один agent loop.
- Скилл хранится как замороженный конфиг.
- Скилл собирается из артефактов в момент согласия пользователя.
- Воркспейс — выбранная пользователем папка.
- Файловая система служит источником контента, SQLite — пересоздаваемым индексом.
- Результаты сохраняются как документы.
- Встроенные проверки выполняются детерминированным реестром.
- Неизвестные инструменты и проверки обрабатываются fail-closed.

Полный индекс решений: [`docs/adr/README.md`](docs/adr/README.md).

## Структура

```text
Catalog/
  backend/
  frontend/
  docs/
    adr/
    plan/
    verification-checks.md
  README.md
  README-RUN.md
```

Рабочие документы пользователя находятся в выбранном воркспейсе, а не в дереве исходников. Маркер воркспейса — `.catalog/index.db`.

## Запуск для разработки

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn catalog.main:app --reload
```

Frontend:

```bash
cd frontend
pnpm install
pnpm run dev
```

Полная инструкция: [`README-RUN.md`](README-RUN.md).

## Проверки

Backend:

```bash
cd backend
ruff check .
pytest
```

Frontend:

```bash
cd frontend
pnpm run build
pnpm run lint
pnpm run typecheck
pnpm run test
```

Сквозной приёмочный прогон:

```bash
cd backend
python scripts/golden_run.py
```

## Инварианты

- Новый инструмент или проверка регистрируется в соответствующем реестре.
- Значимое архитектурное решение оформляется ADR и добавляется в индекс.
- Ключи LLM хранятся только в переменных окружения или глобальной базе настроек.
- Произвольное выполнение пользовательского кода вне предусмотренного runtime не добавляется без отдельной модели изоляции.
- Основной способ запуска — нативный; Docker не является целевым local-first сценарием.

## Перед изменениями

1. Прочитать относящиеся к задаче ADR.
2. Проверить планы в `docs/plan/`.
3. Для проверок результата свериться с `docs/verification-checks.md`.
4. Для UI свериться с `docs/ui-style-guide.md`.
