# CATALOG-125 — Бюджет вложенных вызовов на ход сессии

- **Задача Plane:** [CATALOG-125](https://app.plane.so/belchch/projects/catalog-app/work-items/125) (id: `db657117-4113-4623-b088-0e2802fde6cd`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 04 · blocked_by CATALOG-124 · blocking CATALOG-126 · blocking CATALOG-129
- **Цель:** Один `SkillBudget` на ход сессии: резерв по худшему случаю, списание LLM-вызовов во вложенном runner, возврат остатка, отказ в tool result без падения хода.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. После глубины/цепочки (CATALOG-124), до снятия фильтра script-only.

1. `SkillBudget`: `llm_calls_left = 60`, `nested_runs_left = 20`. Создать в `sessions.py` перед `_run_planner_turn` (рядом с `llm_timeout_context`).
2. Резерв до `apply_skill_collect`: agent → `max_iterations × (max_retries + 1)`; pipeline → `шаги × max_iterations`; script → 0 вызовов, 1 запуск. Не влезает — отказ до запуска.
3. Возврат неизрасходованного, включая ветку с исключением.
4. Списание — в `runner.py:100` рядом с `TraceEntry("llm", i, {})`. Итерации планировщика бюджет не трогают.
5. Отказ: `{"ok": false, "error": "budget exhausted", "budget": {...}}`, не исключение.
6. Узел в трейсе при исчерпании.
7. Числа — настройки, не константы модуля.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `SkillCallContext` из `docs/plan/1-shift/03-CATALOG-124-code-skill-call-context.md`.

- `backend/catalog/api/sessions.py` — ход планировщика, `llm_timeout_context` ~856.
- `backend/catalog/skills/skill_tools.py:113-177` — замыкание `_run`; формат ошибок `ok: false`.
- `backend/catalog/agent/runner.py:96-100` — единственное место, где итерация LLM гарантированно учтена.
- `backend/catalog/skills/config.py:133` — `max_iterations` / `max_retries` для резерва.
- Workspace settings сейчас — provider/model (`SettingsOut`). Лимиты положить в `Settings` + persist workspace, без нового UI в этом шаге.

Планировщик в бюджет не входит: списывать только когда runner крутится внутри skill-tool apply.

## Затрагиваемые файлы
- `backend/catalog/skills/skill_tools.py` — `SkillBudget`, reserve/release, отказ `budget exhausted`.
- `backend/catalog/api/sessions.py` — создать бюджет на ход, передать в сборку тулов.
- `backend/catalog/agent/runner.py` — списание вложенного LLM-вызова (флаг/контекст «это вложенный скилл»).
- `backend/catalog/config.py` / storage workspace settings — дефолты 60 и 20.
- `backend/tests/test_session_skill_tools.py` — резерв, возврат, отказ, сброс на следующем ходе, планировщик не списывается.

## План действий
1. `SkillBudget` с reserve/charge/release; лимиты из настроек.
2. Создавать на каждый ход в `sessions.py`, не шарить между ходами.
3. В `_run` резервировать до apply; при нехватке — tool result + trace node, без LLM.
4. В `runner.py` списывать только вложенный путь (не top-level planner).
5. `try/finally` — возврат остатка.
6. Тесты из DoD.

## Критерии приёмки (Definition of Done)
- [ ] Остаток меньше худшего случая → agent-скилл не стартует, LLM не вызывается.
- [ ] 2 вызова из резерва 24 → возврат 22.
- [ ] Исчерпание не роняет ход — модель получает tool result.
- [ ] Следующий ход — свежий бюджет.
- [ ] Итерации планировщика бюджет не трогают.
- [ ] `ruff check .`, `pytest` из `backend/`.
