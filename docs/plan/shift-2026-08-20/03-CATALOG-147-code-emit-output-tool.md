# CATALOG-147 — code: именованные выходы для kind=agent и llm-шага — тул emit_output

- **Задача Plane:** [CATALOG-147](https://app.plane.so/belchch/projects/catalog-app/work-items/147) (id: `93fd7c1a-c39e-4ac7-8dc5-b8c06d81e5d8`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 03 · blocked_by CATALOG-143 · blocked_by CATALOG-144 · blocked_by CATALOG-145 · blocking CATALOG-146
- **Цель:** Дать agent и финальному llm-шагу тул `emit_output`; набор копить и дозаполнять через существующий verify-retry. Persist уже из 145.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. Порядок: после рантайма script/pipeline, до UI.

У `script` набор берётся из возврата sandbox. У `agent` источник — ответ модели, сегодня это один текст: `FinishEvent.text` → `last_text` (`apply.py:946`) → один документ.

Агент-луп — function-calling (ADR-0001), реестр фильтруется fail-closed (`registry.py:33-44`), verify-retry уже возвращает модели список проблем (`apply.py:980-997`, ADR-0007). Оба механизма переиспользовать.

Что сделать:

1. Тул `emit_output(key, text)` регистрируется автоматически, когда объявлено больше одного выхода. Не в `allowed_tools` и не выбирается пользователем. `enum` ключей — из декларации.
2. Вызовы копятся. Повтор с тем же ключом перезаписывает. В трейс — каждый вызов с длиной текста.
3. Объявленные выходы с описаниями — в стартовое сообщение: что класть в каждый выход и что завершать после заполнения всех.
4. Неполный набор — через существующий retry (как провал verify), в пределах `max_retries`; исчерпание — `failed` с причиной.
5. Primary = `outputs[0]`. Один выход или пустая декларация — тула нет, `FinishEvent.text` как сейчас.
6. llm-шаг pipeline: тул только на последнем шаге. На промежуточных его нет в реестре.
7. Бюджет: `emit_output` локальный, но тратит итерации. 8 выходов не должны молча упираться в `max_iterations` — внятный `capped`, не потеря артефактов.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

Предусловия: `CATALOG-143`, `CATALOG-144` (`SkillConfig.outputs`), `CATALOG-145` (persist / `result_artifacts` / сверка). UI — `CATALOG-146`.

- `backend/catalog/agent/registry.py:33-44` — `filter` fail-closed: неизвестное имя → `ValueError`. Значит `emit_output` нельзя класть в `allowed_tools`. Регистрировать **после** `filter` (или `register` на уже отфильтрованном реестре).
- `backend/catalog/skills/apply.py:332-335` — agent: `base_tools.filter(ensure_read_document_tool(skill.allowed_tools))`; script/pipeline — `filter(skill.allowed_tools)`.
- `backend/catalog/skills/apply.py:547-548` — llm-шаг фильтрует `step.allowed_tools`.
- `backend/catalog/skills/apply.py:925-997` — агент-луп: `FinishEvent.text` → `last_text` → `run_verify` → retry-сообщение в messages.
- `backend/catalog/skills/apply.py:946` — единственный источник финального текста agent.
- `backend/catalog/agent/` — цикл function-calling; тул должен быть в `ToolRegistry` лупа, иначе модель его не увидит.
- Persist/verify/схема — уже 145: этот шаг только наполняет тот же набор до хвоста.

Тесты-якоря: `backend/tests/test_apply.py` (agent retry/verify), новые кейсы на `emit_output`.

## Затрагиваемые файлы
- `backend/catalog/skills/apply.py` — регистрация тула после filter; накопление; промпт; retry неполного набора; primary из `outputs[0]`; тул только на финальном llm-шаге.
- `backend/catalog/agent/` (если нужен отдельный модуль тула) — спека `emit_output`.
- `backend/tests/test_apply.py` — сценарии из DoD.

## План действий
1. Спека тула: `emit_output(key, text)`, `key` — `enum` из декларации. Не добавлять в `allowed_tools` пользователя.
2. После `filter` зарегистрировать тул на копии реестра, если `len(outputs) > 1`. Для pipeline llm — только `index == last`.
3. Хендлер копит `dict[str, str]`; повтор ключа перезаписывает; в трейс — шаг с `key` и `len(text)`.
4. В стартовое user/system сообщение — список ключей с описаниями и правило «завершай после всех».
5. После стопа лупа: сверить набор с декларацией. Дыры → то же retry-сообщение, что verify (`apply.py:980-997`). Исчерпание → `failed` + причина в трейсе.
6. Primary = значение `outputs[0]`; `last_text` / verify / persist 145 работают от него. N≤1 — тул не регистрировать.
7. На `capped` (`max_iterations`) — не терять уже накопленное; статус `capped`/failed с понятной причиной, не молчаливый обрез.
8. Тесты: два выхода → два документа; забытый ключ → retry → дозаполнение; незнакомый key отбит схемой; N=1 без тула; промежуточный llm без тула; вызовы в трейсе.

## Критерии приёмки (Definition of Done)
- [ ] Agent-скилл с двумя объявленными выходами даёт два документа с теми же полями прогона, что и script-скилл.
- [ ] Модель, забывшая выход, получает список незаполненных ключей и дозаполняет их в пределах `max_retries`; после исчерпания — `failed` с причиной.
- [ ] Незнакомый `key` отбивается схемой тула, а не пост-проверкой.
- [ ] Скилл с одним выходом и старые agent-скиллы работают без изменений; `emit_output` им не показывается.
- [ ] На промежуточном llm-шаге pipeline тула нет.
- [ ] Вызовы видны в трейсе как отдельные шаги.
- [ ] Backend: `ruff check .`, `pytest` зелёные.
