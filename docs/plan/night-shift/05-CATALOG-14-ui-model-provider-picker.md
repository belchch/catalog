# CATALOG-14 — UI выбора модели и провайдера (конфиг из env → UI)

- **Задача Plane:** [CATALOG-14](https://app.plane.so/belchch/projects/catalog-app/work-items/14) (id: `45be521d-4268-4edf-8001-cd2146b8b11c`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Предпосылки:** CATALOG-24 (фабрика провайдеров); CATALOG-6 (каталог `/models`/`/providers` — переиспользовать, не дублировать)
- **Цель:** Дать пользователю в UI **самостоятельно выбирать модель и провайдера** — перенести этот конфиг из переменных окружения в интерфейс. Выбранные значения становятся активной runtime-конфигурацией, используемой планировщиком и применением скилов. Опирается на мульти-провайдерную фабрику из [CATALOG-24](https://app.plane.so/belchch/projects/catalog-app/work-items/24) и каталог моделей/провайдеров из [CATALOG-6](https://app.plane.so/belchch/projects/catalog-app/work-items/6).

## Контекст

Сейчас модель и провайдер **зафиксированы на старте из env**, без возможности менять в UI:

- **Стартап:** `Settings` (`backend/app/config.py:29-49`) — `@dataclass(frozen=True)`; `default_model`/`api_key`/`base_url` читаются из env один раз. `main.py:45` инстанцирует **один** `OpenRouterProvider` в `app.state.provider`. Каталог-24 вводит фабрику `build_providers(...) -> dict[str, LLMProvider]` + активный провайдер через env `APP_PROVIDER` (план CATALOG-24, п.5) — но выбор всё ещё env-driven, не UI-driven.
- **Использование модели:** планировщик WS `session_ws` (`backend/app/api/sessions.py:100`) зовёт `run_agent(model=settings.default_model, ...)`; apply берёт `skill.model` (`backend/app/skills/apply.py:134`) из конфига скила. Глобальной «активной модели» в рантайме нет — есть только `settings.default_model`.
- **Каталог моделей:** `LLMProvider.list_models()` (`backend/app/llm/base.py:48`) есть, но **эндпоинты `GET /models`/`GET /providers` не проброшены** (это нужно и CATALOG-6). `ModelInfo{id,name,context_length}` (`base.py:32-36`).
- **Фронтенд:** `App.tsx:72-107` — `<header>` (`App.tsx:74-76`, только заголовок) + сайдбар + `Chat`/`RunView`. Никакого селектора модели/провайдера нет. Конфиг на фронтенде не хранится.

Разрыв: нужно (1) runtime-выбор активного провайдера/модели, mutable поверх frozen `Settings`; (2) эндпоинты каталога + установки выбора; (3) UI-селектор с сохранением выбора (localStorage и/или бэкенд-преференс).

## Затрагиваемые файлы

**Backend — runtime-выбор (поверх CATALOG-24):**
- `backend/app/main.py` — после фабрики провайдеров (`app.state.providers`, CATALOG-24) завести **mutable** активное состояние: `app.state.active_provider: str` и `app.state.active_model: str` (инициализация из env `APP_PROVIDER`/`default_model`); заморозка `Settings` не нарушается — выбор живёт отдельно.
- `backend/app/api/sessions.py:100` — `run_agent(model=active_model, provider=active_provider, ...)` вместо `settings.default_model`.
- `backend/app/agent/runner.py` / `apply.py` — получать провайдера/модель из активного состояния (apply: если у скила не задан `model`/`provider` — брать активный глобальный).
- (опц.) `backend/app/api/deps.py` — `get_active_provider()`/`get_active_model()` хелперы.

**Backend — каталог + установка:**
- `backend/app/api/models.py` **(новый)** или в `skills.py`/`sessions.py`:
  - `GET /providers` — список доступных (`list(app.state.providers.keys())` + человекочитаемые имена).
  - `GET /providers/{provider_id}/models` — `providers[provider_id].list_models()` (или `GET /models` для активного).
  - `POST /settings` (или `PATCH`) — `{provider?, model?}` обновляет `app.state.active_provider`/`active_model`; (опц.) персистенция преференса (в БД/файл), чтобы выбор переживал рестарт.
- `backend/app/main.py:70` — подключить роутер.
- `backend/app/api/schemas.py` — `ProviderOut`, `ModelOut`, `SettingsUpdate{provider?, model?}`, `SettingsOut{provider, model}`.

**Backend — тесты:**
- `backend/tests/test_api.py` — `GET /providers`/`/models` отдают список; `POST /settings` меняет активную модель/провайдера; планировщик/apply используют обновлённый выбор.

**Frontend:**
- `frontend/src/api.ts` — `getProviders()`, `getModels(providerId)`, `getSettings()`, `updateSettings({provider, model})`; типы `ProviderOut`, `ModelOut`.
- `frontend/src/components/ModelSelector.tsx` **(новый)** — выпадающие списки провайдер + модель (модели грузятся по выбранному провайдеру); сохранение через `updateSettings` и в `localStorage` (seed при первом входе).
- `frontend/src/App.tsx:74-76` — разместить `ModelSelector` в `<header>`; хранить текущий выбор в состоянии/хуке.
- `frontend/src/hooks/useSettings.ts` **(новый, опц.)** — загрузка/сохранение выбора, синхронизация с бэком.

## План действий

1. **Зависимости.** Зафиксировать опору на CATALOG-24 (фабрика провайдеров `app.state.providers`) и CATALOG-6 (общие `/models`/`/providers`). Если они не смержены — реализовать минимально (один провайдер), но структуру держать под мульти.
2. **Runtime-выбор (backend).** В `main.py` добавить mutable `active_provider`/`active_model` (поверх frozen `Settings`); seeded из env. Хелперы в `deps.py`.
3. **Проброс в исполнение.** Планировщик (`sessions.py:100`) и apply (`apply.py`) используют активную модель/провайдера (apply: дефолт из активной, если скил не переопределяет — согласовать с CATALOG-6 per-skill config).
4. **Эндпоинты каталога.** `GET /providers`, `GET /providers/{id}/models`, `GET /settings`, `POST /settings` (обновить активный выбор). Подключить роутер.
5. **Схемы.** `ProviderOut`, `ModelOut`, `SettingsUpdate`, `SettingsOut`.
6. **Тесты backend.** Каталог отдаёт списки; `POST /settings` меняет выбор; планировщик использует обновлённую модель; back-comat (env по умолчанию).
7. **Фронтенд — API.** `getProviders`, `getModels`, `getSettings`, `updateSettings`.
8. **Фронтенд — селектор.** `ModelSelector`: провайдер → подгрузка моделей → выбор; сохранение на бэк + `localStorage` (seed при пустом); размещение в `header` (`App.tsx:74-76`).
9. **Ручная проверка.** В шапке выбрать провайдера и модель → планировщик/apply используют их; выбор переживает перезагрузку страницы; env остаётся только для API-ключей/дефолта.

## Критерии приёмки (Definition of Done)

- [ ] В UI (шапка) есть селекторы **провайдера** и **модели**; модели подгружаются по выбранному провайдеру.
- [ ] Выбранные модель/провайдер становятся активной runtime-конфигурацией: планировщик и apply используют их (а не только `settings.default_model`).
- [ ] Выбор сохраняется (переживает перезагрузку — `localStorage` и/или бэкенд-преференс); env остаётся источником API-ключей и начального дефолта.
- [ ] Эндпоинты `GET /providers`, `GET /providers/{id}/models`, `GET/POST /settings` работают.
- [ ] Согласовано с CATALOG-24 (мульти-провайдер) и CATALOG-6 (per-skill config): глобальный выбор ≠ per-skill; apply предпочитает per-skill, если задан.
- [ ] `backend`: `pytest backend/tests` зелёные, добавлены кейсы каталога/`/settings`.
- [ ] `backend`: `ruff check backend` без ошибок.
- [ ] `frontend`: `npm run typecheck`/`npm run lint` проходят.
