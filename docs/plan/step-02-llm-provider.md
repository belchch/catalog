# Step 02 — LLM-провайдер (OpenRouter)

- **Статус:** Code done (правки по ревью применены, ruff чист, 6/6 unit-тестов). Живой smoke блокирован 403 «Access denied by security policy» со стороны OpenRouter (WAF/сеть) — не код. Фиксы: см. `.kilo/plans/1783953542117-step-02-review-fixes.md`.
- **Цель:** рабочая интеграция с OpenRouter — `complete` (с tool-calling), `list_models`, streaming. Доказать, что function-calling поверх OpenRouter работает (главный технический риск среза). Без агент-лупа, инструментов документов, БД.

## Контракты

### `app/llm/base.py`
```python
@dataclass
class ToolSpec:      name: str; description: str; parameters: dict        # JSON Schema
@dataclass
class ToolCall:      id: str; name: str; arguments: dict
@dataclass
class Message:       role: str                                  # system|user|assistant|tool
                     content: str | None = None
                     tool_calls: list[ToolCall] | None = None
                     tool_call_id: str | None = None
                     name: str | None = None
@dataclass
class ModelInfo:     id: str; name: str; context_length: int | None
@dataclass
class CompletionResult:
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str
    usage: dict

class LLMProvider(Protocol):
    async def list_models(self) -> list[ModelInfo]: ...
    async def complete(self, model, messages, tools=None,
                       temperature=0.0, tool_choice="auto") -> CompletionResult: ...
    async def stream_complete(self, model, messages, tools=None,
                              temperature=0.0) -> AsyncIterator[str]: ...   # текстовые чанки
```

### `app/llm/openrouter.py`
- `httpx.AsyncClient`; OpenAI-совместимый API.
- `GET /models` → `list_models`.
- `POST /chat/completions` с `messages`, `tools`, `tool_choice`, `temperature` → `complete`.
- Заголовок `Authorization: Bearer $OPENROUTER_API_KEY`; опц. `HTTP-Referer`, `X-Title`.
- Streaming: SSE `data:` строки, `[DONE]` → `stream_complete`.
- Чёткие ошибки: 401 (нет/неверный ключ), 429 (лимит), таймаут.

### `scripts/smoke_llm.py`
Три проверки через `asyncio.run`:
1. `list_models()` → напечатать число и 3 slug'а.
2. `complete(model, [system, user("скажи привет")])` → текст.
3. **Tool-call proof:** инструмент `current_time()` (schema без параметров), user «сколько сейчас времени?»; `assert` что `result.tool_calls[0].name == "current_time"`; напечатать.

## Зависимости
Использует уже установленные `httpx`, `pydantic`, `python-dotenv` (из шага 01). Новых зависимостей нет.

## Критерий приёмки
- [~] `python scripts/smoke_llm.py` (с `OPENROUTER_API_KEY` в `backend/.env`) проходит все проверки. **Ключ есть, но OpenRouter отдаёт 403 «Access denied by security policy»** (блокировка WAF/сети на текущем окружении). Unit-тесты (`MockTransport`) — 6/6 зелёные, в т.ч. `test_stream_complete`. Прогон вживую требует разблокировки доступа к OpenRouter со стороны сети.
- [x] Без ключа — понятная ошибка, а не трейс (`smoke_llm.py` печатает `ERROR: OPENROUTER_API_KEY is not set` и выходит 1).
- [x] `from app.llm import OpenRouterProvider, Message, ToolSpec` импортируется чисто (проверено).
- **Нет:** агент-лупа, реестра инструментов, SQLite, FastAPI-эндпоинтов (кроме `/health`), UI.

## Заметки
- Модель для smoke берётся из `OPENROUTER_DEFAULT_MODEL` (env); если пусто — fallback на заведомо tool-capable слаг (зафиксировать в коде + README).
- Pin провайдера (ADR-0009) — пока готовим поле в запросе, но не используем; понадобится в шаге скиллов.
- Streaming обязателен по плану (ADR-0009), но в smoke достаточно `complete`; `stream_complete` реализуем и проверим простым выводом чанков.
