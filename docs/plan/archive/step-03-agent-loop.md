# Step 03 — Агент-луп (function-calling цикл, реестр инструментов, trace)

- **Статус:** pending
- **Цель:** ядро движка — один function-calling цикл `run_agent`, общий для планировщика и выполнения скилла. Реестр инструментов (имя → ToolSpec + callable), валидация аргументов по JSON-Schema, cap по итерациям, структурированный trace, поток событий для стриминга в UI. Без документов/БД/verify/скиллов — инструменты-заглушки для тестов.

## Зависимости
- Шаг 02 (LLM-провайдер): `app.llm.LLMProvider`, `Message`, `ToolSpec`, `ToolCall`, `CompletionResult`.
- Новая зависимость: `jsonschema>=4` (валидация аргументов tool_call против схемы инструмента). Добавить в `pyproject.toml` `[project.dependencies]`.

## Контракты

### `app/agent/registry.py`
```python
ToolFunc = Callable[..., Awaitable[Any]]   # async, kwargs = распарсенные аргументы

class ToolRegistry:
    def register(self, spec: ToolSpec, func: ToolFunc) -> None: ...
    def specs(self) -> list[ToolSpec]: ...                  # для передачи в llm.complete(tools=...)
    def get(self, name: str) -> tuple[ToolSpec, ToolFunc] | None: ...
    def names(self) -> list[str]: ...
```
- `register` accepts only `(spec, func)`; `func` is async and receives `**arguments`.
- Поиск по имени → `(spec, func)`; неизвестное имя → ошибку агенту обратно (не исключение наружу).

### `app/agent/events.py`
```python
@dataclass
class TokenEvent:      delta: str                       # текстовый чанк стриминга
@dataclass
class ToolCallEvent:   id: str; name: str; arguments: dict
@dataclass
class ToolResultEvent: id: str; name: str; ok: bool; result: Any | str  # ok=False → error string
@dataclass
class StepEvent:       iteration: int                   # начало новой итерации цикла
@dataclass
class FinishEvent:
    text: str | None
    finish_reason: str          # "stop" | "tool_calls_done"-нет | "capped"
    capped: bool                # упёрлись в max_iter без финального ответа
    usage: dict

AgentEvent = TokenEvent | ToolCallEvent | ToolResultEvent | StepEvent | FinishEvent
```

### `app/agent/trace.py`
```python
@dataclass
class TraceEntry:
    kind: str                   # "llm" | "tool_call" | "tool_result" | "error"
    iteration: int
    data: dict                  # {finish_reason, tool_calls, content} / {name, arguments} / {name, result, ok} / {message}

@dataclass
class Trace:
    entries: list[TraceEntry]
    def to_json(self) -> str: ...
```

### `app/agent/runner.py`
```python
async def run_agent(            # async generator — стримит события
    *,
    provider: LLMProvider,
    model: str,
    system_prompt: str,
    messages: list[Message],    # история (без system — добавляется внутрь)
    tools: ToolRegistry,
    temperature: float = 0.0,
    max_iterations: int = 8,
    use_stream: bool = True,    # True → stream_complete (TokenEvent); False → complete (без токенов)
) -> AsyncIterator[AgentEvent]: ...

async def run_agent_collect(...) -> tuple[str | None, Trace, bool]:
    # drains run_agent → (final_text, trace, capped). Для verify-retry и тестов.
```

## Логика цикла (run_agent)
```
history = [Message(system, system_prompt), *messages]
trace = Trace()
for i in 1..max_iterations:
    yield StepEvent(i); trace.entries.append(TraceEntry("llm", i, {...}))
    if use_stream:
        text = ""
        async for delta in provider.stream_complete(model, history, tools.specs(), temperature):
            text += delta; yield TokenEvent(delta)
        # stream-режим: tool_calls из stream не достаём (упрощение среза); финиш по концу потока
        trace.entries[-1].data = {content: text}
        history.append(Message("assistant", content=text))
        yield FinishEvent(text, "stop", capped=False, usage={}); return
    else:
        resp = await provider.complete(model, history, tools.specs(), temperature)
        trace.entries[-1].data = {finish_reason, content, tool_calls}
        history.append(Message("assistant", content=resp.content, tool_calls=resp.tool_calls))
        if not resp.tool_calls:
            yield FinishEvent(resp.content, resp.finish_reason, capped=False, resp.usage); return
        for tc in resp.tool_calls:
            yield ToolCallEvent(tc.id, tc.name, tc.arguments)
            res = await _execute_tool(tools, tc)         # валидация + вызов
            yield ToolResultEvent(tc.id, tc.name, res.ok, res.payload)
            history.append(Message("tool", content=str(res.payload), tool_call_id=tc.id, name=tc.name))
            trace.entries.append(TraceEntry("tool_call" / "tool_result", i, {...}))
# цикл исчерпан без stop
yield FinishEvent(last_text, "capped", capped=True, usage={}); return
```

### Выполнение инструмента (`_execute_tool`)
1. `entry = tools.get(name)`; если нет → `{ok:False, payload:"error: unknown tool 'name'"}`.
2. Валидация `arguments` против `spec.parameters` через `jsonschema.validate`; при ошибке → `{ok:False, payload:"error: invalid args: <сообщение схемы>"}`.
3. `result = await func(**arguments)`; оборачивать исключения → `{ok:False, payload:"error: <exc>"}`.
4. Успех → `{ok:True, payload: result}`. `result` сериализуется в строку для истории (json для dict, иначе str).

> Стримящийся режим (`use_stream=True`) в срезе не разбирает `tool_calls` из SSE (OpenRouter mixed-content edge cases) — финиш по концу потока. Tool-цикл работает в не-стрим режиме (`use_stream=False`). Шаг 06/07 решает, какой режим для какого экрана (планировщик — стрим без инструментов-вызовов? или collect). Зафиксировать в step-06.

## Тесты (`backend/tests/test_agent.py`)
На **функциональном** провайдере (in-process fake), без сети:
```python
class FakeProvider:   # implements LLMProvider
    def __init__(self, script: list[CompletionResult]): ...
    async def complete(...): return self.script.pop(0)
```
- `test_loop_with_tool_calls` — скрипт: [tool_call(read_doc), final text]; assert trace содержит tool_call→tool_result→finish(text), capped=False.
- `test_unknown_tool_returns_error` — tool_call с несуществующим именем → tool_result ok=False с "error: unknown tool", цикл продолжается, модель (скрипт) даёт финал.
- `test_invalid_args_validation` — tool_call с аргументами вне schema → ok=False "error: invalid args", инструмент НЕ вызывается (spy).
- `test_max_iterations_cap` — скрипт всегда возвращает tool_calls → после max_iter yield FinishEvent(capped=True).
- `test_no_tools_immediate_finish` — 0 tool_calls → одна итерация, finish(text), capped=False.
- `test_tool_exception_wrapped` — инструмент бросает → ok=False "error: ...".
- `test_run_agent_collect` — обёртка возвращает (text, trace, capped).
- `test_stream_mode_emits_tokens` — FakeProvider.stream_complete выдаёт ["Hel","lo"] → TokenEvent×2, FinishEvent(text="Hello").

## Команды запуска / проверки
```bash
cd backend
.venv/bin/pip install jsonschema
.venv/bin/ruff check app/agent/ tests/test_agent.py
.venv/bin/python -m pytest tests/test_agent.py -v
```

## Критерий приёмки
- [ ] `run_agent` корректно крутит цикл tool-call→result→...→stop на FakeProvider; trace отражает каждый шаг.
- [ ] Неизвестный инструмент и невалидные аргументы → осмысленная ошибка обратно в модель (не исключение наружу), цикл жив.
- [ ] `max_iterations` → capped=True, цикл останавливается.
- [ ] `run_agent_collect` возвращает `(text, trace, capped)`.
- [ ] `ruff check` чист; все тесты `test_agent.py` зелёные.
- [ ] `ToolRegistry` регистрирует/ищет инструменты; `specs()` отдаёт список для провайдера.
- **Нет:** реальных документов, SQLite, FastAPI-эндпоинтов, verify, скиллов, UI. Инструменты — только тестовые заглушки.

## Заметки
- Поток событий (`AgentEvent`) — основа для WS-стриминга в шаге 06. Не привязываться к FastAPI здесь.
- `Trace.to_json()` пригодится в шаге 05 (сохранение `trace_json` в `SkillRun`) — реализуем сразу стабильно.
- `use_stream`/`use_stream` переключатель: в срезе tool-цикл бегает в не-стрим режиме (надёжный разбор tool_calls). Стрим токенов — для «человеческого» вывода планировщика (step 06 решит).
