# Catalog — ИИ-агент для аналитика/архитектора

Платформа-оболочка: пользователь в чате составляет план обработки документа, превращает его в переиспользуемый **скилл** и применяет к документам. MVP («первый срез») — один сквозной цикл, чтобы «почувствовать продукт».

> Этот README — точка быстрого погружения для **новой сессии ИИ-агента**. См. раздел «Новому ИИ-агенту» внизу.

## Стек
| Слой | Технология |
|------|-----------|
| Backend | Python 3.11+ · FastAPI (+WebSocket) · httpx · pydantic |
| LLM | OpenRouter (единый шлюз, selector моделей, pin провайдера, streaming) |
| Хранилище | Воркспейс = папка пользователя; контент на ФС; `.catalog/index.db` (бизнес-данные); глобально — настройки и реестр воркспейсов |
| Frontend | React (Vite) + TypeScript + Tailwind CSS |
| Движок скиллов | один function-calling агент-луп |

## Архитектура (кратко)
- **Движок** — один function-calling агент-луп; планировщик (чат) и исполнение скилла используют один и тот же цикл.
- **Скилл** = замороженный конфиг агента (`system_prompt`, `allowed_tools`, `model`, `temperature=0`, `verify_checks`).
- **Поток**: план в чате → система показывает задание → согласие → построение скилла + применение → ревью → коммит/итерация.
- **Хранилище**: воркспейс = открытая папка пользователя (документы — файлы там, где их положили). Бизнес-состояние — SQLite `.catalog/index.db` внутри папки; глобально — настройки приложения и реестр воркспейсов (ADR-0016). SQLite — пересобираемый индекс над ФС.
- **Проверки** — детерминированный реестр (`docs/verification-checks.md`).
- **Доставка** — нативный запуск (venv + uvicorn / pnpm) как основной способ; Docker для локали устарел (см. `README-RUN.md`).

Полный список решений — в `docs/adr/` (ADR-0001…0016).

## Структура репозитория
```
Catalog/
  backend/      # FastAPI (Python)
  frontend/     # React + Vite + Tailwind
  docs/
    adr/                 # архитектурные решения (ADR)
    plan/                # декомпозиция среза по шагам
    pre-design/          # исходные транскрипты (opus, fable)
    verification-checks.md
  README.md
  README-RUN.md          # запуск для пользователя (нативный — основной)
```

> Рабочие документы пользователя — в **выбранной папке-воркспейсе** (не в дереве исходников). Маркер воркспейса: `.catalog/` + `index.db`. Каталог `workspace/` в репо, если есть, — наследие/dev, не целевая модель данных.

## Текущий статус
Первый срез. Текущий шаг — см. `docs/plan/` (индекс шагов). Верхний план среза: `~/.local/share/kilo/plans/1783886041469-first-slice-skill-loop.md`.

## Быстрый старт (после инициализации)
```bash
# env (backend): скопируй шаблон и впиши ключи (env перекрывает persist в app.db)
cd backend
cp .env.example .env
#   OPENROUTER_API_KEY=...        # ключ OpenRouter (или задай через /setup)
#   OPENROUTER_DEFAULT_MODEL=...   # tool-capable модель (см. ниже)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn catalog.main:app --reload  # http://localhost:8000/health

# frontend
cd frontend
pnpm install
pnpm run dev                       # http://localhost:5173
```

Установка без клона (wheel из git, нужен Node/pnpm на машине сборки):

```bash
uv tool install "git+https://github.com/belchch/catalog.git#subdirectory=backend"
catalog
```

> `OPENROUTER_DEFAULT_MODEL` должна уметь в function-calling (tool use) — иначе агент не сможет вызывать инструменты. Для работы с дефолтной модели нужен tool-capable вариант; fallback-модель зашита в `catalog/config.py`.

Полный пользовательский сценарий (env → backend → frontend → открытие папки) — в `README-RUN.md`. Docker для локальной работы с документами не используй.

## Сквозной прогон (золотой путь)
```bash
# из backend/, при настроенном .env — временный воркспейс (.catalog/index.db) + samples/golden*.docx:
python scripts/golden_run.py
```


## Ключевые принципы (не нарушать)
- ФС — источник контента; SQLite — только системные данные/индекс (пересобираемый). Воркспейс = папка пользователя (ADR-0016).
- Новый инструмент/проверка → регистрируем в реестре + запись в `docs/verification-checks.md`.
- Значимое архитектурное решение → новый ADR + строка в `docs/adr/README.md`.
- Произвольная кодогенерация `.py` — вне среза (инструменты только из реестра); sandbox — позже.
- Ключи LLM — только в env / persist (app.db через `/setup`), никогда в коде/коммитах.

## Новому ИИ-агенту (onboarding)
1. Прочитай этот README целиком.
2. Прочитай `docs/adr/README.md` (индекс решений). Ключевые: **ADR-0001** (агент-луп), **ADR-0002** (скилл=конфиг), **ADR-0004** (сборка в момент согласия), **ADR-0005** (разделение хранилищ), **ADR-0010** (скоуп среза и non-goals), **ADR-0011** (фронтенд-стек), **ADR-0016** (workspace-as-folder).
3. Открой `docs/plan/` — текущий шаг и статус работы.
4. При необходимости — `docs/pre-design/` (исходные транскрипты) и `docs/verification-checks.md`.
5. Окружение: Python 3.13, node 23, pnpm 9, git. Менеджеры Python — `venv`+`pip` (uv не установлен).
