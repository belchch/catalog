# CATALOG-16 — Расширить логирование выполнения скила (гранулярная лента шагов)

- **Задача Plane:** [CATALOG-16](https://app.plane.so/belchch/projects/catalog-app/work-items/16) (id: `5cd8a8f5-204d-4e2f-9e1d-2a68106a85bd`, state: In Progress)
- **Статус плана:** Analyzed
- **Предпосылки:** CATALOG-3 (script-события); CATALOG-24 (reasoning)
- **Цель:** Сделать ленту шагов выполнения скила **более гранулярной**: показывать в UI не только старт/финиш итерации, но и любые действия внутри — **модель, провайдер, промпт, вызовы инструментов с результатами, выполнение скрипта (для script-скилов), рассуждения (reasoning)**. Расширить набор событий/кадров и их отрисовку. Опирается на типы скилов из [CATALOG-3](https://app.plane.so/belchch/projects/catalog-app/work-items/3) (script) и reasoning из [CATALOG-24](https://app.plane.so/belchch/projects/catalog-app/work-items/24).

## Контекст

Сейчас лента шагов apply-прогона **грубая и теряет детали**:

- **События:** `AgentEvent = TokenEvent | ToolCallEvent | ToolResultEvent | StepEvent | FinishEvent | VerifyEvent` (`backend/app/agent/events.py:64`). На итерацию приходят: `StepEvent` (старт), `ToolCallEvent`/`ToolResultEvent`, `TokenEvent`, `FinishEvent`; в apply-цикле ещё `VerifyEvent` (`backend/app/skills/apply.py:154-157`). **Событий «промпт/модель/провайдер/скрипт/reasoning» нет.**
- **Маппинг в кадры:** `agent_event_to_frame` (`backend/app/api/deps.py:51-86`) отдаёт `step/token/tool_call/tool_result/verify`. Примечательно: кадр `tool_result` **уже несёт `result`** (`deps.py:75` — полный payload), но фронт его **игнорирует**.
- **Фронтенд:** `useRunStream` (`frontend/src/hooks/useRunStream.ts:38-94`) строит `RunStep[]` с kinds `step|tool_call|tool_result|verify`; при этом `tool_result` сохраняет **только** `← ${e.name}` + `ok` (`useRunStream.ts:68`) — **содержимое результата отбрасывается**. `TraceSteps` (`frontend/src/components/TraceSteps.tsx:9-31`) рисует только `s.text` + цвет + ✓/✗; для `tool_result` — имя инструмента без результата. Меты (модель/провайдер/промпт/kind) нет нигде. `RunView` (`frontend/src/components/RunView.tsx:39-60`) делит экран на «Лента шагов» + «Результат».
- **Логирование (stdout):** `log_agent_event` (`backend/app/agent/logging.py:52`) — единый источник правды, логирует события структурированно (`test_skill_logging.py:429-441` покрывает все текущие типы); новые типы нужно добавить сюда же.

Из описания задачи: «сейчас вывод только начала и конца итерации» — восприятие связано с тем, что результаты инструментов и мета не показываются, а внутритерационные действия (вызов→результат→рассуждение) не детализируются.

## Затрагиваемые файлы

**Backend — события/кадры:**
- `backend/app/agent/events.py:64` — новые события:
  - `RunMetaEvent` (или `RunStartEvent`): `model, provider, skill_kind, system_prompt(обрез.), input_docs` — эмиттится в начале apply.
  - (опц. под CATALOG-3) `ScriptEvent`: `stage(start/stdout/return/done), snippet, duration` — для script-скилов.
  - (опц. под CATALOG-24) `ReasoningEvent`: `text` — проброс `reasoning_content`.
  - расширить `AgentEvent`-union.
- `backend/app/skills/apply.py:103-115` — эмиттить `RunMetaEvent` перед циклом (модель/провайдер/kind/промпт); для script-ветки (CATALOG-3) — `ScriptEvent`-ы.
- `backend/app/agent/runner.py:120-133` — эмиттить `ReasoningEvent` при наличии `CompletionResult.reasoning` (CATALOG-24) внутри итерации.
- `backend/app/agent/logging.py:52` + `agent_event_to_frame` (`deps.py:51-86`) — логировать и маппить в кадры новые типы: `meta`, `script`, `reasoning`; для `tool_result` — гарантировать осмысленный сниппет результата (уже есть в payload, но при необходимости обрезать для кадра).

**Backend — тесты:**
- `backend/tests/test_skill_logging.py:429-441` — покрыть новые типы событий в `log_agent_event`.
- `backend/tests/test_apply.py` / `test_agent.py` — apply эмиттит `meta` (модель/промпт); reasoning/script-события доходят до стрима.

**Frontend:**
- `frontend/src/ws.ts:9-26` — добавить кадры `meta`, `script`, `reasoning` в `ServerEvent`.
- `frontend/src/hooks/useRunStream.ts:4-12,38-94` — расширить `RunStep` (kinds `meta|script|reasoning`, поля `model/provider/kind/prompt/result/...`); **сохранять `result` в `tool_result`-шаге** (сейчас отбрасывается, `useRunStream.ts:68`).
- `frontend/src/components/TraceSteps.tsx:9-31` — рендерить: мета-блок (модель/провайдер/kind/промпт) сверху; результат инструмента (сниппет, сворачиваемый); script-шаги; reasoning (приглушённо). Новые kinds со своими стилями.
- `frontend/src/components/RunView.tsx:39-60` — (опц.) шапка прогона с моделью/провайдером/kind.

## План действий

1. **Мета прогона (backend).** Ввести `RunMetaEvent{model, provider, skill_kind, system_prompt, input_docs}`; эмиттить в `apply.py` перед циклом; залогировать (`logging.py`) и отдать кадром `meta` (`deps.py`).
2. **Результаты инструментов.** Убедиться, что кадр `tool_result` несёт читаемый сниппет результата (payload уже есть — `deps.py:75`); при необходимости обрезать длинные. На фронте — **сохранять и показывать** результат (сейчас `useRunStream.ts:68` теряет его).
3. **Скрипт-события (CATALOG-3).** Для `kind=="script"` эмиттить `ScriptEvent` (старт/исходник-превью/stdout/возврат/длительность) из script-runner/apply; кадр `script`.
4. **Reasoning (CATALOG-24).** При наличии `reasoning` эмиттить `ReasoningEvent` в `runner.py`; кадр `reasoning`.
5. **Логирование (single source of truth).** Расширить `log_agent_event` (`logging.py`) под все новые типы; обновить тест `test_skill_logging.py:429-441`.
6. **Frontend ws.ts.** Кадры `meta`/`script`/`reasoning` в `ServerEvent`.
7. **Frontend useRunStream.** Расширить `RunStep` и обработку: meta, script, reasoning + сохранять `result` для tool_result.
8. **Frontend TraceSteps/RunView.** Рендерить мета-блок, сниппеты результатов, script-шаги, reasoning; согласовать стили.
9. **Тесты + ручная проверка.** Прогон показывает модель/провайдер/промпт, каждый вызов инструмента с результатом, verify, (для script) шаги скрипта, (при reasoning) рассуждения.

## Критерии приёмки (Definition of Done)

- [ ] В ленте шагов прогона видна **мета**: модель, провайдер, тип скила (kind), используемый промпт (обрезок).
- [ ] Каждый вызов инструмента показывает **аргументы и результат** (сниппет), а не только имя/✓.
- [ ] Для script-скилов (CATALOG-3) видны шаги выполнения скрипта (старт/вывод/возврат/длительность).
- [ ] При наличии reasoning (CATALOG-24) рассуждения отображаются в ленте.
- [ ] Verify-шаги и итерации видны; внутритерационные действия детализированы (не «только старт/финиш»).
- [ ] Новые события логируются через единый `log_agent_event` и покрываются тестами.
- [ ] `backend`: `pytest backend/tests` зелёные (включая расширенный `test_skill_logging.py`).
- [ ] `backend`: `ruff check backend` без ошибок.
- [ ] `frontend`: `npm run typecheck`/`npm run lint` проходят.
