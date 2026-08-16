# CATALOG-127 — Разрешить agent и pipeline скиллы как тулы сессии

- **Задача Plane:** [CATALOG-127](https://app.plane.so/belchch/projects/catalog-app/work-items/127) (id: `a1629f45-3f13-42ee-87b8-7c8c7505d1a3`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 06 · blocked_by CATALOG-126 · blocking CATALOG-128 · blocking CATALOG-129
- **Цель:** Снять script-only фильтр после работающих глубины, бюджета и дедлайна. Agent/pipeline вызываются из сессии с реальным провайдером; script по-прежнему не ходит в LLM; draft и неизвестный kind отклоняются на API.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. Только после CATALOG-124/125/126.

1. Убрать `if skill.config.kind != "script": continue` (`skill_tools.py:96-97`).
2. Для agent/pipeline — реальный провайдер из `_ws_session_tools`; для script оставить `_UnusedProvider`.
3. Пин `provider`/`model` скилла побеждает `fallback_model` (`provider_for_skill` в `apply.py`).
4. В описание тула — `kind` и оценка цены в LLM-вызовах.
5. `POST /sessions/{id}/tools` — явно отклонять `draft` и неизвестный `kind`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловия: `docs/plan/1-shift/03-CATALOG-124-code-skill-call-context.md`, `04-CATALOG-125-code-skill-budget.md`, `05-CATALOG-126-code-turn-deadline.md`. UI — `07-CATALOG-128-ui-toolspopover-cost.md` (ждёт `SkillOut` с ценой).

- `backend/catalog/skills/skill_tools.py:38-63` — `_UnusedProvider`.
- `backend/catalog/skills/skill_tools.py:94-97` — script-only.
- `backend/catalog/skills/apply.py` — `provider_for_skill` (~485).
- `backend/catalog/api/sessions.py:370-382` — attach без проверки status/kind.
- Оценка цены для описания тула и для `SkillOut` — одна функция (agent: `max_iterations × (max_retries + 1)`, pipeline: `len(steps) × max_iterations`, script: 0).

## Затрагиваемые файлы
- `backend/catalog/skills/skill_tools.py` — снять фильтр, провайдер по kind, description с ценой.
- `backend/catalog/api/sessions.py` — валидация attach; прокинуть реальный provider.
- `backend/catalog/api/schemas.py` — поле цены в `SkillOut` (для CATALOG-128).
- `backend/catalog/skills/apply.py` — только если пин провайдера не доезжает из collect.
- `backend/tests/test_session_skill_tools.py` / `test_sessions.py` — agent/pipeline вызов, draft 4xx, script без LLM.

## План действий
1. Убрать script-only; фильтры — только depth/chain (+ status committed).
2. Script → `_UnusedProvider`; agent/pipeline → переданный provider; модель/провайдер скилла через `provider_for_skill`.
3. Общая функция оценки LLM-вызовов — в description тула и в `SkillOut`.
4. `POST /sessions/{id}/tools`: draft и unknown kind → 4xx с понятным detail.
5. Тесты: agent и pipeline создают `skill_run` с `parent_run_id` и текстом в result; пин SHA-256; verify как раньше; script не вызывает LLM.

## Критерии приёмки (Definition of Done)
- [ ] Прикреплённый agent-скилл вызывается из сессии, есть `skill_run` + `parent_run_id` + текст в tool result.
- [ ] То же для pipeline.
- [ ] Пин SHA-256 работает для всех трёх kind.
- [ ] `verify_checks` вызванного скилла прогоняются.
- [ ] Script не доходит до LLM.
- [ ] Draft отклоняется на API.
- [ ] `ruff check .`, `pytest` из `backend/`.
