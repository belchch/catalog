# Catalog — как запустить

[English](README-RUN.md) | **Русский**

Основной способ: **нативно** (Python venv / `uv tool install`, Node/pnpm для разработки UI). Docker для локальной работы с документами **не используй** — см. раздел в конце.

После этих шагов у тебя будут backend, UI и открытая папка-воркспейс с твоими файлами.

---

## Быстрый путь: `uv tool install` (из git)

PyPI пока не используем (имя пакета не зафиксировано). Ставится из репозитория; для сборки wheel нужны **uv**, **Node.js** и **pnpm** (hook собирает фронт в пакет).

```bash
uv tool install "git+https://github.com/belchch/catalog.git#subdirectory=backend"
catalog
```

Команда `catalog` поднимает uvicorn на `127.0.0.1:8000` и открывает браузер. Ключи можно задать через env (`OPENROUTER_API_KEY` / `ZAI_API_KEY`) или позже через API `/setup` (экран первого запуска — отдельный UI-шаг); persist — в глобальной `app.db`, не в `.env` CWD.

---

## Что нужно один раз (dev из исходников)

1. **Python 3.11+** (удобнее 3.13) — [https://www.python.org/downloads/](https://www.python.org/downloads/)
2. **Node.js** и **pnpm** — [https://nodejs.org/](https://nodejs.org/) · затем `npm install -g pnpm`
3. Ключ LLM-провайдера (env перекрывает persist):
  - по умолчанию **OpenRouter**: `OPENROUTER_API_KEY` (+ tool-capable `OPENROUTER_DEFAULT_MODEL`);
  - либо **z.ai** (`APP_PROVIDER=zai`, `ZAI_API_KEY`) — см. `backend/.env.example`.

---

## 1. Окружение backend

Из корня репозитория:

```bash
cd backend
cp .env.example .env
```

Открой `backend/.env` и задай минимум (для CI/dev; в продукте ключи могут жить в app-db):

- `OPENROUTER_API_KEY=...` (или ключ z.ai при `APP_PROVIDER=zai`)
- `OPENROUTER_DEFAULT_MODEL=...` — модель с function-calling / tool use

Остальное можно не трогать. Пути к документам в `.env` не задаются: папку выбираешь в UI.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn catalog.main:app --reload
# или: catalog --no-browser
```

Проверка: [http://localhost:8000/health](http://localhost:8000/health)

Оставь этот терминал запущенным.

---

## 2. Frontend

В **другом** терминале:

```bash
cd frontend
pnpm install
pnpm run dev
```

Открой в браузере: [http://localhost:5173](http://localhost:5173)

---

## 3. Открыть или создать папку-воркспейс

В UI выбери папку («Открыть воркспейс» / пикер папок):


| Папка                                    | Что произойдёт                                      |
| ---------------------------------------- | --------------------------------------------------- |
| Пустая (без маркера Catalog)             | Предложение **создать** воркспейс → подтверди       |
| С обычными файлами, без `.catalog`       | Показ превью индекса → **подтверди инициализацию**  |
| Уже воркспейс (есть `.catalog/index.db`) | Откроется сразу, индекс при необходимости обновится |


Документы остаются **обычными файлами в выбранной папке**. Служебное — только `.catalog/` (в т.ч. `index.db`); руками править не нужно.

Глобальные настройки и список известных воркспейсов лежат в каталоге данных ОС (на macOS — `~/Library/Application Support/catalog`, иначе `~/.local/share/catalog`), не рядом с исходниками и не в Docker-томе.

---

## Остановка

В каждом терминале (backend / frontend) — **Ctrl+C**.

---

## Сквозной прогон (golden path)

Нужны настроенный `backend/.env` и samples в корне репо (`samples/golden.docx`, `samples/golden2.docx`). Скрипт сам создаёт временную папку-воркспейс с `.catalog/index.db` и гоняет цикл ingest → план → скилл → apply:

```bash
cd backend
source .venv/bin/activate   # если ещё не активирован
python scripts/golden_run.py
```

Успех: в конце `=== GOLDEN RUN PASSED ===` и JSON-отчёт.

---

## Если что-то не работает

| Симптом                           | Что делать                                                    |
| --------------------------------- | ------------------------------------------------------------- |
| Нет ключа / ошибки LLM            | Проверь `backend/.env`: ключ задан; модель умеет tool use     |
| Порт **8000** занят               | Останови другой процесс или `uvicorn ... --port 8001`         |
| Порт **5173** занят               | Vite предложит другой порт или останови конфликтующий процесс |
| `pnpm: command not found`         | `npm install -g pnpm`                                         |
| Backend не стартует после install | Активируй venv, из `backend/` снова `pip install -e ".[dev]"` |
| HTTP **409** `workspace not open` | В UI ещё не открыта папка — открой воркспейс (шаг 3)          |
| 409 при смене папки               | Дождись окончания активного прогона скилла, затем переключи   |


Если ничего не помогает — пришли вывод терминала (backend и/или frontend).

---

## Устарело для локального запуска: Docker

Docker-обвязка вынесена в `deploy/` (`deploy/docker-compose.yml`, том `catalog-data` → `/data`, `deploy/Catalog.command` / `deploy/Build.command`) — это **не** продуктовый сценарий для работы с документами на своём компьютере. Named volume больше не место «где лежат мои файлы».

Скрипты и образ оставлены как задел под возможный серверный деплой и могут отставать от кода. Для повседневной локальной работы используй нативный путь выше.
