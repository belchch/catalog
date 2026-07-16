# CATALOG-6 — Настройка скила перед сохранением (модель, провайдер, рассуждения)

- **Задача Plane:** [CATALOG-6](https://app.plane.so/belchch/projects/catalog-app/work-items/6) (id: `171c27b0-5ffe-45ef-be28-b8a276c772b4`, state: In Progress)
- **Статус плана:** Analyzed
- **Предпосылки:** CATALOG-24 (мульти-провайдер + reasoning)
- **Цель:** Перед сохранением скила показывать **модалку настройки**, где пользователь может скорректировать параметры — пока минимум: **модель, провайдер, режим рассуждений** (reasoning variant). Для этого нужно: расширить `SkillConfig` полями `provider`/`reasoning`, добавить эндпоинты получения списка доступных моделей/провайдеров/вариантов рассуждений, и разделить сборку скила на «получить черновик конфига» → «пользователь настраивает» → «сохранить». Связан с [CATALOG-24](https://app.plane.so/belchch/projects/catalog-app/work-items/24) (второй провайдер zai — даёт множественность провайдеров).

## Контекст

Сейчас сборка скила **одношаговая и без ревью пользователем**:

- **Build-флоу:** кнопка «Создать скилл из сессии» (`frontend/src/components/Chat.tsx:75-81`, `onCreateSkill`) → `App.handleCreateSkill` → `buildSkill(sessionId)` (`frontend/src/api.ts:77-79`) → `POST /sessions/{id}/skills` (`backend/app/api/skills.py:198-215`, `build_skill_endpoint`) → `build_skill_from_session` (`skills.py:113-195`). Эта функция гоняет один function-calling-оборот LLM с инструментом `build_skill` (`skills.py:69-73`), парсит аргументы в `SkillConfig` (`_args_to_config`, `skills.py:76-96`) и **сразу** `create_skill(..., status="draft")` (`skills.py:182-188`). Пользователь не видит конфиг до сохранения и не может поменять модель/провайдер.
- **SkillConfig** (`backend/app/skills/config.py:28-40`): несёт `model: str`, `temperature`, но **нет** поля `provider` и **нет** поля `reasoning`/`reasoning_variant`. Сериализуется в `config_json` (`config.py:42-61`).
- **Провайдер — пока один**, инстанцируется в lifespan: `app.state.provider = OpenRouterProvider(...)` (`backend/app/main.py:45`). Протокол `LLMProvider` (`backend/app/llm/base.py:47-65`) уже содержит `list_models() -> list[ModelInfo]` (`base.py:48`), и `OpenRouterProvider.list_models()` (`backend/app/llm/openrouter.py:151-170`) тянет модели с `/models`. Но **эндпоинт `GET /models` не проброшен** в API. `complete(model, messages, tools, temperature, tool_choice)` (`base.py:50-57`) принимает только `model` + `temperature` — **параметра reasoning в протоколе ещё нет**.
- **ModelInfo** (`base.py:32-36`): `{id, name, context_length}` — без информации о поддержке reasoning и его вариантах.
- **Множественность провайдеров** появляется в CATALOG-24 (zai-провайдер). Эта задача проектируется с оглядкой на него, но минимально работает и с одним провайдером (список из одного).

Ключевой разрыв: build = «сгенерил и сразу сохранил», а нужно «сгенерил → показал превью → пользователь выбрал модель/провайдер/reasoning → сохранил».

## Затрагиваемые файлы

**Backend — модель данных:**
- `backend/app/skills/config.py:28-40` — добавить поля `provider: str = ""` и `reasoning: str = ""` (variant; пусто = по умолчанию) в `SkillConfig`; обновить `to_json`/`from_json` (`config.py:42-83`). Старые `config_json` без этих полей читаются с дефолтами — миграция не нужна.
- `backend/app/llm/base.py:32-36` — расширить `ModelInfo` опциональными `supports_reasoning: bool` / `reasoning_variants: list[str]` (если провайдер умеет отдавать; иначе заполняется на стороне бэка/статикой).

**Backend — сборка в два шага (превью → сохранение):**
- `backend/app/api/skills.py`:
  - `build_skill_from_session` (`skills.py:113-195`) — не вызывать `create_skill` сразу; вернуть `SkillConfig` (превью) + собранный набор опций. Либо: создать `draft`, но добавить отдельный шаг подтверждения с переопределением полей.
  - Новый эндпоинт подтверждения: `POST /sessions/{id}/skills` возвращает `draft` id + превью конфига (имя/описание/модель/...); новый `PATCH /skills/{id}` (или `POST /skills/{id}/configure`) принимает `{model?, provider?, reasoning?}` и обновляет конфиг перед финальным сохранением. Альтернатива: `build_skill_from_session` создаёт draft и возвращает `SkillBuilt{skill_id}` + `config`; модалка правит через `PATCH`.
  - `_args_to_config` (`skills.py:76-96`) — пробросить `provider`/`reasoning` из tool-args (если модель их предлагает); дефолты — текущий провайдер/без reasoning.
- `backend/app/api/schemas.py` — `SkillBuilt` расширить превью конфига (`name, description, model, provider, reasoning`) или добавить `SkillPreview`; `SkillConfigureRequest{model?, provider?, reasoning?}`.

**Backend — каталог опций (модели/провайдеры/reasoning):**
- `backend/app/api/skills.py` (или новый `backend/app/api/models.py`) — эндпоинты:
  - `GET /models` — `provider.list_models()` → `[{id, name, context_length, supports_reasoning, reasoning_variants}]`.
  - `GET /providers` — список доступных провайдеров (минимум текущий; расширится в CATALOG-24).
  - `GET /models/{model_id}/reasoning` (опционально) — варианты рассуждений для модели.
- `backend/app/main.py:70` — подключить новый роутер.

**Backend — проброс reasoning в вызов LLM:**
- `backend/app/llm/base.py:50-57` — добавить `reasoning: str = ""` в `complete`/`stream_complete`.
- `backend/app/llm/openrouter.py` — передать reasoning в тело запроса (OpenRouter mapping: `reasoning: {"effort": ...}` или эквивалент).
- `backend/app/agent/runner.py:74-173` — пробросить `reasoning` в `provider.complete`/`stream_complete`; `apply.py:133-149` — передавать `skill.reasoning`.

**Backend — тесты:**
- `backend/tests/test_api.py` — build возвращает превью; configure обновляет model/provider/reasoning; `GET /models` отдаёт список (FakeProvider уже умеет `list_models`, `test_skill_logging.py:65`).
- `backend/tests/test_build.py` (если есть) / `test_llm.py` — reasoning доходит до тела запроса.

**Frontend — модалка и флоу:**
- `frontend/src/api.ts` — `getModels(): Promise<ModelInfo[]>`, `getProviders()`, типы `ModelInfo`, `SkillPreview`; расширить `SkillOut`/`SkillBuilt` превью; `configureSkill(skillId, {model, provider, reasoning})`.
- `frontend/src/components/SkillSettingsModal.tsx` **(новый)** — модалка с выпадающими списками модель/провайдер/reasoning (загружаются с бэка), кнопка «Сохранить».
- `frontend/src/components/Chat.tsx:75-81` — после build открывать модалку с превью конфига вместо немедленного завершения.
- `frontend/src/App.tsx` (`handleCreateSkill`) — получить `skill_id` + превью → открыть модалку → `configureSkill` → обновить список.
- `frontend/src/hooks/useSkills.ts` — состояние модалки/превью.

## План действий

1. **Расширить SkillConfig.** Добавить `provider` и `reasoning` (`config.py`), обновить сериализацию. Зафиксировать дефолты (пусто = текущий провайдер / без reasoning), чтобы старые скилы и agent-скилы CATALOG-3 не сломались.
2. **Каталог опций (backend).** Добавить `GET /models` (через `provider.list_models()`), `GET /providers` (минимум — один; структура под CATALOG-24), и определение reasoning-вариантов на модель. Расширить `ModelInfo` (`supports_reasoning`, `reasoning_variants`).
3. **Проброс reasoning в LLM-вызов.** Добавить `reasoning` в протокол `complete`/`stream_complete` (`base.py`) и в OpenRouter-запрос; передавать `skill.reasoning` из `apply.py`/`runner.py`.
4. **Двухшаговый build.** Решить схему: (рекомендация) `build_skill_from_session` создаёт `draft` и возвращает `SkillBuilt{skill_id}` + превью конфига; новый `PATCH /skills/{id}/configure` обновляет `model`/`provider`/`reasoning` (через новый `update_skill`-репометод — см. CATALOG-17 `update_skill`) **до** коммита. Альтернатива: build возвращает только превью (без строки БД), сохранение — отдельный `POST`.
5. **Backend-схемы.** `SkillPreview`, `SkillConfigureRequest`, расширенный `SkillBuilt`; респонсы `/models`, `/providers`.
6. **Тесты backend.** build → превью; configure меняет поля (config_json обновлён); `/models` отдаёт список; reasoning доходит до провайдера; back-comat (скил без provider/reasoning работает).
7. **Фронтенд — API.** `getModels`, `getProviders`, `configureSkill`, типы.
8. **Фронтенд — модалка.** `SkillSettingsModal`: селекты модель/провайдер/reasoning (опции грузятся), кнопка «Сохранить». Открывается после build с превью. После сохранения — обновить список скиллов и закрыть модалку.
9. **Фронтенд — флоу.** `handleCreateSkill` получает `skill_id`+превью, открывает модалку; `Chat`/`App` пробрасывают состояние.
10. **Ручная проверка.** Создать скилл из сессии → открывается модалка → выбрать модель/провайдер/reasoning → сохранить → скил в списке с выбранным конфигом; применить — использует выбранную модель/провайдер/reasoning.

## Критерии приёмки (Definition of Done)

- [ ] После сборки скила из сессии **открывается модалка настройки** перед финальным сохранением (не «сразу в draft без ревью»).
- [ ] В модалке пользователь выбирает **модель** (из списка `GET /models`), **провайдер** (`GET /providers`), **режим рассуждений** (варианты, поддерживаемые выбранной моделью).
- [ ] `SkillConfig` хранит `provider` и `reasoning` (сериализация/десериализация); старые конфиги без них совместимы.
- [ ] При apply выбранные модель/провайдер/reasoning фактически используются при вызове LLM (reasoning доходит до тела запроса провайдера).
- [ ] Эндпоинты `GET /models` и `GET /providers` отдают доступные опции; reasoning-варианты корректны для моделей, где применимо.
- [ ] Обратная совместимость: скилы, собранные без настройки модалки (provider/reasoning пусты), работают как раньше.
- [ ] Согласована интеграция с CATALOG-24 (множественность провайдеров): структура `/providers` готова к добавлению zai.
- [ ] `backend`: `pytest backend/tests` зелёные, добавлены кейсы build→configure→commit и `/models`.
- [ ] `backend`: `ruff check backend` без ошибок.
- [ ] `frontend`: `npm run typecheck`/`npm run lint` проходят.
