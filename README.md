# Catalog — ИИ-агент для аналитика/архитектора

Платформа-оболочка: пользователь в чате составляет план обработки документа, превращает его в переиспользуемый **скилл** и применяет к документам. MVP («первый срез») — один сквозной цикл, чтобы «почувствовать продукт».

> Этот README — точка быстрого погружения для **новой сессии ИИ-агента**. См. раздел «Новому ИИ-агенту» внизу.

## Стек
| Слой | Технология |
|------|-----------|
| Backend | Python 3.11+ · FastAPI (+WebSocket) · httpx · pydantic |
| LLM | OpenRouter (единый шлюз, selector моделей, pin провайдера, streaming) |
| Хранилище | ФС (`workspace/`) — контент; SQLite — системные данные |
| Frontend | React (Vite) + TypeScript + Tailwind CSS |
| Движок скиллов | один function-calling агент-луп |

## Архитектура (кратко)
- **Движок** — один function-calling агент-луп; планировщик (чат) и выполнение скилла используют один и тот же цикл.
- **Скилл** = замороженный конфиг агента (`system_prompt`, `allowed_tools`, `model`, `temperature=0`, `verify_checks`).
- **Поток**: план в чате → система показывает задание → согласие → построение скилла + применение → ревью → коммит/итерация.
- **Хранилище**: ФС — источник контента (документы, результаты); SQLite — состояние (сессии, сообщения, скиллы, трейсы). Git — после среза.
- **Проверки** — детерминированный реестр (`docs/verification-checks.md`).

Полный список решений — в `docs/adr/` (ADR-0001…0011).

## Структура репозитория
```
Catalog/
  backend/      # FastAPI (Python)
  frontend/     # React + Vite + Tailwind
  workspace/    # контент: документы и результаты (ФС)
  docs/
    adr/                 # архитектурные решения (ADR)
    plan/                # декомпозиция среза по шагам
    pre-design/          # исходные транскрипты (opus, fable)
    verification-checks.md
  README.md
```

## Текущий статус
Первый срез. Текущий шаг — см. `docs/plan/` (индекс шагов). Верхний план среза: `~/.local/share/kilo/plans/1783886041469-first-slice-skill-loop.md`.

## Быстрый старт (после инициализации)
```bash
# env (backend): скопируй шаблон и впиши ключи
cd backend
cp .env.example .env
#   OPENROUTER_API_KEY=...        # обязательный ключ OpenRouter
#   OPENROUTER_DEFAULT_MODEL=...   # tool-capable модель (см. ниже)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload      # http://localhost:8000/health

# frontend
cd frontend
pnpm install
pnpm run dev                       # http://localhost:5173
```

> `OPENROUTER_DEFAULT_MODEL` должна уметь в function-calling (tool use) — иначе агент не сможет вызывать инструменты. Для работы с дефолтной модели нужен tool-capable вариант; fallback-модель зашита в `app/config.py`.

## Сквозной прогон (золотой путь)
```bash
# из backend/, при настроенном .env — оркестрирует весь цикл на samples/golden*.docx:
python scripts/golden_run.py
```


## Ключевые принципы (не нарушать)
- ФС — источник контента; SQLite — только системные данные/индекс (пересобираемый).
- Новый инструмент/проверка → регистрируем в реестре + запись в `docs/verification-checks.md`.
- Значимое архитектурное решение → новый ADR + строка в `docs/adr/README.md`.
- Произвольная кодогенерация `.py` — вне среза (инструменты только из реестра); sandbox — позже.
- Ключ `OPENROUTER_API_KEY` — только в `.env` (в `.gitignore`), никогда в коде/коммитах.

## Новому ИИ-агенту (onboarding)
1. Прочитай этот README целиком.
2. Прочитай `docs/adr/README.md` (индекс решений). Ключевые: **ADR-0001** (агент-луп), **ADR-0002** (скилл=конфиг), **ADR-0004** (сборка в момент согласия), **ADR-0005** (разделение хранилищ), **ADR-0010** (скоуп среза и non-goals), **ADR-0011** (фронтенд-стек).
3. Открой `docs/plan/` — текущий шаг и статус работы.
4. При необходимости — `docs/pre-design/` (исходные транскрипты) и `docs/verification-checks.md`.
5. Окружение: Python 3.13, node 23, pnpm 9, git. Менеджеры Python — `venv`+`pip` (uv не установлен).
