# Plan — Логирование выполнения скилла в стандартный вывод

- **Цель:** каждое действие во время выполнения скилла (apply + агент-луп) пишет
  одну запись в стандартный лог-вывод (stdout через Python `logging`), с
  корреляционным контекстом (`run_id`/`session_id`/`iteration`/`purpose`).
  Поток токенов НЕ логируется (шум).
- **Статус:** готов к реализации.

## Контекст (что есть сейчас)
- В приложении **нет настройки логирования** (`main.py` не вызывает
  `basicConfig`/`dictConfig`). Только `app.llm` и `app.llm.prompt_log` используют
  `logging.getLogger` → их INFO-сообщения по умолчанию невидимы.
- Выполнение скилла (`_run_agent_core` в `runner.py:73`, `_apply_core` в
  `apply.py:55`) генерирует структурированные `AgentEvent`
  (`Step/ToolCall/ToolResult/Token/Finish/Verify`) и пишет `Trace` в БД, но
  **не пишет ни одной log-строки**.
- Корреляция существует (`app/llm/log_context.py`: contextvars
  `session_id/run_id/iteration/purpose`, `collect_context()`), но绑ивается
  **только** в пути `build_skill` (`skills.py:137`). Apply/WS-путь контекст не
  привязывает → run_id/purpose для выполнения скилла пустые.
- Шаблон event→frame уже есть: `agent_event_to_frame` в `deps.py:51` — на него
  ориентируемся для event→log маппера.
- Соседняя фича (опц. запись prompt-логов на диск) — план
  `.kilo/plans/1784059101171-prompt-logging.md` и `app/llm/prompt_log.py`. Эта
  работа **дополняет** его (stdout-логи всегда вкл.; prompt-log на диске — opt-in).

## Решения (зафиксировано с пользователем)
1. Добавляем **конфиг логирования** (dictConfig, stdout-хендлер, формат с
   контекстом, уровень через env `LOG_LEVEL`, default INFO) — не только log-вызовы.
2. Гранулярность — **действия без токенов**: apply старт, итерация агента,
   LLM-запрос/ответ (уже в провайдере), tool_call, tool_result, verify (pass/fail
   + причины), retry, persist результата, finish, ошибка. `TokenEvent` пропускаем.

## Задачи (по порядку)

### 1. `app/config.py` — настройка LOG_LEVEL
- `LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()`.
- Добавить поле `log_level: str = LOG_LEVEL` в `Settings`.

### 2. НОВЫЙ `app/logging_config.py` — настройка логирования
- `setup_logging(level: str | None = None) -> None` через
  `logging.config.dictConfig`:
  - `version: 1`, **`disable_existing_loggers: False`** (не гасить uvicorn).
  - Один форматter + один `logging.StreamHandler` на `sys.stdout`, уровень INFO.
  - К хендлеру прикреплён **`ContextFilter`** (см. п.3).
  - Логгер `"app"` (и его дочерние) на INFO; root — WARNING.
- Идемпотентно (безопасно повторный вызов). Не трогает логгеры uvicorn.

### 3. `app/logging_config.py` — `ContextFilter(logging.Filter)`
- В `filter(record)` ставит `record.ctx = _fmt(collect_context())` через уже
  существующий `app.llm.log_context.collect_context()`.
- `_fmt`: только непустые поля, напр. `"run_id=abc iteration=2 purpose=apply_skill"`;
  пустая строка если ничего не привязано.
- Формат: `"%(asctime)s %(levelname)s %(name)s [%(ctx)s] %(message)s"`.

### 4. `app/main.py` — активировать настройку
- Импортировать `setup_logging` и вызвать на уровне модуля (после импортов) —
  выполняется при импорте `app.main`, после инициализации логов uvicorn.
- Читать уровень из `get_settings().log_level` (или env напрямую, чтобы не
  зависеть от lifespan).

### 5. НОВЫЙ `app/agent/logging.py` — event→log маппер (один источник правды)
- Модульный логгер `logger = logging.getLogger("app.agent")`.
- `def log_agent_event(event: AgentEvent) -> None` — `match`/if по типам:
  - `StepEvent` → `logger.info("agent iteration %d", e.iteration)`.
  - `TokenEvent` → **пропуск** (`return`).
  - `ToolCallEvent` → `logger.info("tool_call name=%s args=%s", e.name, _trunc(e.arguments))`.
  - `ToolResultEvent` → `logger.info("tool_result name=%s ok=%s result=%s", e.name, e.ok, _trunc(e.result))`.
  - `VerifyEvent` → `logger.info("verify attempt=%d passed=%s failures=%s", e.iteration, e.result.passed, list(e.result.failures))`.
  - `FinishEvent` → `logger.info("finish reason=%s capped=%s text=%s", e.finish_reason, e.capped, _trunc(e.text))`.
- `_trunc(v, limit=300)`: dict/list → `json.dumps(..., ensure_ascii=False)`; иначе
  `str(v)`; обрезается до `limit` с суффиксом `…[truncated]`. (Полный payload уже
  в trace и prompt-log.)

### 6. `app/agent/runner.py` — вызовы маппера в `_run_agent_core`
- Рядом с каждым `yield <event>` (и `trace.entries.append(...)`) добавить
  `log_agent_event(event)`. Точки: `StepEvent` (стр.~94), `TokenEvent` —
  пропустить, `FinishEvent` (стрим-ветка ~112 и не-стрим ~131, ~160), `ToolCallEvent`
  (~140), `ToolResultEvent` (~149).
- Тем самым и `run_agent`, и `run_agent_collect` логят идентично (оба идут через core).

### 7. `app/skills/apply.py` — apply-уровневые логи + маппер
- Модульный логгер `logger = logging.getLogger("app.skills.apply")`.
- В `_apply_core`:
  - старт: `logger.info("apply_skill start skill=%s skill_id=%s input_doc=%s run_id=%s", skill.name, skill_id, input_doc_id, run_id)`.
  - после каждого `_run_agent_core` event → `log_agent_event(event)` (covers step/tool/tool_result/finish).
  - `VerifyEvent` → `log_agent_event(...)`.
  - retry: `logger.info("verify failed, retry %d/%d failures=%s", r+1, skill.max_retries, list(result.failures))`.
  - persist: `logger.info("apply_skill persisted output_doc_id=%s", out_id)`.
  - итог: `logger.info("apply_skill done status=%s output_doc_id=%s", status, output_doc_id)`.
  - в `except Exception` (стр.~201): `logger.error("apply_skill failed: %s", exc)` перед `raise`.

### 8. `app/api/runs.py` — привязать корреляционный контекст
- В `run_stream_ws` обернуть цикл `async for event in apply_skill(...)` в
  `with prompt_log_context(run_id=run_id, session_id=None, purpose="apply_skill"):`.
  → теперь `record.ctx` содержит `run_id`/`purpose`, а `iteration` проставляется в
  `_run_agent_core` через `current_iteration.set(i)` (уже есть).
- `skill_id` логируется в apply-start строке (контекствар для него не нужен — вне скоупа).

### 9. Тесты — НОВЫЙ `backend/tests/test_skill_logging.py` (pytest `caplog`)
- `test_runner_logs_each_action`: на `FakeProvider` (как `test_agent.py`) прогнать
  цикл tool_call→final; assert caplog содержит записи "agent iteration",
  "tool_call name=...", "tool_result name=... ok=True", "finish ...".
- `test_tokens_not_logged`: stream-режим с `["Hel","lo"]` → нет записей про токены,
  есть "finish".
- `test_apply_logging`: через `apply_skill_collect` (setup как `test_apply.py`)
  → caplog содержит "apply_skill start ...", "verify ... passed=True",
  "apply_skill persisted output_doc_id=...", "apply_skill done status=ok".
- `test_context_filter_formats_context`: unit — создать LogRecord, прогнать
  `ContextFilter`, при `collect_context()=={run_id:"R1",purpose:"apply_skill"}`
  assert `record.ctx` содержит `"run_id=R1"` и `"purpose=apply_skill"`.
- `caplog`-setup: `caplog.set_level(logging.INFO, logger="app")`.

## Контракты (для исполнителя)
- `setup_logging(level: str | None = None) -> None` — `app/logging_config.py`.
- `ContextFilter(logging.Filter)` — там же.
- `log_agent_event(event: AgentEvent) -> None` — `app/agent/logging.py`.
- Без новых зависимостей (`logging`, `logging.config` — stdlib).
- Не меняем контракты `run_agent`/`apply_skill`/схему БД (ADR не нужен).

## Failure modes / риски
- dictConfig случайно гасит логгеры uvicorn → **`disable_existing_loggers: False`**.
- Двойное логирование в collect-пути — невозможно: core вызывается один раз на путь.
- Огромный `tool_result` (read_document) раздувает логи → `_trunc(limit=300)`
  (полный payload остаётся в trace/prompt-log).
- Ошибка логирования не должна ломать применение: `log_agent_event` оборачивать не
  нужно (formatter failures обрабатываются stdlib), но держать маппер простым, без
  выбросов.
- Порядок вызова `setup_logging` (после логов uvicorn) — вызов на импорте модуля
  `app.main` это гарантирует.

## Валидация (критерий приёмки)
```bash
cd backend
.venv/bin/ruff check app/ tests/
.venv/bin/python -m pytest tests/test_skill_logging.py tests/test_agent.py tests/test_apply.py tests/test_prompt_log.py -q
```
- Ручной прогон: `python scripts/golden_run.py` (или WS-применение скилла) — в
  stdout видны структурированные строки `... INFO app.skills.apply [run_id=... purpose=apply_skill] apply_skill start ...`, затем `app.agent` tool_call/tool_result/verify/finish, с `iteration=` в контексте.
- `ruff check` чист; новые + существующие тесты зелёные.

## Out of scope
- `skill_id` как contextvar (хватит в apply-start строке).
- Логирование стрима токенов.
- Запись логов в файл / внешнюю систему (stdout достаточно).
- ADR (инфра-изменение, не архитектурное) — по желанию можно добавить ADR-0012.
- Логирование пути планировщика/`build_skill` (контекст там уже привязан; при
  желании — отдельной задачей).
