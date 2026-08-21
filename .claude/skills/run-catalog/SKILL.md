---
name: run-catalog
description: Поднять локальный стенд Catalog — backend (FastAPI/uvicorn на 8000) и frontend (Vite на 5173) — и убедиться, что они отвечают. Использовать, когда просят запустить/стартовать приложение, открыть UI, посмотреть изменение в живом приложении, а не в тестах, или снять поведение через API живого бэкенда.
---

# Skill: запуск стенда Catalog

Проверенный путь запуска. Docker для локальной работы **не используем** (AGENTS.md,
инвариант «основной способ запуска — нативный»); `deploy/` — задел под серверный
деплой и может отставать от кода.

## Предусловия

Окружение в репо, как правило, уже собрано — сначала проверь, а не переустанавливай:

```bash
ls -d backend/.venv frontend/node_modules backend/.env frontend/.env
```

Чего нет — доставь:

| Нет | Команда (из соответствующей папки) |
|---|---|
| `backend/.venv` | `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"` |
| `backend/.env` | `cp .env.example .env`, затем задать `OPENROUTER_API_KEY` и tool-capable `OPENROUTER_DEFAULT_MODEL` |
| `frontend/node_modules` | `pnpm install` |

Ключи можно не класть в `.env`: они persist-ятся в глобальной `app.db` через экран
первого запуска (`PUT /setup/keys`). Env перекрывает persist.

## Запуск

Два процесса, оба **в фоне** — они долгоживущие, foreground их не держи.

```bash
# backend — из backend/
.venv/bin/uvicorn catalog.main:app --reload --port 8000

# frontend — из frontend/
pnpm run dev
```

venv активировать не нужно: `.venv/bin/uvicorn` самодостаточен.

## Проверка

```bash
curl -s http://localhost:8000/health          # {"status":"ok","git_sha":"..."}
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5173/
```

**Важно про адреса.** uvicorn слушает `127.0.0.1:8000` (IPv4), Vite — `[::1]:5173`
(IPv6). Поэтому `http://127.0.0.1:5173` не ответит вообще, а `http://[::1]:8000` —
наоборот. Для фронта всегда `http://localhost:5173`. Не диагностируй это как
«фронт не поднялся» — сначала посмотри вывод процесса, там будет `VITE ready in ...`.

Фронт ходит в бэк по `VITE_API_URL` из `frontend/.env` (`http://localhost:8000`);
без него в dev дефолт тот же. CORS в `catalog/main.py` разрешает 5173–5175 на
`localhost` и `127.0.0.1` — если Vite занял 5174/5175, всё ещё работает.

## Драйвинг: воркспейс обязателен

Сразу после старта воркспейс **не открыт**, и это нормально. Доменные ручки в этом
состоянии отдают `409 {"detail":"workspace not open"}` — это не поломка:

```bash
curl -s http://localhost:8000/skills      # 409 workspace not open
```

Воркспейс — папка с маркером `.catalog/index.db` (ADR-0016). Открывается в UI
(«Открыть воркспейс», серверный folder-picker `/fs/browse`, ADR-0017) либо запросом:

```bash
curl -s http://localhost:8000/workspaces                    # известные папки
curl -s -X POST http://localhost:8000/workspaces/open \
     -H 'Content-Type: application/json' -d '{"path":"/абсолютный/путь"}'
curl -s http://localhost:8000/workspaces/current
```

Папка без маркера потребует подтверждения инициализации: первый ответ несёт
`status` с превью индекса, а не открытый воркспейс — повтори запрос с
`{"path": "...", "confirm": true}`.

Дальше по вкусу задачи: `/sessions` (WS `/sessions/{id}` — планировщик),
`/skills`, `/skills/{id}/apply` + WS `/runs/{id}/stream`, `/documents`.

Если менял UI — открой `http://localhost:5173`, доведи до экрана с изменением и
**посмотри на результат**, а не ограничивайся кодом 200.

## Остановка

Убить оба фоновых процесса. Порт занят от прошлого прогона:

```bash
lsof -nP -iTCP -sTCP:LISTEN | grep -E ':5173|:8000'
```

## Что это не заменяет

Стенд ≠ проверки. Гейт DoD — шесть команд из CLAUDE.md (`ruff check .`, `pytest`
из `backend/`; `pnpm run build|lint|typecheck|test` из `frontend/`). Сквозной
прогон домена — `python scripts/golden_run.py` из `backend/` (нужны ключ в `.env`
и `samples/golden.docx`, `samples/golden2.docx`).
