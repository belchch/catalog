# ADR 0013: Multi-provider + z.ai (GLM) + StreamDelta-контракт reasoning

- **Date:** 2026-07-16
- **Status:** Accepted
- **Supersedes:** уточняет ADR-0009 (провайдер больше не = только OpenRouter)

## Context

ADR-0009 зафиксировал провайдер = **OpenRouter**. На практике OpenRouter доступен только через VPN, что блокирует разработку/демо без сети. Нужен рабочий провайдер без VPN.

Все кандидаты (OpenRouter, z.ai/Zhipu GLM, будущий Ollama/корп-gateway) говорят одним диалектом — **OpenAI Chat Completions**: `POST /chat/completions`, `choices[].message`, SSE `data:` + `[DONE]`, function calling, `Authorization: Bearer`. При этом реализация была монолитом `OpenRouterProvider` (~400 строк): retry/backoff, парсинг tool_calls, SSE-стриминг, prompt-лог — всё захардкожено под OpenRouter (включая 5 вызовов `write_prompt_log(provider="openrouter")` и текст 401).

Дополнительно: thinking-модели GLM отдают `reasoning_content` рядом с `content` (и в `message`, и в streaming-`delta`). Контракт `stream_complete -> AsyncIterator[str]` отдавал **только текст** — reasoning в стриме пробросить было нельзя без смены контракта.

## Decision

1. **Базовый класс `OpenAICompatibleProvider`** (`app/llm/openai_compatible.py`) — общая логика (retry/backoff, `_parse_tool_calls`, `_auth_headers`, SSE-парсер, `complete`, `stream_complete`, `list_models` через `/models`). Параметризуется `base_url`, `provider_name`, `auth_error_message`. Все вызовы `write_prompt_log` идут с `self._provider_name`; 401-текст — `self._auth_error_message`.

2. **`OpenRouterProvider` — тонкий подкласс** (`provider_name="openrouter"`, `list_models` через `/models`, 401 → `OPENROUTER_API_KEY`). Поведение идентично прежнему монолиту; существующие тесты остались зелёными.

3. **`ZaiProvider(OpenAICompatibleProvider)`** (`app/llm/zai.py`): `base_url=https://api.z.ai/api/paas/v4`, `provider_name="zai"`, Bearer-auth. `list_models()` возвращает **хардкод-каталог GLM** (`glm-4.6`, `glm-4.5`, `glm-4.5-air`, `glm-4.5-flash`, …) — z.ai `/models` ненадёжен/иной формы. `complete`/`stream_complete` унаследованы и корректно собирают `reasoning_content`.

4. **Контракт streaming изменён на `AsyncIterator[StreamDelta]`.** Введён `StreamDelta(content: str = "", reasoning: str | None = None)` (`app/llm/base.py`). Один chunk может нести только `content`, только `reasoning`, или оба. Это позволяет пробросить chain-of-thought thinking-моделей наружу без отдельного метода. Согласованно обновлены: `runner.py` (stream-ветка копит `reasoning_parts` → trace), `CompletionResult.reasoning` (не-stream), и все `FakeProvider` в тестах.

5. **Фабрика провайдеров** (`app/llm/factory.py`): `build_providers(settings, http_client)` создаёт каждый провайдер с настроенным ключом (OpenRouter — всегда, для backward compat; z.ai — при `ZAI_API_KEY`). `select_provider(providers, app_provider)` выбирает активный через env `APP_PROVIDER` (дефолт `openrouter`). `main.py` кладёт и dict (`app.state.providers`), и активный (`app.state.provider`).

6. **Config** (`app/config.py`): `ZAI_API_KEY`, `ZAI_BASE_URL` (дефолт `https://api.z.ai/api/paas/v4`), `APP_PROVIDER` — проброшены в `Settings`.

## Consequences

**Плюсы:** z.ai работает без VPN; добавление нового OpenAI-совместимого провайдера = тонкий подкласс + строка в фабрике; reasoning thinking-моделей виден в trace/prompt_log; `provider="openrouter"` больше не захардкожен.

**Минусы / совместимость:** смена контракта `stream_complete` (str → StreamDelta) — breaking change для любых внешних потребителей протокола; в рамках репо все потребители (runner + 4 FakeProvider) обновлены. Хардкод-каталог GLM требует ручного обновления при выходе новых моделей.

## Alternatives considered

- **Отдельный метод `stream_complete_with_reasoning`** вместо смены контракта — отклонено: дублирование, runner должен выбирать ветку, контракт расслаивается.
- **`yield tuple[str, str | None]`** вместо dataclass — отклонено: менее читаемо, позиционные аргументы хрупки.
- **Прямой SDK z.ai/Zhipu** — отклонено: lock-in, теряется переиспользование общей OpenAI-логики.
- **Live `/models` для z.ai** — отклонено: endpoint ненадёжен/иной формы; хардкод-каталог детерминированнее.
