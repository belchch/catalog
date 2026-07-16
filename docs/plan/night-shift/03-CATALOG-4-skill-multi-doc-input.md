# CATALOG-4 — Скил принимает один, два или список документов

- **Задача Plane:** [CATALOG-4](https://app.plane.so/belchch/projects/catalog-app/work-items/4) (id: `d3cdce71-2b55-4276-8e77-5a949a1ba52e`, state: In Progress)
- **Статус плана:** Analyzed
- **Предпосылки:** нет (паттерн безопасного ALTER TABLE — см. CATALOG-17)
- **Цель:** Позволить скилу принимать на вход **несколько документов** (один, два или произвольный список) вместо строго одного. Расширить модель данных (`skill_run`, `ApplyRequest`, при необходимости `SkillConfig` для декларации ожидаемого числа входов) и доработать UI выбора документов. Существующий сингл-документный поток должен сохраниться как частный случай (обратная совместимость).

## Контекст

Сейчас apply-поток **жёстко завязан на один входной документ** на всех слоях:

- **API apply:** `POST /skills/{skill_id}/apply` (`backend/app/api/runs.py:27-44`) принимает `ApplyRequest{doc_id: str}` (`backend/app/api/schemas.py:23-24`) — **одно** поле, не список. Создаёт `skill_run` через `create_run(..., input_doc_id=req.doc_id)`.
- **WS-стрим:** `run_stream_ws` (`runs.py:67-139`) читает `run["input_doc_id"]` (`runs.py:94-100`), проверяет непустоту одного id и передаёт его в `apply_skill(input_doc_id=input_doc_id)` (`runs.py:113`).
- **Apply-ядро:** `_apply_core` (`backend/app/skills/apply.py:59-115`) грузит один документ `get_document(db, input_doc_id)` (`apply.py:90`, 404-raise если нет) и формирует **одно** стартовое сообщение `f"Обработай документ {input_doc_id} ({doc.title})."` (`apply.py:111-114`), на которое агент опирается. `create_run` пишет `input_doc_id` в строку (`apply.py:99-101`).
- **Хранилище:** таблица `skill_run` (`backend/app/storage/schema.py:32-37`) имеет колонку `input_doc_id TEXT` — **один** id. Миграционного фреймворка нет (`schema.py:1-8`: только `CREATE TABLE IF NOT EXISTS`, single source of truth), поэтому новая колонка/таблица требует безопасного `ALTER TABLE` (как в плане CATALOG-17).
- **Инструменты документов:** агент дополнительно читает контент через `read_document(doc_id)` (`backend/app/documents/tools.py:28-53`) и видит список через `list_documents` (`tools.py:22`). Это уже поддерживает любой документ по id, но первичный «вход» — один.
- **Фронтенд:** `SkillsPanel.tsx:60-80` рендерит **один** `<select>` на скилл (`target[s.id]`, `SkillsPanel.tsx:13,30`); `onApply(skillId, docId)` принимает один id (`SkillsPanel.tsx:9,77`). Цепочка вызовов: `SkillsPanel` → `App.tsx:60-63` (`handleApply`) → `useSkills.apply(skillId, docId)` (`frontend/src/hooks/useSkills.ts:38-39`) → `applySkill(skillId, docId)` (`frontend/src/api.ts:90-95`, тело `{doc_id: docId}`).

Декларация «сколько входов ждёт скил» сейчас **отсутствует** — `SkillConfig` (`config.py:28-40`) не несёт arity. Задача («скилы могут принимать один, два или список») подразумевает, что набор входов определяется пользователем при применении и/или декларируется скилом. Решение о том, нужно ли поле arity в `SkillConfig`, — ниже.

## Затрагиваемые файлы

**Backend — модель данных:**
- `backend/app/storage/schema.py:32-37` — добавить хранение списка входных документов. Вариант A (предпочтительный, минимальный): новая колонка `input_doc_ids TEXT` (JSON-массив) рядом с `input_doc_id` (последний сохранить как «первый/legacy» для обратной совместимости + `ALTER TABLE ... ADD COLUMN input_doc_ids TEXT` в safe-стиле). Вариант B: связь many-to-many через таблицу `skill_run_doc(run_id, doc_id, position)` — чище, но больше кода. Зафиксировать A в плане.
- `backend/app/skills/repo_run.py` — `create_run(..., input_doc_ids: list[str] | None)` сериализует JSON-массив в `input_doc_ids` и пишет первый id в `input_doc_id` (back-compat); `get_run` отдаёт `input_doc_ids` (десериализует JSON → list) рядом с `input_doc_id` (`repo_run.py:59-80`).
- `backend/app/skills/config.py:28-40` — (опционально, по решению) поле `input_arity: int | None` (1/2/None=список) для декларации скилом ожидаемого числа входов; сериализация в `to_json`/`from_json`.

**Backend — API:**
- `backend/app/api/schemas.py:23-24` — `ApplyRequest` принять список: `doc_ids: list[str]` (минимум 1). Для back-comat оставить `doc_id: str | None`; валидация: если есть `doc_id` — обернуть в `[doc_id]`, если оба пусты — 422. `RunOut` (`schemas.py:27-34`) — добавить `input_doc_ids: list[str] | None`.
- `backend/app/api/runs.py:27-44` — `apply_endpoint` строит список из `req`, передаёт в `create_run(..., input_doc_ids=...)`. WS `runs.py:94-113` — читать список `run["input_doc_ids"]`, валидировать непустоту, передавать в `apply_skill(input_doc_ids=...)`.

**Backend — apply-ядро:**
- `backend/app/skills/apply.py` — `_apply_core`/`apply_skill`/`apply_skill_collect` меняют сигнатуру с `input_doc_id: str` на `input_doc_ids: list[str]` (`apply.py:66,272,313`). Грузить все документы через `get_document` (404 если хоть одного нет), строить стартовое сообщение со списком всех входов (`apply.py:111-114`). Если скил декларирует `input_arity` — проверять совпадение числа выбранных документов (иначе ошибка/422). Лог `apply_skill start` (`apply.py:103-109`) — логировать список/число. Поведение verify/персистенции (`apply.py:154-219`) не меняется (результат — один `result_md`).

**Backend — билд скила (если вводится `input_arity`):**
- `backend/app/api/skills.py:42-67` — добавить `input_arity` в `_BUILD_SKILL_PARAMETERS`; `_args_to_config` (`skills.py:76-96`) пробрасывает его; `BUILD_SKILL_SYSTEM_PROMPT` (`skills.py:32-39`) — указание модели задать arity по смыслу задачи.

**Backend — тесты:**
- `backend/tests/test_apply.py` — кейсы: apply с 1/2/N документами (все грузятся, результат сохраняется); отсутствующий документ в списке → ошибка; несоответствие `input_arity` (если введено) → 422.
- `backend/tests/test_api.py` — `POST /skills/{id}/apply` с `doc_ids: [...]`; back-comat по `doc_id` (одно поле) по-прежнему работает; `GET /runs/{id}` отдаёт `input_doc_ids`.

**Frontend:**
- `frontend/src/api.ts:90-95` — `applySkill(skillId, docIds: string[])` → тело `{doc_ids: docIds}` (или `{doc_ids, doc_id}` для back-comat); тип `RunOut.input_doc_ids`.
- `frontend/src/hooks/useSkills.ts:38-39` — `apply(skillId, docIds: string[])`.
- `frontend/src/components/SkillsPanel.tsx:9,13,30,60-80` — замена одного `<select>` на **множественный выбор**: либо `multiple` select, либо чипы/чек-лист документов, либо динамический «+ добавить документ» (1/2/N селектов). Состояние `target` хранит список на скилл. Кнопка «Применить» disabled пока не выбран ≥1 документ; если есть `input_arity` — ровно столько.
- `frontend/src/App.tsx:60-63` — `handleApply(skillId, docIds: string[])`.

## План действий

1. **Решение по структуре хранения.** Принять вариант A: колонка `input_doc_ids TEXT` (JSON-массив) + сохранить `input_doc_id` как «первый». Решить, вводится ли `SkillConfig.input_arity` (рекомендация: да, опционально `1|2|None`, `None`=произвольный список), чтобы UI показывал нужное число селекторов и валидировать на сервере.
2. **Схема.** В `schema.py` добавить `input_doc_ids TEXT` в `skill_run` + безопасный `ALTER TABLE skill_run ADD COLUMN input_doc_ids TEXT` (catch `duplicate column`), т.к. миграций нет (аналог CATALOG-17).
3. **repo_run.** `create_run(..., input_doc_ids=...)` пишет JSON-массив и первый id в `input_doc_id`; `get_run` десериализует `input_doc_ids` → list (с fallback на `[input_doc_id]` для старых строк).
4. **API schemas.** `ApplyRequest{doc_ids: list[str], doc_id?: str}` с нормализацией → list (минимум 1, иначе 422); `RunOut.input_doc_ids`.
5. **apply-ядро.** Сигнатуры `input_doc_ids: list[str]`; грузить все, строить сообщение со списком входов; если есть `input_arity` — проверять число; логировать список; персистенция результата без изменений.
6. **Эндпоинты runs.py.** `apply_endpoint` нормализует список → `create_run`; WS читает `input_doc_ids`, валидирует, передаёт в `apply_skill`.
7. **SkillConfig + build (если введено arity).** Поле `input_arity`, schema в `build_skill`, проброс в `_args_to_config`, инструкция в системный промпт билдера.
8. **Тесты backend.** apply 1/2/N; отсутствующий doc; arity-несовпадение; back-comat `doc_id`; `GET /runs` отдаёт список.
9. **Фронтенд.** `applySkill`/`useSkills.apply` — массивы; `SkillsPanel` — множественный выбор документов (чек-лист/чипы/динамические селекторы), disabled пока <1 (или ≠ `input_arity`); `App.handleApply` — массив.
10. **Ручная проверка.** Создать скил, применить к 1, к 2, к списку документов — результат-документ создаётся, агент видит все входы; старый сингл-выбор работает.

## Критерии приёмки (Definition of Done)

- [ ] `POST /skills/{id}/apply` принимает `doc_ids` (список из ≥1 id); обратная совместимость с одиночным `doc_id` сохранена.
- [ ] `skill_run` хранит все входные документы (`input_doc_ids`); `GET /runs/{id}` возвращает список.
- [ ] `apply_skill` грузит **все** переданные документы и строит стартовый контекст агента со списком входов; отсутствующий документ → ошибка (404/ValueError), run помечается failed.
- [ ] (Если введено `input_arity`) скил декларирует ожидаемое число входов; при несоответствии — 422/ошибка с понятной причиной.
- [ ] Результат применения — один `result_md`-документ (contract ADR-0006 не изменился); verify/persist работают как прежде.
- [ ] В UI можно выбрать один, два или несколько документов для применения скила; кнопка «Применить» корректно блокируется.
- [ ] Обратная совместимость: старые скилы/runs с одним `input_doc_id` читаются и работают.
- [ ] `backend`: `pytest backend/tests` зелёные, добавлены кейсы multi-doc/arity/back-comat.
- [ ] `backend`: `ruff check backend` без ошибок.
- [ ] `frontend`: `npm run typecheck`/`npm run lint` проходят.
