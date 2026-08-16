# CATALOG-130 — Чат/прогоны: UI зависает в «думает», finish теряется, результат появляется только после Stop

- **Задача Plane:** [CATALOG-130](https://app.plane.so/belchch/projects/catalog-app/work-items/130) (id: `51334258-5ed5-4f1c-ae80-e18bd4663a18`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 00 · независимый
- **Цель:** Планировщик не помечает уже завершённый ход как `cancelled`; во время хода и apply идут keepalive; cancel в idle отвечает кадром; прогон отдаёт промежуточный текст до verify.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Backend-часть (пункты 2–5 ТЗ; пункт 1 — парный UI-план):

- `_run_planner_turn`: если `agent_task` уже в `done`, слать честный `finish ok`, даже когда одновременно пришёл cancel.
- Keepalive ping внутри `_run_planner_turn` и `_stream_apply`, не только в idle (`_receive_text_with_keepalive`).
- Cancel вне хода: ответить кадром (`finish {status:"noop"}` или повторный `finish`), чтобы UI мог сбросить залипший `streaming`.
- Runs: отдать промежуточный текст после генерации, до verify — чтобы verify/ретраи не выглядели как зависание.

Приоритет ТЗ: пункты 1–2 закрывают основной сценарий; 3–5 — устойчивость. В этом плане — 2–5.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Гонка и тишина на сокете:

- `backend/catalog/api/sessions.py:687-703` — `FIRST_COMPLETED`: ветка `receive_task` проверяется раньше `agent_task`; cancel отменяет уже готовый ход.
- `backend/catalog/api/sessions.py:845-846` — cancel/keepalive в idle просто `continue`, ответа клиенту нет.
- `backend/catalog/api/sessions.py:221-236` — ping только пока сервер ждёт следующее сообщение в idle.
- `backend/catalog/api/sessions.py:659` / `891-900` — планировщик с `use_stream=False`; `token`+`finish` уходят одним куском после хода.
- `backend/catalog/skills/apply.py:778-825` — `CancelledError` пишет run как `cancelled` с `result_text=last_text`.
- `backend/catalog/api/runs.py:330-340` — WS `finish` берёт `result_text` из строки run; до этого кадра токенов нет.

Парный UI-план: `docs/plan/2-shift/01-CATALOG-130-ui-streaming-onclose.md`.

## Затрагиваемые файлы
- `backend/catalog/api/sessions.py` — порядок done-веток, ping во время хода, ответ на cancel в idle.
- `backend/catalog/api/runs.py` — ping во время `_stream_apply`; промежуточный кадр с текстом до verify.
- `backend/catalog/skills/apply.py` — yield промежуточного текста после генерации, до verify (если нет отдельного события — добавить кадр в WS-слой).
- `backend/tests/test_api.py` / тесты сессий/runs — гонка cancel vs готовый ход; idle-cancel отвечает кадром; keepalive не ломает ход.

## План действий
1. В `_run_planner_turn` сначала смотреть `agent_task in done`. Если агент завершился — взять `final_text`, не ставить `cancelled`. Cancel применять только когда агент ещё работает.
2. Во время ожидания `agent_task` слать ping с тем же интервалом, что `_receive_text_with_keepalive`.
3. В idle-цикле сессии на cancel отвечать кадром (`finish` со `status: "noop"` или эквивалент), не молча `continue`.
4. В `_stream_apply` слать ping, пока apply крутится (verify/ретраи).
5. После генерации, до verify, отдать клиенту промежуточный текст (`token` или отдельный кадр с `result_text`), чтобы экран не был пустым.
6. Тесты: одновременный cancel+done → `finish ok`; idle cancel → кадр клиенту; apply не падает от ping.

## Критерии приёмки (Definition of Done)
- [ ] Готовый ход планировщика не помечается `cancelled`, если агент уже в `done`.
- [ ] Ping уходит во время хода планировщика и во время apply.
- [ ] Cancel в idle даёт кадр, по которому UI может сбросить `streaming`.
- [ ] До `finish` прогона клиент видит промежуточный текст после генерации.
- [ ] `ruff check .`, `pytest` из `backend/`.
