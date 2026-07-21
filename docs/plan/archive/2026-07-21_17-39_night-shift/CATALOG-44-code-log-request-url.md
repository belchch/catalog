# CATALOG-44 — Логировать полную инфу запроса, включая URL провайдера

- **Задача Plane:** [CATALOG-44](https://app.plane.so/belchch/projects/catalog-app/work-items/44) (id: `fde97783-c888-4ef5-a46b-a3afc7d5f73f`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** В логах и/или prompt-log JSON виден полный контекст LLM-запроса: провайдер, его `base_url`, модель, параметры, размер payload'а, статус ответа, latency. Сейчас `base_url` провайдера отсутствует везде — это критично для дебага «какой URL реально дёргался».

## Постановка задачи (актуальное ТЗ)

_(источник: название задачи; описание и комментарии пустые)_

> Добавить логирование полной инфы запроса, в том числе URL провайдера.

Расшифровка: при каждом LLM-вызове (через `OpenAICompatibleProvider`) в лог должно попадать достаточно информации, чтобы по логам восстановить: **какой провайдер, на какой URL (`base_url + path`), с каким телом (модель, tools, temperature, размер messages) и с каким результатом (статус, latency, error)**. Сейчас URL провайдера нигде не пишется.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

### Что уже логируется

В `backend/app/llm/openai_compatible.py`:

- `complete` (`openai_compatible.py:241-247`) — `model`, `len(messages)`, tool names, `temperature`. Без `base_url`, без размера body.
- `complete response` (`openai_compatible.py:302-309`) — `finish_reason`, обрезанный `content`, tool names, `usage`. Без статуса HTTP, без URL.
- `stream_complete request` (`openai_compatible.py:369-375`) — то же, что и `complete`.
- Ошибки: `_post_with_retry` логирует статус HTTP и тело ответа (`openai_compatible.py:178-198`), но без URL.
- `list_models` (`openai_compatible.py:216`) — счётчик моделей, без URL.

В `backend/app/llm/prompt_log.py` — `write_prompt_log` пишет JSON-файл с `provider`, `model`, `temperature`, `tools`, `messages`, `response`, `meta.latency_ms`, `meta.ok`. **Нет `base_url`**, нет полного URL запроса, нет HTTP-статуса.

### Что отсутствует

1. **`base_url` провайдера** — не пишется ни в `logger.info`, ни в prompt-log JSON. Это ключевой пункт задачи.
2. **Полный URL запроса** (`{base_url}/chat/completions` или `{base_url}/models`) — не пишется.
3. **HTTP-статус в успешных логах** — пишется только в ошибках (`logger.warning`), в норме статус не виден.
4. **Размер тела запроса / количество токенов в messages** — не пишется, только `len(messages)`.

### Архитектурный контекст

- Все провайдеры (OpenRouter, z.ai, …) наследуются от `OpenAICompatibleProvider` (`backend/app/llm/openai_compatible.py:65`) и задают `base_url` через `__init__`. То есть `self._base_url` доступен во всех методах — добавить в логи тривиально.
- `provider_name` также хранится в `self._provider_name`. В логах он иногда пишется (`_error_detail`, `_post_with_retry`), но не в информационных строках `complete`/`stream_complete`.
- `PROMPT_LOG_DIR`/`PROMPT_LOG_ENABLED` — конфигурация prompt-log в `app/config.py` (упоминается в `prompt_log.py:38-39`, `77`).

### Безопасность

`base_url` не чувствителен — это публичный endpoint. Логировать можно. А вот `Authorization` header — никогда (см. докстринг `prompt_log.py:14`); это и так соблюдается. Если в URL есть query-параметры с ключом — стоит проверить (на практике у OpenAI-compat провайдеров ключ всегда в header, не в URL).

## Затрагиваемые файлы

- `backend/app/llm/openai_compatible.py` — добавить `base_url` и полный URL в `logger.info` строки в `complete`, `stream_complete`, `list_models`, `_post_with_retry`; добавить HTTP-статус в success-логи.
- `backend/app/llm/prompt_log.py` — расширить `write_prompt_log`: добавить `request.base_url`, `request.url` (полный), опционально `request.tools_count`, `messages_count` (дублирование для быстрого чтения JSON без сканирования массива). Учитывать совместимость со старыми файлами — `schema_version` bump.
- `backend/app/llm/base.py` — если в `LLMProvider` протокол нужно暴露ить `base_url`/`provider_name` (для использования в более высоких слоях) — добавить. Но скорее всего достаточно внутренних полей класса; протокол можно не трогать.
- `backend/tests/test_llm.py` / `test_openai_compatible.py` / `test_prompt_log.py` — проверки, что в логах/JSON присутствуют `base_url` и URL.

## План действий

1. **Расширить `write_prompt_log`** (`prompt_log.py`):
   - Добавить параметры `base_url: str` и `url: str` (полный URL запроса) и `http_status: int | None`.
   - В `payload["request"]` добавить поля `base_url`, `url`.
   - В `payload["meta"]` добавить `http_status` (если есть).
   - Поднять `_SCHEMA_VERSION` до 2. Старые файлы остаются читаемыми — `schema_version` просто маркер.
   - Обновить все вызовы `write_prompt_log` в `openai_compatible.py` (5 мест: 2 в `complete`, 1 в `stream_complete` except, 1 в `stream_complete` success; плюс `list_models` не вызывает — там можно не логировать или добавить минимально).
2. **Расширить `logger.info` строки** в `openai_compatible.py`:
   - В `complete request` (стр. 241-247) и `stream_complete request` (стр. 369-375) — добавить `provider=%s base_url=%s url=%s`. Имена tool'ов, размер messages — уже есть.
   - В `complete response` (стр. 302-309) — добавить `http_status=200` (или реальный статус, если он сохранён). На текущий момент `_post_with_retry` возвращает `resp`, его `status_code` доступен — залогировать.
   - В `list_models` (стр. 216) — добавить `provider` и `base_url`.
   - В `_post_with_retry` warnings (стр. 178-198) — уже есть статус, добавить `url` для контекста.
3. **Безопасность URL**: `self._base_url` не содержит ключа, но если будущий провайдер будет использовать query-auth — добавить проверку/редакцию query-параметров в `_post_with_retry` перед логированием. На данный момент достаточно писать `base_url` как есть.
4. **Тесты**:
   - В `test_prompt_log.py` — записать лог через `write_prompt_log` с новым параметрами, прочитать JSON, assert что `request.base_url` и `request.url` присутствуют.
   - В `test_openai_compatible.py` — проверить, что `complete` логирует `base_url`/`url` (mock httpx, caplog).
   - В `test_llm.py` — общий smoke.
5. **Ручная проверка**: включить `PROMPT_LOG_ENABLED=1`, сделать planner-запрос, открыть свежий JSON в `PROMPT_LOG_DIR` — убедиться, что `base_url` и `url` есть. Проверить stdout/stderr лог — должны быть строки с URL.

## Критерии приёмки (Definition of Done)

- [ ] В логах приложения (`logger.info`) для каждого LLM-вызова видны: `provider`, `base_url`, полный `url` запроса, `model`, `tools`, `temperature`.
- [ ] В ответных логах видны: `http_status` (для `complete`), `finish_reason`, `usage`, `latency` (через prompt-log).
- [ ] В JSON prompt-лога появились поля `request.base_url`, `request.url`, `meta.http_status`; `schema_version` поднят до 2.
- [ ] Старые JSON-логи остаются читаемыми (новые поля опциональны для ридера, если есть ридер).
- [ ] `list_models` логирует провайдер и `base_url`.
- [ ] Ошибочные запросы логируют URL, по которому шли (в сообщении об ошибке или рядом).
- [ ] Authorization header не попадает в логи ни в каком виде (проверить, что `base_url` не содержит ключ).
- [ ] `backend/`: `ruff check .` зелёный.
- [ ] `backend/`: `pytest` зелёный, включая обновлённые тесты prompt_log и openai_compatible.
- [ ] Ручная проверка: `PROMPT_LOG_ENABLED=1`, сделать LLM-вызов, в JSON видно `base_url` и `url`.
