# Step 01 — Инициализация проекта (каркас монорепо)

- **Статус:** Done
- **Цель:** сформировать runnable-каркас всего приложения: backend (FastAPI, `/health`) и frontend (Vite+React+TS+Tailwind, dev-сервер), плюс `workspace/`, `.gitignore`, README. Без бизнес-логики (LLM/движок/БД — со следующих шагов).

## Решения (стандартный вариант)
- **Монорепо, простое:** соседние `backend/` (Python) и `frontend/` (React). Без workspace-оркестратора (backend не на JS).
- **Python:** `venv` + `pip` + `pyproject.toml` (PEP 621). uv не установлен — не тянем.
- **Frontend:** Vite (react-ts) + Tailwind v3 + PostCSS; пакетный менеджер **pnpm**.
- **Git:** инициализируем репозиторий (сейчас его нет — `Is directory a git repo: no`).

## Целевая структура
```
Catalog/
  backend/
    pyproject.toml
    app/
      __init__.py
      config.py          # переменные окружения (ключ OpenRouter и т.п.)
      main.py            # FastAPI app + GET /health + CORS для дев-сервера фронта
      llm/__init__.py    # placeholder под шаг 02
    scripts/.gitkeep
    tests/__init__.py
    .env.example
  frontend/
    package.json         # создаётся через pnpm create vite
    vite.config.ts
    tsconfig.json
    tailwind.config.js
    postcss.config.js
    index.html
    src/{main.tsx, App.tsx, index.css}
  workspace/.gitkeep
  docs/                  # уже есть
  .gitignore
  README.md              # уже есть
```

## Порядок задач
1. **Root:** `.gitignore` (python, node, .env, workspace/* кроме .gitkeep, .DS_Store), `workspace/.gitkeep`.
2. **Backend:** `pyproject.toml` (deps: fastapi, uvicorn[standard], httpx, pydantic, python-dotenv; dev: pytest, ruff); `app/`-пакет (`config.py`, `main.py` с `/health` и CORS, `llm/__init__.py`); `.env.example`; `tests/__init__.py`.
3. **Frontend:** `pnpm create vite frontend --template react-ts` → `pnpm install` → добавить Tailwind v3 (`pnpm add -D tailwindcss@3 postcss autoprefixer`, `npx tailwindcss init -p`) → настроить `tailwind.config.js` (content: `./index.html ./src/**/*`) и `src/index.css` (`@tailwind base/components/utilities`) → `App.tsx` с демо-блоком.
4. **Git:** `git init`, первый коммит «chore: project skeleton».

## Команды запуска / проверки
```bash
# backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
curl localhost:8000/health      # -> {"status":"ok"}

# frontend
cd frontend
pnpm install
pnpm run dev                     # localhost:5173, страница со стилем Tailwind
pnpm run build                   # сборка без ошибок
```

## Критерий приёмки (definition of done)
- [x] `GET /health` → `{"status":"ok"}` (проверено через TestClient; uvicorn поднимается).
- [x] `pnpm run build` проходит без ошибок; Tailwind-стили компилируются (index css ~4.76 kB). `pnpm run dev` — дев-сервер на :5173.
- [x] `import app` чистый; `workspace/`, `docs/` на месте; `.gitignore` корректен (`.env`, `node_modules`, `__pycache__`, контент workspace, `*.egg-info`, `dist`).
- [x] Git-репозиторий инициализирован. **Первый коммит не сделан** — ждём явного решения заказчика.
- **Нет:** LLM-вызовов, агент-лупа, SQLite, загрузки документов, логики скиллов.

## Заметки
- Python 3.13 в окружении (≥3.11 — ок). `requires-python = ">=3.11"`.
- CORS пока `allow_origins=["*"]` только для удобства дев-сервера; сузим в шаге API.
- Файл `.env` не создаём (только `.env.example`); реальный ключ пользователь вносит сам.
