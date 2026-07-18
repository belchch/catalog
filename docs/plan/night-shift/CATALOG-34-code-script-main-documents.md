# CATALOG-34 — Apply python-скила: `main(documents)`

- **Задача Plane:** [CATALOG-34](https://app.plane.so/belchch/projects/catalog-app/work-items/34) (id: `471d2274-3a16-4f41-b329-30c9b33be147`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Script skills с `def main(documents):` (и совместимые сигнатуры) выполняются без `missing 1 required positional argument: 'documents'`.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Ошибка: `main() missing 1 required positional argument: 'documents'` — вызов python сразу падает.

## Предыстория

_нет — комментариев к задаче не было_

## Контекст

- `_extract_result` вызывает `main()` **без аргументов** — `script_runner.py:268-274`.
- Globals дают `document` / `input_text` (строка), не `documents` — `_build_globals`.
- Apply передаёт один склеенный `doc_text` — `apply.py:170-184`.
- Планировщик/build часто генерирует `def main(documents):` — контракт рассинхронен с runtime.

## Затрагиваемые файлы

- `backend/app/skills/script_runner.py` — вызов `main` по signature; globals `documents`.
- `backend/app/skills/apply.py` — передавать список текстов/docs в runner при multi-doc.
- Промпт build script skills (если фиксируем контракт) — `skills.py` / config.
- `backend/tests/test_apply.py` / script tests — кейс `main(documents)`.

## План действий

1. Зафиксировать контракт: `main()` / `main(document)` / `main(documents)` / использование globals.
2. В `_extract_result`: inspect signature → передать `document` str и/или `documents: list[str]`.
3. В `_build_globals` / apply: положить `documents` (list) даже для одного входа.
4. Регрессионный тест на ошибку из ТЗ.
5. (Опционально) гарантировать `finish` после script fail в WS — смежный UX, не блокер ТЗ.

## Критерии приёмки (Definition of Done)

- [ ] Скил с `def main(documents):` успешно apply без missing argument.
- [ ] Обратная совместимость: `main()` без аргументов и scripts через `result`/`print` работают.
- [ ] Тест на воспроизведение бага зелёный.
- [ ] `ruff` / `pytest` зелёные.
