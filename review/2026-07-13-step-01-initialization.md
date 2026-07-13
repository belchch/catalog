# Ревью — Step 01: Инициализация проекта (каркас монорепо)

- **Дата:** 2026-07-13
- **Объект:** первый коммит (всё untracked-дерево)
- **Шаг плана:** [step-01-initialization](../docs/plan/step-01-initialization.md)
- **Проверено в рантайме:**
  - `pnpm run build` — зелёный (css 4.76 kB, js 191 kB)
  - `/health` → `{"status":"ok"}` через FastAPI TestClient
  - `ruff check .` — All checks passed

## Общая оценка

Каркас соответствует `step-01-initialization.md` и критерию приёмки. Структура, `.gitignore`, `.env.example`, ADR/план согласованы. Несколько моментов стоит почистить до/в первом коммите.

## Что хорошо

- `.gitignore` корректен: `.env` + `!.env.example`, `node_modules`, `workspace/*` с `!.gitkeep`, `*.egg-info`, `dist`. Ключ не утечёт.
- Backend минимальный и чистый; ruff проходит.
- Frontend: TS strict (`noUnusedLocals`, `verbatimModuleSyntax`), Tailwind v3 компилируется, build без ошибок.
- `config.py` читает всё из env с дефолтами; `.env.example` синхронен с `config.py`.

## Замечания

### Средние

#### 1. CORS невалиден для credentialed-запросов
- **Файл:** `backend/app/main.py:6-12`
- `allow_origins=["*"]` + `allow_credentials=True` — браузеры reject'ят `ACAO: *` вместе с credentials. В step-01 это помечено как dev-shortcut, но `allow_credentials=True` здесь бессмыслен и будет молча ломать запросы, как только появятся cookie/auth.
- **Решение:** либо убрать `allow_credentials`, либо (лучше) `allow_origins=["http://localhost:5173"]`. Не тащить в шаг 06.

#### 2. DoD по `/health` не закреплён тестом
- **Файл:** `backend/tests/` (только `__init__.py`)
- DoD гласит «проверено через TestClient», но контракта в коде нет — он не защищён от регрессии.
- **Решение:** добавить `tests/test_health.py` (одно утверждение через TestClient) + в `pyproject.toml` секцию `[tool.pytest.ini_options]` с `testpaths=["tests"]`.

### Низкие / cleanup

#### 3. Мёртвые ассеты Vite-шаблона
- **Файлы:** `frontend/src/assets/{hero.png,react.svg,vite.svg}`, `frontend/public/icons.svg`
- Нигде не используются (проверено grep'ом). `favicon.svg` тоже дефолтный, но хотя бы подключён в `index.html:5`.
- **Решение:** удалить — первый коммит будет чище.

#### 4. `<title>frontend</title>`
- **Файл:** `frontend/index.html:7`
- Дефолт Vite. Должно быть `Catalog`.

#### 5. Tailwind ESM-config warning при build
- `tailwind.config.js`/`postcss.config.js` — ESM (т.к. `package.json` `"type":"module"`), а Tailwind v3 грузит конфиг через `require()` → `ExperimentalWarning: CommonJS module … loading ES Module`.
- Безобидно, но шумит.
- **Решение:** переименовать в `.cjs` (оба) или смириться.

#### 6. Пробелы в именах файлов
- **Файлы:** `docs/pre-design/fable review.json`, `opus chat.json`
- Ссылки в `docs/adr/README.md:22` и `README.md` через пробел — неудобно в shell/импортах.
- **Решение:** переименовать в `fable-review.json` / `opus-chat.json` и поправить ссылки.

#### 7. Starlette TestClient deprecation (dev-only)
- Предупреждение: `install httpx2 instead`.
- Учесть в шаге 02, когда появится LLM-клиент.

## Не баги, на заметку

- `backend/app/config.py:5` — `load_dotenv()` на импорте норм для каркаса; в шаге API имеет смысл перейти на `pydantic-settings` (BaseSettings), раз pydantic уже в deps.
- Вложенный `frontend/.gitignore` дублирует часть корневого — безвредно, можно оставить как дефолт шаблона.
- `backend/scripts/.gitkeep` пока пуст — ок как заглушка.

## Рекомендация

Перед первым коммитом закрыть минимум:
- п.1 (CORS)
- пп.3–4 (cleanup ассетов + title)

Это дёшево и не тащит техдолг в историю. П.2 (тест `/health`) тоже лучше добавить сейчас, пока скелет «свежий». Пп.5–6 — по желанию.
