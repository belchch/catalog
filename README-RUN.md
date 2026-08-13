# Catalog — как запустить

Catalog работает с **папкой на твоём компьютере**: документы лежат там, куда ты их положил. Основной способ запуска — **нативный** (Python + Node), без Docker.

---

## Что нужно один раз

1. **Python 3.11+** (лучше 3.13) — https://www.python.org/downloads/
2. **Node.js** и **pnpm** (для интерфейса) — https://nodejs.org/ · `npm install -g pnpm`
3. Ключ **OpenRouter** (`OPENROUTER_API_KEY`) — впиши в `backend/.env` (см. ниже)

---

## Запуск (основной путь)

### Backend

```bash
cd backend
cp .env.example .env
# отредактируй .env: OPENROUTER_API_KEY=... и при необходимости OPENROUTER_DEFAULT_MODEL=...

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload      # API: http://localhost:8000  ·  health: /health
```

### Frontend

В другом терминале:

```bash
cd frontend
pnpm install
pnpm run dev                       # http://localhost:5173
```

Открой в браузере `http://localhost:5173` — это интерфейс Catalog.

### Остановка

В каждом терминале (backend / frontend) — **Ctrl+C**.

---

## Где мои документы

Документы — в **папке-воркспейсе**, которую ты открываешь в приложении (обычная папка на диске).

- Каталог не хранит «твои файлы» внутри Docker-тома и не требует искать данные рядом со скриптом запуска.
- Служебные данные воркспейса — в подпапке `.catalog/` (в т.ч. `index.db`). Её не нужно править вручную.
- Глобальные настройки и список известных воркспейсов живут отдельно от папки с документами (см. ADR-0016).

---

## Если что-то не работает

| Симптом | Что делать |
|---|---|
| `OPENROUTER_API_KEY` / ошибки LLM | Проверь `backend/.env`: ключ задан, модель умеет tool use |
| Порт 8000 или 5173 занят | Останови другой процесс или смени порт в команде запуска |
| `pnpm: command not found` | Установи pnpm: `npm install -g pnpm` |
| Backend не стартует после `pip install` | Активируй venv и повтори `pip install -e ".[dev]"` из `backend/` |

Если ничего не помогает — пришли вывод терминала (backend и/или frontend) тому, кто дал тебе проект.

---

## Опционально: Docker

Docker Desktop + `Catalog.command` — **не** основной способ. Имеет смысл только если так удобнее упаковать окружение; данные в модели workspace-as-folder всё равно должны жить в выбранной папке пользователя, а не в томе `catalog-data` как единственном хранилище.

Скрипты `Catalog.command` / образ в репозитории могут ещё существовать для совместимости — для повседневной работы предпочитай нативный запуск выше.
