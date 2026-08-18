# CATALOG-138 — парность окружения script-прогона + номер строки в ошибке рантайма

- **Задача Plane:** [CATALOG-138](https://app.plane.so/belchch/projects/catalog-app/work-items/138) (id: `f96bad54-f84c-478b-b36d-4f85e37a9786`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 00 · blocking CATALOG-139
- **Цель:** Один путь подготовки входа и запуска script для apply и будущего dry-run; в `ScriptRuntimeError` — номер строки исходника и сама строка, без путей backend.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев к задаче не было)_

ADR-0023, п.1 и п.3. Подготовительный шаг для dry-run: один путь запуска скрипта и пригодная для отладки диагностика отказа.

Проблема. Логика подготовки входа script-скилла живёт внутри `_apply_core` (`backend/catalog/skills/apply.py`, ветка `skill.kind == "script"`): `extract_text` по документам, один документ verbatim / несколько через `\n\n---\n\n`, `documents=doc_texts`, затем `run_script_async`. Любой второй вызывающий (dry-run) обязан идти тем же путём, иначе среда отладки разойдётся с рантаймом. Отдельно: `run_script` заворачивает исключение в `ScriptRuntimeError(f"script raised: {exc}")` и теряет traceback — номера строки нет.

Объём.

- Вынести из `apply.py` общий хелпер подготовки входа и запуска script (текст документов → `doc_text` + `documents` → `run_script_async` с теми же лимитами). Ветка apply для `kind="script"` и script-шаг pipeline используют его; поведение не меняется.
- `ScriptRuntimeError` получает деталь отказа: номер строки в исходнике скрипта и сама строка. Источник — `traceback.extract_tb`, кадры фильтруются по filename `<script-skill>`; кадры backend наружу не отдаются.
- Таймаут и `MemoryError` остаются без номера строки, но с прежними сообщениями.
- Строка ошибки для существующих потребителей (`ScriptEvent(stage="error")`, `TraceEntry(kind="error")`) дополняется номером строки; формат остаётся строкой.

Приёмка.

- Копии логики подготовки входа в кодовой базе нет — apply и pipeline-шаг вызывают общий хелпер.
- Тест: скрипт с `IndexError` на известной строке → в `ScriptRuntimeError` есть её номер и текст.
- Тест: в сообщении об ошибке нет путей файлов backend.
- Существующие тесты `tests/test_script_runner.py`, `tests/test_apply.py` зелёные; поведение apply не изменилось.
- `ruff check .`, `pytest` зелёные.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Следующий шаг — `01-CATALOG-139-code-try-skill-script.md`: тул и HTTP dry-run обязаны звать этот хелпер, а не копировать `run_script_async`.

Сейчас склейка входа продублирована в двух местах `_apply_core`:

- `kind == "script"`: `doc_text = doc_texts[0] if len(doc_texts) == 1 else "\n\n---\n\n".join(doc_texts)`, затем `run_script_async(skill.code, doc_text, documents=doc_texts)` — `backend/catalog/skills/apply.py:423-434`.
- pipeline `step.type == "script"`: `_value_as_text` / `_value_as_documents` (`apply.py:104-115`) дают тот же join (`\n\n---\n\n`) и список, затем `run_script_async` — `apply.py:497-509`.

`extract_text` уже выполнен выше (`apply.py:338-339`); хелпер принимает готовые тексты, не пути файлов. `exec` компилирует код как `"<script-skill>"` (`script_runner.py:395`). Обёртка исключения — `script_runner.py:406-407`: `ScriptRuntimeError(f"script raised: {exc}")` без traceback. Таймаут и память — `script_runner.py:397-403`, сообщения не трогать.

Существующие тесты ловят `match="script raised"` (`test_script_runner.py:250-259`) — префикс сохранить.

## Затрагиваемые файлы
- `backend/catalog/skills/script_runner.py` — атрибуты `line_no` / `source_line` у `ScriptRuntimeError`; сборка из `traceback.extract_tb`; строка ошибки с номером; хелпер `prepare_script_input` + `run_skill_script` / `run_skill_script_async`.
- `backend/catalog/skills/apply.py` — ветки `kind=="script"` и pipeline script-шаг зовут хелпер; локальный join убрать.
- `backend/tests/test_script_runner.py` — IndexError с известной строкой; отсутствие путей backend в сообщении.
- `backend/tests/test_apply.py` — без смены поведения; существующие script/pipeline кейсы остаются зелёными.

## План действий
1. Расширить `ScriptRuntimeError`: опциональные `line_no: int | None`, `source_line: str | None`. Сообщение для `str(exc)` при ошибке скрипта — прежний префикс `script raised:` плюс номер и текст строки исходника. Таймаут / `MemoryError` / `unsupported required parameter` — без номера.
2. В `except Exception` внутри `run_script` разобрать `traceback.extract_tb`, оставить кадры с `filename == "<script-skill>"`, взять первый такой кадр. Текст строки — из исходника `code` по `lineno` (1-based), не из `frame.line` backend. Если кадра нет — номер не ставить, сообщение как сейчас (`script raised: {exc}`).
3. Вынести `prepare_script_input(doc_texts: list[str]) -> tuple[str, list[str]]` (один текст verbatim, несколько через `\n\n---\n\n`, `documents=list(doc_texts)`) и `run_skill_script` / `run_skill_script_async(code, doc_texts, **limits)` — join + `run_script` / `run_script_async` с теми же дефолтами таймаута и памяти.
4. В `_apply_core`: `kind=="script"` и script-шаг pipeline передают в хелпер уже подготовленный список текстов (`doc_texts` / `_value_as_documents(step_input)`). Повторный join в apply не оставлять. `_value_as_text` для llm-шагов не трогать.
5. Тесты: IndexError на фиксированной строке → `exc.line_no` и `source_line` совпадают, `str(exc)` содержит номер; в сообщении нет `backend/` и путей модулей; таймаут по-прежнему `time limit` без номера.

## Критерии приёмки (Definition of Done)
- [ ] Apply `kind=script` и pipeline script-шаг вызывают общий хелпер; второго join `\n\n---\n\n` + `run_script_async` в `apply.py` нет.
- [ ] Скрипт с `IndexError` на известной строке → в `ScriptRuntimeError` есть номер и текст этой строки.
- [ ] В сообщении об ошибке нет путей файлов backend.
- [ ] Таймаут и `MemoryError` без номера строки, тексты прежние.
- [ ] `ScriptEvent(stage="error")` и `TraceEntry(kind="error")` по-прежнему получают `str(exc)`.
- [ ] Зелёные: `tests/test_script_runner.py`, `tests/test_apply.py`, `ruff check .`, `pytest` из `backend/`.
