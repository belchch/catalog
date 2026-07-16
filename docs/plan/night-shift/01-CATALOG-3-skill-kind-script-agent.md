# CATALOG-3 — Скилы с типами: детерминированный (Python-скрипт) vs умный (агент)

- **Задача Plane:** [CATALOG-3](https://app.plane.so/belchch/projects/catalog-app/work-items/3) (id: `746a71f0-d334-4aeb-98b7-50817887d2af`, state: In Progress)
- **Статус плана:** Analyzed
- **Предпосылки:** нет (база для CATALOG-8, CATALOG-16)
- **Цель:** Ввести у скила поле **типа** (`kind`): `agent` (умный/смешанный — текущее поведение, агент-луп + LLM) и `script` (детерминированный — чистый Python-код без агент-лупа и без вызова LLM). Дать пользователю/модели выбирать тип при создании; модель должна определять, возможен ли детерминизм для данной задачи, и если нет — сообщать об этом и предлагать вариант `agent`. Связан с [CATALOG-8](https://app.plane.so/belchch/projects/catalog-app/work-items/8) (теги `python`/`ai` на UI).

## Контекст

Сейчас **все скилы — одного (агентского) типа**, и это закреплено архитектурой:

- `SkillConfig` (`backend/app/skills/config.py:28-40`) — это «замороженный конфиг агента»: `system_prompt, allowed_tools, model, temperature, max_iterations, max_retries, verify_checks, output_kind`. Понятия «скрипт» или «тип скила» **нет**. Сериализуется целиком в `config_json` (`config.py:42-61`).
- **Создание:** `build_skill_from_session` (`backend/app/api/skills.py:113-195`) гоняет один function-calling-оборот LLM с инструментом `build_skill` (`skills.py:69-73`), чья JSON-схема `_BUILD_SKILL_PARAMETERS` (`skills.py:42-67`) **зеркалит поля SkillConfig** — поля `kind`/`code` там нет. Результат валидируется (`_validate_config`, `skills.py:99-110`: только проверка имён инструментов и verify-checks) и сохраняется через `create_skill` (`repo_skill.py:50-67`) со статусом `draft`. Системный промпт билдера `BUILD_SKILL_SYSTEM_PROMPT` (`skills.py:32-39`) требует только собрать конфиг агента.
- **Выполнение:** `apply_skill` / `apply_skill_collect` (`backend/app/skills/apply.py:64-326`) **всегда** запускает агент-луп `_run_agent_core` (`apply.py:133-149`) — тот самый function-calling loop (`backend/app/agent/runner.py:74-173`: stream/complete → tool_calls → execute → feed back). Альтернативного пути «выполнить чистый скрипт» нет. Результат сохраняется как документ (`apply.py:184-199`, ADR-0006 results-are-documents, `kind="result_md"`) и пишется в `skill_run` (`finish_run`, `apply.py:204-211`).
- **Хранилище:** таблица `skill` (`schema.py:27-31`) хранит `config_json TEXT` целиком — тип можно нести **внутри** `config_json` (поле `kind`) без отдельной колонки; `SkillOut` (`schemas.py:15-20`) отдаёт только `id/name/description/status/created_at` — тип на UI пока не передаётся (это зона CATALOG-8).
- **Дизайн-напряжение (важно):** ADR-0002 (`docs/adr/0002-skill-as-frozen-config.md`) и ADR-0003 (`docs/adr/0003-code-via-tool-layer.md`) **явно отклонили** генерацию `.py` под каждый скил (причины: исполнение произвольного кода без sandbox + недетерминизм кодогенерации; код — это «слой инструментов», а не тип шага). CATALOG-3 **пересматривает** это: вводит исполнение пользовательского Python-кода, но в **детерминированной** форме (нет агент-лупа, нет LLM в рантайме). Это требует нового/дополняющего ADR и решения по **песочнице** (см. ниже).

Связь с CATALOG-8: тег `python` ставится скилам типа `script`; тег `ai` — скилам типа `agent` (т.к. те обращаются к моделям). Тип `kind`, введённый здесь, — единственный источник этих тегов.

## Затрагиваемые файлы

**Backend — конфиг и данные:**
- `backend/app/skills/config.py` — добавить поле `kind: str = "agent"` в `SkillConfig` (`"agent" | "script"`) и поле `code: str = ""` для исходника скрипта (актуально только при `kind="script"`); обновить `to_json`/`from_json` (`config.py:42-83`).
- `backend/app/storage/schema.py` — колонка `skill` НЕ меняется (тип живёт в `config_json`), но при выборе «хранить код отдельным файлом в workspace/» — нужна схема хранения (решение ниже).

**Backend — создание скила (выбор типа + детерминизм):**
- `backend/app/api/skills.py`:
  - `_BUILD_SKILL_PARAMETERS` (`skills.py:42-67`) — добавить поля `kind` (enum `agent|script`) и `code` (string, только для `script`).
  - `BUILD_SKILL_SYSTEM_PROMPT` (`skills.py:32-39`) — инструкция модели: **сначала оценить детерминизм** задачи; если задача сводится к чистой обработке текста/данных без суждений и рассуждений → `kind="script"` + сгенерировать `code`; иначе `kind="agent"`. При невозможности детерминизма модель **сообщает причину** и предлагает `agent`.
  - `_args_to_config` (`skills.py:76-96`) — проброс `kind`/`code`; при `script` — `allowed_tools=[]`, `model` не важен.
  - `_validate_config` (`skills.py:99-110`) — новые проверки: для `script` — `code` непустой, синтаксически валидный (`ast.parse`), нет запрещённых импортов/опасных вызовов (sandbox-policy); для `agent` — текущие проверки.
  - Опционально: новый инструмент `explain_non_determinism` или текстовое поле, чтобы модель объяснила, почему детерминизм невозможен (требование задачи «модель должна сообщать»).

**Backend — выполнение script-скила (новый путь, без агент-лупа):**
- `backend/app/skills/apply.py` — в `apply_skill`/`apply_skill_collect` (`apply.py:64-326`) ветвление по `skill.kind`: если `script` → вызывать новый исполнитель скрипта вместо `_run_agent_core`; результат текста проходит те же `run_verify` (`apply.py:154`) и ту же персистенцию документа (`apply.py:184-199`), чтобы contract `skill_run`/`result_md` не изменился.
- `backend/app/skills/script_runner.py` **(новый)** — детерминированный исполнитель: `run_script(code, doc_text, params) -> str`. Sandbox: ограниченный набор разрешённых модулей (via import-хук / `RestrictedPython` / subprocess с seccomp-аналогом), таймаут, ограничение памяти. Скрипт получает на вход текст документа и возвращает строку. Без доступа к LLM, сети, файловой системе вне разрешённого.
- `backend/app/agent/runner.py` — **не трогать** (`_run_agent_core` остаётся для `agent`-скилов).

**Backend — ADR / sandbox-решение:**
- `docs/adr/0013-script-skills.md` **(новый)** — зафиксировать: ввод `kind=script`, отказаться от тотального запрета ADR-0002 в части детерминированных скриптов, описать модель sandbox и почему скрипт-путь детерминирован (нет LLM-вызовов в рантайме).

**Backend — тесты:**
- `backend/tests/test_api.py` — кейсы build с `kind="script"` (валидный код → `draft`; невалидный/опасный код → 422); детерминизм-оценка (модель предлагает `agent` с объяснением).
- `backend/tests/test_apply.py` — apply script-скила: выполняется код, результат-документ создаётся, `skill_run.status="ok"`, агент-луп не запускается.
- `backend/tests/test_script_runner.py` **(новый)** — sandbox: запрещённый импорт/атака отбиваются; таймаут; чистая функция возвращает ожидаемый текст.

**Frontend (минимально, основной UI — CATALOG-8):**
- `frontend/src/api.ts` — `SkillOut`-аналог получает `kind` (или теги из CATALOG-8); здесь достаточно пробросить `kind`.
- `frontend/src/components/SkillsPanel.tsx` — отображение типа/тега (см. CATALOG-8); в рамках CATALOG-3 — опционально, пометка `script`/`agent`.

## План действий

1. **Решение по sandbox (блокирующее).** До кода выбрать модель исполнения пользовательского Python: (a) `RestrictedPython`/AST-фильтр с белым списком модулей в текущем процессе — просто, но риск побега; (b) subprocess в изоляции + таймаут + no-network — надёжнее; (c) отложенный «проксирующий» исполнитель (в v1 — заглушка, скрипт = зарегистрированная builtin-функция). Зафиксировать в новом ADR-0013. Минимум для первого среза: AST-валидация (`ast.parse` + запрет `import`/`__import__`/`eval`/`exec`/`open` за пределами разрешённого) + таймаут выполнения.
2. **SkillConfig.** Добавить `kind` (`"agent"|"script"`, дефолт `"agent"` для обратной совместимости) и `code: str = ""` в `config.py`; обновить `to_json`/`from_json`. Старые скилы (без `kind`) читаются как `agent` — миграция не нужна.
3. **Build: выбор типа и оценка детерминизма.** В `skills.py`: расширить `_BUILD_SKILL_PARAMETERS` (`kind`, `code`), переписать `BUILD_SKILL_SYSTEM_PROMPT` (модель сначала решает «детерминированно ли это»), обновить `_args_to_config`. Механизм «модель сообщает о невозможности детерминизма»: модель либо вызывает `build_skill` с `kind="agent"` и текстовым `non_determinism_reason`, либо (альтернатива) при `script` и сомнении предлагает `agent` в ответе — зафиксировать один вариант.
4. **Валидация скрипта.** В `_validate_config`: для `script` — `code` непустой, `ast.parse(code)` без ошибок, AST не содержит запрещённых узлов (import запрещённых модулей, опасные callables); для `agent` — текущие проверки инструментов/checks.
5. **Script-runner.** Создать `backend/app/skills/script_runner.py`: `async def run_script(code: str, doc_text: str, params: dict) -> str` — выполняет код в sandbox (по п.1), передаёт текст документа (например, через переменную `document`/`input_text`), ожидает результат через `return`/глобальную `result`/печатный вывод. Без LLM, без сети, с таймаутом.
6. **Apply-ветвление.** В `apply.py`: если `skill.kind == "script"` → `text = await run_script(skill.code, doc_text, ...)` минуя `_run_agent_core`; далее тот же `run_verify` + персистенция `result_md` + `finish_run`. Для `agent` — без изменений. Убедиться, что `skill_run.trace` для script хранит осмысленную запись (например, `{"script": True, "ok": ...}`).
7. **Тесты.** Backend: build script-скила (успех/невалидный код/опасный код → 422); apply script-скила (детерминированный результат, документ создан, run=ok); sandbox (запрещённый импорт отбит, таймаут срабатывает); оценка детерминизма (модель выбирает `agent` с объяснением). Проверить, что существующие agent-скилы работают без регрессий.
8. **ADR-0013.** Документировать пересмотр ADR-0002/0003: детерминированные скрипты допускаются как новый `kind`, модель sandbox, почему это не нарушает «код — слой инструментов» (т.к. скрипт-скил — это самостоятельный детерминированный исполнитель, а не замена инструментов агентского скила).
9. **Фронт (минимум).** Пробросить `kind` в `SkillOut`-ответ; основное отображение тегов `python`/`ai` — в CATALOG-8 (выполняется отдельно).

## Критерии приёмки (Definition of Done)

- [ ] `SkillConfig` имеет поле `kind` (`"agent"|"script"`, дефолт `"agent"`) и `code` для скриптов; сериализация/десериализация сохраняет их; старые `config_json` без `kind` совместимы.
- [ ] При создании скила модель **выбирает тип**: если задача детерминирована — `script` + валидный Python-код; если нет — `agent` **с объяснением** причины недетерминизма.
- [ ] `build_skill` с `kind="script"` + опасный/невалидный код → 422 с понятной причиной (синтаксис / запрещённый импорт).
- [ ] `apply_skill` для `script`-скила **не запускает агент-луп** (`_run_agent_core` не вызывается) и не делает LLM-вызов в рантайме — результат детерминирован (одинаковый вход → одинаковый выход).
- [ ] Результат `script`-скила сохраняется как документ (`kind="result_md`), `skill_run.status="ok"` — тот же contract персистенции, что и у agent-скилов.
- [ ] Sandbox отбивает запрещённые операции (запрещённый `import`, `open` файловой системы, `eval`/`exec`, выход в сеть) и таймаут; подтверждено тестами.
- [ ] Существующие agent-скилы работают без регрессий (build/apply/verify — зелёные).
- [ ] Написан ADR-0013, описывающий пересмотр ADR-0002/0003 и модель sandbox.
- [ ] `backend`: `pytest backend/tests` зелёные, добавлены тесты script-runner/build/apply для нового типа.
- [ ] `backend`: `ruff check backend` без ошибок.
- [ ] Согласована интеграция с CATALOG-8: поле `kind` — источник тегов `python` (`script`) / `ai` (`agent`) на UI.
