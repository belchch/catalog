# CATALOG-27 — Сборка скилла: анти-доменные правила промптов + выбор трека операции пользователем

- **Задача Plane:** [CATALOG-27](https://app.plane.so/belchch/projects/catalog-app/work-items/27) (id: `76fb7636-7660-4a86-8bc0-1ef07eee3e52`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Добавить фазу A (дизамбигуация операции) — `propose_skill_tracks` + `POST /sessions/{id}/skill-tracks` с retry/валидацией; усилить `BUILD_SKILL_SYSTEM_PROMPT` анти-доменными правилами и few-shot; при сборке in-memory помечать assistant-сообщения как справочный журнал; обеспечить fallback и обратную совместимость одношагового build. UI выбора трека — в парном плане `CATALOG-27-ui-skill-track-picker.md` (после этого code-шага).

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

При сборке скилла из planner-сессии LLM цепляется к теме документов, а не к операции пользователя (кейс Go/Dart → «ревью» вместо «сравнить по топикам»). Нужна двухфазная сборка:

**Фаза A** — `propose_skill_tracks` + `POST /sessions/{id}/skill-tracks`: 1–3 трека (`name`, `description`, `operation`, `input_arity`, `rationale`). Несколько треков только при неоднозначности. Треки не персистятся как сущность БД.

**Фаза B** — существующий `build_skill_from_session` по истории, где выбранный трек — последнее авторитетное user-указание («Собери скилл по этой операции: …»).

Анти-доменные правила в промптах A и B: операция над документами, не тема; не тащить языки/продукты в name/description/system_prompt/code без явного требования; приоритет user-инструкций над пересказом ассистента; few-shot Go/Dart.

Backend-объём: инструмент + эндпоинт + retry; переработка `BUILD_SKILL_SYSTEM_PROMPT`; in-memory маркировка ролей при сборке; fallback фазы A → одношаговый build; build без `/skill-tracks` как раньше. Edit-flow (CATALOG-17): фаза A по умолчанию не нужна (намерение в конфиге). Вне объёма: персист треков, confidence, правка `PLANNER_SYSTEM_PROMPT`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

Сейчас сборка — `POST /sessions/{id}/skills` → `build_skill_from_session` (`backend/app/api/skills.py:413`):

1. Сначала `_build_skill_from_artifacts` (упаковка `session_artifact` в `SkillConfig` без LLM) — основной путь после planner.
2. Если артефактов нет — `_build_skill_from_session_llm` (`skills.py:326`): system = `BUILD_SKILL_SYSTEM_PROMPT` (`65–80`), история user/assistant как есть (`336–338`), tool `build_skill`, retry до `MAX_BUILD_ATTEMPTS` (`63`, цикл `344–388`).

Промпт сейчас только про script/agent и `input_arity` — без анти-домена. Edit: `POST /skills/{id}/edit` (`556+`) ставит `session.skill_id` и сидит артефакты; повторный build обновляет тот же skill.

**Важный зазор с dual-path:** фаза B «по истории с выбранным треком» не сработает на artifact-path (история игнорируется). Нужно явно решить: при наличии user-сообщения выбора трека (или флаге сессии) не брать чистый artifact-pack без учёта трека — например форсировать LLM-path / перепаковать meta с опорой на `operation`, иначе кейс-репродукция из ТЗ на текущем основном пути недостижима. Без выбора трека — поведение как сейчас.

Парный UI-план: `docs/plan/next-shift/CATALOG-27-ui-skill-track-picker.md` (выполнять после code).

## Затрагиваемые файлы

- `backend/app/api/skills.py` — `PROPOSE_SKILL_TRACKS_*` промпт/tool/schema; `propose_skill_tracks_from_session` + retry; `POST .../skill-tracks`; анти-домен в `BUILD_SKILL_SYSTEM_PROMPT`; in-memory префикс/пометка assistant vs user в history; тихая запись выбранного трека в messages (без planner turn); ветка build при наличии track-intent; skip/guard для edit (`session.skill_id`).
- `backend/app/api/schemas.py` — `SkillTrack`, ответ `SkillTracksOut` (и при необходимости request подтверждения выбора).
- `backend/app/storage/repo_message.py` — только если понадобится хелпер append (скорее reuse `add_message`).
- `backend/tests/test_api.py` и/или новый `backend/tests/test_skill_tracks.py` — unit/API: 1..3 трека, retry, fallback, anti-domain с fake provider, edit skip, build без tracks зелёный.
- `backend/tests/test_session_artifacts.py` — при изменении взаимодействия tracks ↔ artifact path.
- Не трогать: `PLANNER_SYSTEM_PROMPT` / flow сессии до сборки (вне объёма ТЗ).

## План действий

1. Схемы ответа: Pydantic-модели трека и списка (1..3) в `schemas.py`.
2. Tool `propose_skill_tracks` + system prompt фазы A (анти-домен + few-shot Go/Dart + «несколько треков только при неоднозначности») рядом с `BUILD_SKILL_TOOL` в `skills.py`.
3. Функция `propose_skill_tracks_from_session` по образцу `_build_skill_from_session_llm`: загрузка messages, in-memory пометки (user = intent, assistant = research journal), LLM + tool, retry/`MAX_BUILD_ATTEMPTS`, валидация длины и полей трека.
4. Эндпоинт `POST /sessions/{session_id}/skill-tracks`: при `session.skill_id` (edit) — сразу осмысленный skip (пустой список / 204 / флаг `skipped: true` — выбрать один контракт и зафиксировать во фронте); иначе вернуть треки. После исчерпания ретраев — не 5xx, а сигнал fallback (например пустой `tracks` + `fallback: true` или HTTP, который UI трактует как «сразу build»), чтобы сборка не блокировалась.
5. Тихая персистенция выбора трека: API, который делает `add_message(..., role="user", content="Собери скилл по этой операции: …")` **без** planner WS-turn (обычный `planner.send` запускает ход — нельзя). Либо отдельный `POST .../skill-tracks/select`, либо тело на build — предпочтительно select/append, затем существующий `POST .../skills`.
6. Переработать `BUILD_SKILL_SYSTEM_PROMPT`: анти-доменные правила + few-shot; тот же акцент user vs assistant journal в `_build_skill_from_session_llm` (только in-memory, БД не менять).
7. В `build_skill_from_session`: если в истории есть авторитетный track-intent — учесть его на фазе B (см. зазор в Контексте); без track-intent — текущий artifact→LLM порядок без изменений.
8. Тесты с fake provider: валидные 1/2/3 трека; невалидный ответ → retry → успех/fallback; edit-сессия не предлагает треки; build без `/skill-tracks` и golden path остаются зелёными; anti-domain: при фикстуре Go/Dart + выбранный track «сравнение по топикам» в LLM-path `name`/`description`/`system_prompt` без Go/Dart, `input_arity == 2`.

## Критерии приёмки (Definition of Done)

- [ ] `POST /sessions/{id}/skill-tracks` возвращает 1–3 валидных трека; schema и retry покрыты тестами.
- [ ] Edit-сессия (`session.skill_id`) не запускает осмысленную фазу A (skip по контракту).
- [ ] Сбой/невалид фазы A после ретраев не блокирует `POST /sessions/{id}/skills` (fallback на одношаговый build).
- [ ] `POST /sessions/{id}/skills` без предварительного `/skill-tracks` ведёт себя как раньше; существующие тесты и golden run зелёные.
- [ ] `BUILD_SKILL_SYSTEM_PROMPT` содержит анти-доменные правила и few-shot; при сборке history помечается in-memory (user intent / assistant journal), персистентные messages не меняются.
- [ ] Выбор трека можно записать user-сообщением без planner turn; при наличии этого intent фаза B учитывает операцию (не игнорирует её из‑за чистого artifact-pack).
- [ ] Unit-тесты: `propose_skill_tracks` (1..3, retry, fallback) + anti-domain поведение сборки с фейковым провайдером.
- [ ] Из `backend/`: `ruff check .`, `pytest` зелёные.
