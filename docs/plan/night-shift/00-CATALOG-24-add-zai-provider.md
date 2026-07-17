# CATALOG-24 — Добавить провайдера z.ai

- **Задача Plane:** [CATALOG-24](https://app.plane.so/belchch/projects/catalog-app/work-items/24) (id: `b00ba6c5-ab0b-4448-8e1c-907c532fe87d`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Реализовать OpenAI-совместимый провайдер **z.ai** (Zhipu/BigModel, GLM), переиспользуя общую логику OpenRouter через базовый класс `OpenAICompatibleProvider`; добавить поддержку `reasoning_content` (thinking-модели GLM) и фабрику нескольких провайдеров. Мотивация: OpenRouter доступен только по VPN — нужен рабочий провайдер без VPN.

## Контекст

Протокол z.ai ≈ OpenRouter (диалект OpenAI Chat Completions): `/chat/completions`, `choices[].message`, SSE `data:`+`[DONE]`, function calling, `Authorization: Bearer`. Реализация провайдера сегодня:

- `backend/app/llm/openrouter.py` — монолитный `OpenRouterProvider`:
  - retry/backoff: `_post_with_retry` (`openrouter.py:88-149`), `_RETRY_STATUS`/`_DEFAULT_*` (`:27-29`).
  - `_parse_tool_calls` (`:43-62`), SSE-парсинг в `stream_complete` (`:341-360`).
  - `complete` (`:172-291`) и `stream_complete` (`:293-391`).
  - `list_models` дёргает `/models` (`:151-170`).
  - 401-сообщения захардкожены «Invalid OpenRouter API key» (`:120-121`, `:327-328`).
- Имя провайдера для логов **захардкожено** `provider="openrouter"` в **5** вызовах `write_prompt_log` (`openrouter.py:205, 227, 258, 362, 376`).
- `backend/app/llm/base.py`:
  - `CompletionResult` (`base.py:39-44`): `content, tool_calls, finish_reason, usage` — **нет `reasoning`**.
  - `LLMProvider` Protocol (`base.py:47-65`): `stream_complete(...) -> AsyncIterator[str]` — стрим отдаёт **только текст**, reasoning в стрime не пробросить без смены контракта.
- `backend/app/agent/runner.py`:
  - потребление `CompletionResult` (`runner.py:120-133`): `content/finish_reason/tool_calls/usage` кладутся в `trace.entries[-1].data` (`:121-128`) и историю; `FinishEvent` (`:136-141`, `:171`) несёт `usage`.
  - stream-ветка (`runner.py:104-118`): копит `text` из `stream_complete`, не парсит tool_calls, finishes at end of stream — reasoning здесь вообще не виден.
- `backend/app/llm/prompt_log.py:51-63` `write_prompt_log(provider=...)` уже параметризован провайдером строкой — переиспользуем.
- `backend/app/config.py:8-11` — `OPENROUTER_API_KEY/BASE_URL/DEFAULT_MODEL/FALLBACK_MODEL`. Нет `ZAI_*`.
- `backend/app/main.py:45-47` — `OpenRouterProvider(http_client, settings.api_key, settings.base_url)` инстанцируется напрямую, кладётся в `app.state.provider`. Фабрики нет.
- `backend/tests/conftest.py:35-81` `FakeProvider` реализует Protocol (`complete` `:51-68`, `stream_complete` `:70-77`) — при смене контракта/добавлении поля его надо обновить.
- **`.env.example` отсутствует** в репо (задача упоминает его обновление → создать).
- ADR-0009 (`docs/adr/0009-openrouter-provider.md`, Accepted) — провайдер=OpenRouter; задача требует новый ADR по мульти-провайдеру + дополнение ADR-0009.

Отличия z.ai (по описанию задачи): base_url `https://api.z.ai/api/paas/v4`; `/models` нет/иной формат → хардкод-каталог (`glm-4.6`, `glm-4.5`, `glm-4.5-air`, `glm-4.5-flash` …); thinking-модели отдают `reasoning_content` рядом с `content` (в стриме-дельте и в `message`); auth `Bearer` (JWT access token); `tool_choice` поддерживается, но `required`/конкретную функцию проверить под версию модели.

## Затрагиваемые файлы

**Новые:**
- `backend/app/llm/openai_compatible.py` — `OpenAICompatibleProvider`: общая логика (`_post_with_retry`, `_parse_tool_calls`, `_auth_headers`, `_backoff_delay`, SSE-парсер, `complete`, `stream_complete`, вызовы `write_prompt_log` с `self._provider_name`); параметризуемые `base_url`, `provider_name`, 401-сообщение. Поддержка `reasoning_content` (сборка + передача).
- `backend/app/llm/zai.py` — `ZaiProvider(OpenAICompatibleProvider)`: `base_url`, `provider_name="zai"`, `list_models()` (хардкод-каталог GLM), при необходимости тонкая правка обработки reasoning.
- `backend/app/llm/factory.py` (или в `config.py`/`main.py`) — `build_providers(settings, http_client) -> dict[str, LLMProvider]` + выбор активного (env `APP_PROVIDER` / `LLM_PROVIDER`).
- `docs/adr/0013-multi-provider-and-zai.md` — новый ADR (мульти-провайдер + z.ai); дополнить/сослаться на ADR-0009.
- `.env.example` — задокументировать `OPENROUTER_*`, `ZAI_API_KEY`, `ZAI_BASE_URL`, выбор провайдера.

**Изменяемые:**
- `backend/app/llm/base.py` — `CompletionResult.reasoning: str | None = None` (`base.py:39-44`); (решение) расширить `stream_complete` контракт, чтобы пробрасывать reasoning (напр. yield кортеж/объект `StreamDelta(content, reasoning)` вместо голой строки) — затронет `runner.py` и `FakeProvider`.
- `backend/app/llm/openrouter.py` — превратить `OpenRouterProvider` в тонкий подкласс `OpenAICompatibleProvider` (`provider_name="openrouter"`); удалить дубль общей логики; поведение **не меняется** (текущие тесты зелёные).
- `backend/app/agent/runner.py` — проброс `reasoning` в `trace.entries[-1].data` (`runner.py:121-128`), в не-stream `FinishEvent` (опц.), и в stream-ветке (`runner.py:104-118`) при смене контракта `stream_complete`.
- `backend/app/config.py:8-14` — `ZAI_API_KEY`, `ZAI_BASE_URL` (дефолт `https://api.z.ai/api/paas/v4`), `APP_PROVIDER` (выбор активного); проброс в `Settings` (`config.py:29-49`).
- `backend/app/main.py:45-47` — использовать фабрику: `app.state.providers` (dict) + `app.state.provider` (активный).
- `backend/app/agent/events.py` — (если reasoning выводится наружу) опц. поле в `TokenEvent`/новое `ReasoningEvent`; иначе оставить reasoning только в trace/log.
- `backend/tests/conftest.py:35-81` — `FakeProvider` привести к новому контракту (поле reasoning, сигнатура stream).
- `backend/tests/` — добавить `test_openai_compatible.py`/`test_zai.py`: моки `/chat/completions` (обычный + tool_calls), SSE-стрим с `reasoning_content`, `list_models` (хардкод для zai), 401-сообщение параметризовано.

## План действий

1. **Базовый класс.** Вынести из `openrouter.py` общую логику в `OpenAICompatibleProvider` (`openai_compatible.py`): `__init__(client, api_key, base_url, provider_name, *, max_retries, backoff_base)`, `_post_with_retry`, `_parse_tool_calls`, `complete`, `stream_complete`, `list_models` (с хуком `_parse_models`). Все 5 `write_prompt_log` зовут с `provider=self._provider_name`; 401-текст — `self._auth_error_message`.
2. **OpenRouter — тонкий подкласс.** `OpenRouterProvider(OpenAICompatibleProvider)` с `provider_name="openrouter"`, `list_models` через `/models` (перенести `openrouter.py:151-170`). Поведение идентично; прогнать существующие тесты — должны остаться зелёными.
3. **reasoning_content (контракт).** Добавить `CompletionResult.reasoning` (`base.py`). В `OpenAICompatibleProvider.complete` читать `message.get("reasoning_content")`; в stream собирать `delta.get("reasoning_content")`. Решение по стрим-контракту: либо `stream_complete -> AsyncIterator[StreamDelta]` (полная замена), либо доп. метод — зафиксировать в ADR/комменте; синхронно поправить `runner.py` (trace + stream-ветка) и `FakeProvider`.
4. **ZaiProvider.** `zai.py`: `base_url=ZAI_BASE_URL`, `provider_name="zai"`, `list_models()` возвращает хардкод-каталог GLM (`ModelInfo(id="glm-4.6", ...)` и т.д.); унаследованные `complete`/`stream_complete` корректно обрабатывают reasoning. Проверить `tool_choice` под GLM (при необходимости ограничить `required`).
5. **Фабрика + config.** В `config.py` добавить `ZAI_API_KEY`/`ZAI_BASE_URL`/`APP_PROVIDER`; в `Settings` пробросить. В `main.py` `build_providers(settings, http_client)` создаёт доступные (по наличию ключей) провайдеры и выставляет активный в `app.state.provider` (+ `app.state.providers`).
6. **trace/events/log.** В `runner.py` положить `reasoning` в `trace.entries[-1].data`; при выводе reasoning наружу — поле/событие (минимально: только trace + prompt_log, UI-показ — отдельная задача). `write_prompt_log` уже принимает произвольный `response` dict — добавить туда `reasoning`.
7. **Тесты.** `test_openai_compatible.py`: retry на 429/5xx, 401-raise с параметризованным текстом, парсинг tool_calls, SSE `[DONE]`. `test_zai.py`: `complete` с reasoning_content, stream с reasoning, `list_models` (хардкод). Обновить `conftest.FakeProvider` под новый контракт. Регресс `pytest backend/tests`.
8. **Документация.** Создать `.env.example`; новый ADR-0013 (мульти-провайдер + z.ai + решение по стрим-контракту reasoning); в ADR-0009 добавить ссылку «уточнён ADR-0013».
9. **Ручная проверка.** `APP_PROVIDER=zai` + `ZAI_API_KEY` → планировщик/build/apply ходят в z.ai; thinking-модель отдаёт reasoning (видно в prompt_log/trace); OpenRouter-режим не сломан.

## Критерии приёмки (Definition of Done)

- [ ] Общая OpenAI-совместимая логика в `OpenAICompatibleProvider`; `OpenRouterProvider` — тонкий подкласс, поведение идентично прежнему (существующие тесты зелёные).
- [ ] `ZaiProvider` работает: `complete`/`stream_complete` к `https://api.z.ai/api/paas/v4`, Bearer-auth, `list_models` отдаёт хардкод-каталог GLM.
- [ ] `provider="openrouter"` больше не захардкожен — параметризовано через `provider_name` (5 вызовов лога + 401-текст).
- [ ] `reasoning_content` пробрасывается: поле в `CompletionResult`, собирается в `complete` и stream; попадает в trace (`runner.py`) и prompt_log.
- [ ] Контракт `LLMProvider`/`stream_complete` осмысленно поддерживает reasoning (согласованно изменён в base/runner/FakeProvider); решение зафиксировано в ADR-0013.
- [ ] Фабрика провайдеров + env (`ZAI_API_KEY`/`ZAI_BASE_URL`/`APP_PROVIDER`); `main.py` инстанцирует несколько провайдеров и выбирает активный.
- [ ] `.env.example` создан и документирует все переменные; ADR-0013 добавлен, ADR-0009 дополнен ссылкой.
- [ ] `backend`: `pytest backend/tests` зелёные (включая новые `test_openai_compatible.py`/`test_zai.py` и обновлённый `conftest.FakeProvider`).
- [ ] `backend`: `ruff check backend` без ошибок.
- [ ] Ручная проверка: z.ai отвечает без VPN; thinking-рассуждения попадают в лог/trace; OpenRouter-режим не регрессировал.
