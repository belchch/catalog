# CATALOG-94 — GET /setup: полный список провайдеров со статусом ключа и признаком env

- **Задача Plane:** [CATALOG-94](https://app.plane.so/belchch/projects/catalog-app/work-items/94) (id: `d9b9f715-2691-4607-8949-a33e345e61c7`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 09 · blocking CATALOG-95
- **Цель:** Добавить в `GET /setup` поле `providers` со списком всех *известных* провайдеров (`id`, `name`, `configured`, `managed_by_env`, `active`), вынести перечень провайдеров в явный реестр вместо вывода из собранных инстансов и сохранить существующие поля ответа. Ключи по-прежнему нигде не отдаются.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи; комментариев нет)_

### Контекст
Сейчас ключ провайдера можно ввести только один раз, на онбординге (`frontend/src/components/SetupKeyScreen.tsx`). После сохранения флаг `keysConfigured` становится `true`, экран исчезает, и второй провайдер подключить неоткуда.

Замкнутый круг: `build_providers` создаёт z.ai только при наличии ключа (`backend/catalog/llm/factory.py:38-41`), поэтому `GET /providers` его не возвращает, и в UI он не появляется. А ввести ключ негде.

Бэкенд при этом уже умеет всё нужное: `PUT /setup/keys` поддерживает частичное обновление (`set_api_keys` в `storage/repo_app_settings.py:44`) и дёргает `apply_runtime_providers()`, то есть пересобирает провайдеров без рестарта.

Не хватает только данных для экрана настроек: списка *известных* провайдеров (а не только собранных) и информации о том, какие ключи заданы через окружение.

### Что сделать
1. Расширить `GET /setup` (`backend/catalog/api/models.py:158`) — добавить поле `providers: list[ProviderSetupOut]`, где для каждого известного провайдера отдаётся:
   - `id` — `openrouter` | `zai`
   - `name` — человекочитаемое имя
   - `configured` — есть ли непустой ключ
   - `managed_by_env` — ключ задан через переменную окружения
   - `active` — совпадает с `app.state.active_provider`
2. Источник перечня известных провайдеров вынести из `factory.py` в явную константу/реестр, чтобы список не зависел от того, какие инстансы удалось собрать.
3. `managed_by_env` считать по наличию соответствующей env-переменной (`OPENROUTER_API_KEY` / `ZAI_API_KEY`) — это важно, потому что `resolve_provider_keys` (`config.py:52`) отдаёт env приоритет над БД, и запись через UI в таком случае молча не сработает.
4. Существующие поля `keys_configured`, `provider`, `openrouter_configured`, `zai_configured` сохранить — фронт на них завязан.

### Критерии приёмки
Перенесены в раздел ниже.

## Предыстория
_нет — комментариев к задаче не было._

## Контекст
- Схема ответа: `SetupOut` — `backend/catalog/api/schemas.py:251-255` (`keys_configured`, `provider`, `openrouter_configured`, `zai_configured`). Ключей в ней нет и быть не должно. Рядом уже есть похожая по форме `ProviderOut` (`schemas.py:234-237`: `id`, `name`, `active`) — новую `ProviderSetupOut` логично положить сразу перед `SetupOut`.
- Сборка ответа — `_setup_status` в `backend/catalog/api/models.py:28-45`. Важно: у функции **две** ветки. Если `app.state.settings` отсутствует (`:31-39`), данные берутся напрямую из БД (`get_app_settings`, `get_api_keys`); иначе (`:40-45`) — из `settings`. Поле `providers` надо наполнять в обеих ветках, иначе ответ окажется неконсистентным на раннем старте.
- Эндпоинты, использующие `_setup_status`: `GET /setup` (`models.py:158-162`) и `PUT /setup/keys` (`models.py:165-188`). Второй уже делает частичное обновление через `set_api_keys` (`:173-177`), перечитывает ключи (`:178`), пересобирает `Settings` через `with_resolved_keys` (`:182-186`) и вызывает `apply_runtime_providers` (`:187`) — то есть требование «провайдер появляется в `GET /providers` без рестарта» уже обеспечено этим кодом, задача — не сломать его и покрыть тестом.
- Частичность `set_api_keys` подтверждена: `backend/catalog/storage/repo_app_settings.py:44-61` — `None` означает «не менять» (`:51-52`), запись идёт через `INSERT … ON CONFLICT DO UPDATE`. Регрессионный тест из критериев приёмки проверяет именно это.
- Приоритет env над БД: `resolve_provider_keys` — `backend/catalog/config.py:52-62`, читает `os.getenv` **в момент вызова** (`:57-58`), а не модульные константы `OPENROUTER_API_KEY` / `ZAI_API_KEY` (`config.py:11`, `:16`), захваченные при импорте. Значит `managed_by_env` тоже нужно считать через `os.getenv(...).strip()` в момент запроса — тогда поведение совпадёт с `resolve_provider_keys` и станет тестируемым через `monkeypatch.setenv`.
- Текущий источник перечня провайдеров — `build_providers` в `backend/catalog/llm/factory.py:23-48`: `openrouter` создаётся всегда (`:34-36`), `zai` — только при непустом `settings.zai_api_key` (`:38-41`). Именно отсюда `GET /providers` (`models.py:68-82`) получает список, поэтому незаконфигуренный провайдер в UI не виден. Реестр должен хранить для каждого провайдера: `id`, человекочитаемое `name`, имя env-переменной и поле в `Settings` с ключом.
- `GET /providers` сейчас использует id как отображаемое имя (`ProviderOut(id=name, name=name, …)`, `models.py:76`). После появления реестра его тоже стоит подпитать человекочитаемыми именами — но строго в рамках обратной совместимости: `id` менять нельзя, на нём завязаны `POST /settings` (`models.py:128-133`) и `provider_for_skill` (`factory.py:86-101`).
- `active`: источник — `request.app.state.active_provider` (уже читается в `_setup_status:30`).
- Существующие тесты, которые нельзя ломать: `backend/tests/test_setup_keys.py` — `test_resolve_provider_keys_env_overrides_persisted` (`:17`), `test_resolve_provider_keys_falls_back_to_persisted` (`:26`), `test_apply_runtime_providers_resets_model_on_fallback` (`:53`), `test_setup_endpoints_hide_secrets` (`:87`); `backend/tests/test_api.py::test_list_providers_endpoint` (`:1032`), `test_update_settings_unknown_provider_404` (`:1088`), `test_update_settings_switches_active_provider` (`:1094`).
- Парный шаг: [CATALOG-95](docs/plan/night-shift/10-CATALOG-95-ui-settings-provider-keys.md) — экран настроек, который потребляет это поле. Он зависит от текущей задачи, `code` выполняется раньше `ui`. Другой тикет-потребитель — тот же CATALOG-95 (правка активного провайдера в онбординге).
- Проверки бэкенда: `ruff check .` и `pytest` из `backend/`.

## Затрагиваемые файлы
- `backend/catalog/llm/providers.py` (новый; допустимо `registry.py`) — явный реестр известных провайдеров: `id`, отображаемое имя, имя env-переменной ключа, имя поля ключа в `Settings`.
- `backend/catalog/llm/factory.py` — `build_providers` строит инстансы по реестру вместо жёстко прописанных двух веток (`:34-41`), поведение сохраняется: openrouter создаётся всегда, остальные — при непустом ключе.
- `backend/catalog/api/schemas.py` — новая модель `ProviderSetupOut` (`id`, `name`, `configured`, `managed_by_env`, `active`) и поле `providers: list[ProviderSetupOut]` в `SetupOut` (`:251-255`); существующие поля не трогаем.
- `backend/catalog/api/models.py` — `_setup_status` (`:28-45`) наполняет `providers` в обеих ветках; при желании `list_providers_endpoint` (`:68-82`) берёт человекочитаемые имена из реестра.
- `backend/catalog/config.py` — при необходимости хелпер «ключ провайдера задан через env» рядом с `resolve_provider_keys` (`:52-62`), чтобы логика env-приоритета жила в одном месте.
- `backend/tests/test_setup_keys.py` — новые тесты: оба провайдера в ответе при одном настроенном; `configured: false` без ключа; `managed_by_env: true` при выставленной env вне зависимости от БД; частичный `PUT /setup/keys` не затирает второй ключ; после `PUT` с ключом z.ai провайдер виден в `GET /providers`.

## План действий
1. Ввести реестр известных провайдеров: список записей `(id, display_name, env_var, settings_field)` для `openrouter` и `zai`. Положить его в отдельный модуль `backend/catalog/llm/providers.py`, чтобы он не тянул за собой `httpx` и был импортируем из API-слоя.
2. Переписать `build_providers` (`factory.py:23-48`) на обход реестра: openrouter создаётся всегда (сохранить текущее поведение и комментарий про back-compat), остальные — только при непустом ключе из соответствующего поля `Settings`. Лог `build_providers` (`:43-47`) оставить.
3. Добавить в `config.py` (рядом с `resolve_provider_keys`, `:52-62`) функцию проверки «ключ задан через окружение» по имени env-переменной, читающую `os.getenv(...).strip()` в момент вызова.
4. Описать `ProviderSetupOut` в `schemas.py` (перед `SetupOut`, `:251`): `id: str`, `name: str`, `configured: bool`, `managed_by_env: bool`, `active: bool = False`. Добавить в `SetupOut` поле `providers: list[ProviderSetupOut]` со значением по умолчанию `[]`, чтобы не ломать конструирование в тестах.
5. В `_setup_status` (`models.py:28-45`) собрать `providers` по реестру: `configured` — по непустому ключу (в ветке без `settings` — из `get_api_keys`, в основной — из полей `Settings`), `managed_by_env` — через новый хелпер, `active` — сравнение `id` с `app.state.active_provider`. Заполнить в **обеих** ветках.
6. Сохранить существующие поля ответа (`keys_configured`, `provider`, `openrouter_configured`, `zai_configured`) без изменения семантики — фронт на них завязан.
7. Опционально: подставить человекочитаемые имена из реестра в `list_providers_endpoint` (`models.py:75-78`), не меняя `id`. Проверить `test_list_providers_endpoint` (`test_api.py:1032`) и при необходимости обновить его ожидания.
8. Убедиться, что ни один эндпоинт не отдаёт ключ в открытом виде: `SetupOut` полей с ключами не получает, `test_setup_endpoints_hide_secrets` (`test_setup_keys.py:87`) остаётся зелёным (при необходимости расширить его на новое поле `providers`).
9. Написать тесты в `backend/tests/test_setup_keys.py`: (а) `GET /setup` возвращает оба провайдера при настроенном только openrouter; (б) `configured: false` у провайдера без ключа; (в) `managed_by_env: true` при `monkeypatch.setenv("ZAI_API_KEY", …)` даже когда в `app_settings` пусто или лежит другое значение; (г) `PUT /setup/keys` только с `zai_api_key` не затирает openrouter-ключ; (д) после такого `PUT` провайдер `zai` присутствует в `GET /providers` без перезапуска процесса.
10. Прогнать из `backend/`: `ruff check .` и `pytest`.

## Критерии приёмки (Definition of Done)
- [ ] `GET /setup` возвращает оба провайдера даже когда настроен только один.
- [ ] У провайдера без ключа: `configured: false`.
- [ ] При заданной env-переменной: `managed_by_env: true` независимо от того, что лежит в `app_settings`.
- [ ] Поле `active` совпадает с `app.state.active_provider`.
- [ ] Перечень провайдеров берётся из явного реестра, а не из собранных инстансов; `build_providers` использует тот же реестр.
- [ ] Существующие поля `keys_configured`, `provider`, `openrouter_configured`, `zai_configured` сохранены и не изменили семантику.
- [ ] `providers` заполняется и в ветке `_setup_status` без `app.state.settings`.
- [ ] `PUT /setup/keys` с одним полем не затирает второй ключ (регрессионный тест на `set_api_keys`).
- [ ] После `PUT /setup/keys` с ключом z.ai провайдер появляется в `GET /providers` без перезапуска процесса.
- [ ] Ключи ни в одном ответе API не возвращаются в открытом виде.
- [ ] Зелёные: `ruff check .`, `pytest` (из `backend/`).
