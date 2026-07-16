# Plan — uvicorn-стиль вывода + устранение дублирования логов

- **Цель:** строки `app.*` в stdout выглядят как родные uvicorn-строки
  (`INFO:     <message>`), с цветными уровнями (TTY), без таймстемпа и имени
  логгера, но с **компактным correlation-тегом** `[run=… iter=… purpose=…]`
  (только непустые поля, `run_id` до 8 символов). Плюс — починить баг
  дублирования (`agent iteration 1` ×2, `finish` ×3), который оставил прошлый PR.
- **Статус:** готов к реализации.

## Контекст (что есть сейчас)
- Сервер запускается uvicorn-CLI: `uvicorn app.main:app --reload` (README:51).
  uvicorn ставит **свой** `DefaultFormatter` на логгеры `uvicorn*` →
  `INFO:     <message>` (префикс уровня + цвет, без таймстемпа).
- Наш `setup_logging` (`app/logging_config.py`, вызывается на импорте `app.main`)
  ставит на логгер `app` **другой** формат:
  `%(asctime)s %(levelname)s %(name)s [%(ctx)s] %(message)s` → отсюда разнобой.
- Все `app.*` логи (`app.llm`, `app.agent`, `app.skills.apply`) идут через один
  handler логгера `app` (`propagate: False`) — значит, сменив форматтер, меняем
  вид **всех** app-строк сразу.
- `ContextFilter` (`logging_config.py:40`) уже ставит `record.ctx` из
  `app.llm.log_context.collect_context()` (keys: `session_id`/`run_id`/
  `iteration`/`purpose`). Меняем только рендер тега.

### Баг дублирования (починить)
`log_agent_event(event)` вызывается **в двух местах** для одних и тех же событий:
- `_run_agent_core` (runner.py:97,117,140,149,160,173) — после каждого `yield`;
- `_apply_core` (apply.py:145) — повторно логирует каждое внутреннее событие
  агента внутри `async for event in _run_agent_core(...)`.
Плюс `_apply_core` эмитит свой `FinishEvent` (apply.py:227) и логирует его
(apply.py:228) → третий `finish`. VerifyEvent эмитится только в apply → 1 раз.

## Решения (зафиксировано с пользователем)
1. **Компактный correlation-тег** в новом формате: `INFO:     [run=05429765
   purpose=apply_skill iter=1] <message>`. Ключи: `run`/`session`/`iter`/
   `purpose`, только непустые, `run_id` обрезается до первых 8 символов (полный
   id остаётся в `apply_skill start …` строке + в trace/БД).
2. **Таймстемп и имя логгера убираем** (как у uvicorn). Время остаётся в
   trace/prompt-log/БД.
3. **Цвет уровня** — переиспользуем `uvicorn.logging.DefaultFormatter` (его
   `color_level_prefix` + авто-detect TTY через `use_colors=None`), чтобы
   префикс/цвет были байт-в-байт как у uvicorn и не дублировать ANSI-логику.
4. **Дедуп:** единый источник правды — `_run_agent_core`. В `_apply_core`
  убираем повторное логирование внутренних событий и apply-finish; оставляем
  логирование VerifyEvent (apply-only) и apply-уровневые `logger.info`/`error`.

## Задачи (по порядку)

### 1. `app/logging_config.py` — новый форматтер + компактный контекст
- Удалить константу `_LOG_FORMAT` (старый verbose-формат).
- `_fmt_context(ctx)`: рендерить **компактные** пары, порядок
  `run, iter, purpose, session`; маппинг ключей: `run_id`→`run` (значение
  обрезается до `[:8]`), `iteration`→`iter`, `purpose`→`purpose`,
  `session_id`→`session`; только непустые (`is not None and != ""`); join `" "`.
  Пустой контекст → `""`.
- `ContextFilter` — без изменений контракта: всё так же ставит `record.ctx`
  (теперь компактную строку / `""`).
- НОВЫЙ `AppFormatter(uvicorn.logging.DefaultFormatter)`:
  - импорт `from uvicorn.logging import DefaultFormatter`
    (и `LEVEL_NAME_TO_LEVEL_PREFIX` если нужен для fallback);
  - переопределить `formatMessage(record)`: использовать унаследованный
    `color_level_prefix`/`levelprefix` (точная логика uvicorn), затем собрать
    строку: `f"{record.levelprefix}{tag} {record.getMessage()}"`, где
    `tag = f" [{record.ctx}]"` если `record.ctx`, иначе `""`.
  - цель: `INFO:     <message>` (без контекста) и
    `INFO:     [run=… purpose=…] <message>` (с контекстом), выровнено по
    колонке с родными uvicorn-строками.
  - Fallback (если API uvicorn изменится): реплицировать таблицу префиксов
    (`INFO:     ` / `WARNING:  ` / `ERROR:    ` / `DEBUG:    ` / `CRITICAL: `)
    и ANSI-коды вручную.
- В `setup_logging`: форматтер `"default"` → фабрика `AppFormatter` через `"()"`
  (dictConfig), `disable_existing_loggers: False` **обязательно**, handler
  `stdout` (StreamHandler на `sys.stdout`, level INFO, фильтр `context`),
  логгер `app` (`propagate: False`, level из аргумента/`LOG_LEVEL`), root WARNING.
  Сигнатура `setup_logging(level: str | None = None) -> None` — без изменений.

### 2. `app/skills/apply.py` — устранить дубли (правки точечно)
- **Удалить** `log_agent_event(event)` в теле `async for event in
  _run_agent_core(...)` (apply.py:145) — внутренние события уже логирует ядро.
- **Удалить** `log_agent_event(finish_apply)` (apply.py:228) — избыточно
  (finish агента уже залогирован ядром; `apply_skill done` — авторитетная строка
  завершения apply).
- **Оставить** `log_agent_event(verify_event)` (apply.py:156) — VerifyEvent
  эмитится только в apply.
- **Оставить** все `logger.info(...)` (start/retry/persist/done) и
  `logger.error("apply_skill failed", exc_info=True)`.
- Итог: каждое событие логируется ровно 1 раз; standalone `run_agent`/
  `run_agent_collect` логируют идентично (через ядро).

### 3. `app/agent/runner.py` — без правок
- Вызовы `log_agent_event(...)` в `_run_agent_core` (97/117/140/149/160/173) —
  единственный источник правды. Не трогать. Только проверить, что отдельные
  пути (`run_agent`, `run_agent_collect`) логируют одинаково.

### 4. `app/main.py` — без правок
- `setup_logging(level=get_settings().log_level)` на импорте остаётся. Проверить.

### 5. Тесты — `backend/tests/test_skill_logging.py` (pytest `caplog`)
- Обновить `test_context_filter_formats_context`: assert `record.ctx` содержит
  `"run=R1"` и `"purpose=apply_skill"` (новые компактные ключи). Добавить кейс с
  длинным `run_id` (32 hex) → в теге `run=` ровно 8 символов.
- Оставить `test_context_filter_empty_when_no_context` (`record.ctx == ""`).
- НОВЫЙ `test_no_duplicate_logging`: через `apply_skill_collect` (полный apply
  путь) прогнать сценарий «1 итерация → finish» и assert, что
  `"agent iteration 1"` и `"finish reason=stop"` встречаются в caplog **ровно по
  одному разу** (защита от регресса дедупа).
- НОВЫЙ `test_formatter_renders_uvicorn_prefix_and_context`: собрать LogRecord,
  прогнать через `ContextFilter` + `AppFormatter().format(record)`; assert:
  начинается с префикса уровня (`"INFO"` / цветной вариант), содержит
  `[run=… purpose=apply_skill]` при привязанном контексте, **не** содержит
  `[...]` при пустом контексте, и **не** содержит таймстемпа/имени логгера.
  Цвет: тестировать стабильную часть (`INFO:`), не конкретные ANSI-коды.
- Существующие `test_runner_logs_each_action`, `test_tokens_not_logged`,
  `test_apply_logging`, `test_log_agent_event_handles_all_event_types` — тела
  сообщений не меняются → остаются зелёными без правок (убедиться).
- `caplog`-setup прежний: `caplog.set_level(logging.INFO, logger="app")`.

## Контракты (для исполнителя)
- `setup_logging(level: str | None = None) -> None` — без изменений сигнатуры.
- `ContextFilter(logging.Filter)` — без изменений (ставит `record.ctx`).
- `AppFormatter(uvicorn.logging.DefaultFormatter)` — новый, внутренний.
- Без новых зависимостей (`uvicorn` уже в `pyproject.toml`).
- Не меняем контракты `run_agent`/`apply_skill`/схему БД/ADR.

## Failure modes / риски
- Связка с internals uvicorn (`LEVEL_NAME_TO_LEVEL_PREFIX`,
  `color_level_prefix`) → fallback: реплицировать таблицу префиксов + ANSI.
- Цветы в pipe/non-TTY (сборщик логов) → `DefaultFormatter(use_colors=None)`
  сам отключает цвет вне TTY (поведение uvicorn).
- Удаление лога apply-finish может «сюрпризнуть» → митигировано: finish агента
  логируется ядром 1 раз, `apply_skill done` = авторитет завершения apply.
- Убран таймстемп → время остаётся в trace/prompt-log/БД; читаемость консоли
  важнее (env-тоггл таймстемпа — out of scope).
- ANSI-коды vs `caplog`: caplog ловит record'ы, не форматированный вывод; тест
  форматтера вызывает `AppFormatter().format(record)` явно и проверяет
  стабильную часть (`INFO:`), игнорируя конкретные ANSI-последовательности.

## Валидация (критерий приёмки)
```bash
cd backend
.venv/bin/ruff check app/ tests/
.venv/bin/python -m pytest tests/test_skill_logging.py tests/test_agent.py tests/test_apply.py tests/test_prompt_log.py -q
```
- Ручной прогон: `uvicorn app.main:app --reload`, применить скилл через
  `WS /runs/{id}/stream` (или `python scripts/golden_run.py`) → app-строки
  выровнены по колонке с uvicorn-строками (`INFO:     …`), виден компактный тег
  `[run=… purpose=apply_skill iter=1]`, **нет дублей** `agent iteration`/`finish`,
  цвет уровня в TTY; `app.llm` `complete request/response` тоже в новом стиле.
- `ruff check` чист; новые + существующие тесты зелёные.

## Out of scope
- Запись логов в файл / внешнюю систему; env-тоггл таймстемпа/контекста/цветов.
- Формат access-лога uvicorn (`uvicorn.access`) — не трогаем.
- ADR (инфра-правка, не архитектурная).
- Логирование пути планировщика/`build_skill` (контекст там уже привязан).
