# CATALOG-49 — Не создаются связи у результатов с исходными доками

- **Задача Plane:** [CATALOG-49](https://app.plane.so/belchch/projects/catalog-app/work-items/49) (id: `faa92d32-91dc-47a2-a8d8-b8a1c1b2d176`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** При persist apply и `POST /runs/{id}/save` в текст result **детерминированно** попадают Obsidian-линки `[[stem]]` на **всех** родителей — входные документы из параметров запуска skill. Не полагаться на LLM. Stem = `Path(doc.path).stem`, не title из UI.

## Постановка задачи (актуальное ТЗ)

_(источник: последний комментарий от 2026-07-19T15:16:57Z)_

Всегда производный файл (result после persist / save) содержит Obsidian-линки на своих родителей.

Родители = все документы, указанные в параметрах запуска skill (входные doc ids / слоты), не «что LLM вспомнила».

- На каждого родителя — `[[stem]]` (имя файла без расширения), не title из UI.
- Гарантия детерминированная при записи результата: дописать линки на всех родителей, если их ещё нет в тексте.
- Один родитель → один линк; несколько → линки на всех.

Rewrite `[[title]]→[[stem]]` — опциональный доп.слой, не замена этому правилу.

**DoD:** новый result → в файле есть `[[stem]]` на каждый документ из параметров запуска.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

**Описание задачи:**

> Связь это линк обсидиан - [[имя файла документа]]. Важно. Документы сохраняются как результаты: 56dfe0e9476248bf8d962e95ea2f0f81, исходные документы: cover-letter-spiiran-ntbvt-java-ea411722. Нужно в линк вписывать название файла, а не отображаемое называние.

**Комментарий 2026-07-19T15:15:55Z:**

> Прошлый фикс (только rewrite title→stem + мягкий хинт) не создаёт связи. Нужна детерминированная вставка `[[stem]]` на входные документы при persist/save. Предпочтительно блок «Источник: [[stem]]» / список, если линка ещё нет. Старые results не обязаны мигрировать.

_Дубликат плана:_ `docs/plan/night-shift/CATALOG-49-code-obsidian-links-by-stem.md` (фокус на rewrite; актуальный SoT требует ensure parent links).

## Контекст

Связь в продукте = wiki-link в markdown vault (Obsidian), не таблица в БД. Provenance в `skill_run.input_doc_ids` / `output_doc_id` есть, но graph Obsidian строится только из `[[...]]` в файлах.

Сейчас есть:

- `build_title_to_stem_map` / `rewrite_wiki_links` — `backend/app/documents/obsidian.py:12-57`
- При persist: `apply.py:329-333` — только rewrite, без ensure
- При save: `runs.py:146-149` — то же
- Промпт agent с хинтом stem — `apply.py` (~230–248) — не гарантия

Пробел: если LLM/script не написала `[[...]]` на входы — в result связей нет. Нужен слой **ensure** после rewrite (или до записи на диск).

Родители берутся из списка входных документов прогона (`docs` в apply / `input_doc_ids` run при save), не из текста модели.

## Затрагиваемые файлы

- `backend/app/documents/obsidian.py` — хелпер `ensure_parent_wikilinks(text, parent_docs) -> str` (или аналог): для каждого родителя, если `[[{stem}]]` ещё нет в тексте — дописать (блок «Источники» / «Источник»)
- `backend/app/skills/apply.py` — при persist вызвать ensure на `docs` (входные DocumentRow) перед `write_text`
- `backend/app/api/runs.py` — при save загрузить входные docs run и вызвать тот же ensure
- `backend/tests/test_obsidian_links.py` — unit на ensure (один/несколько родителей, идемпотентность, уже есть линк)
- `backend/tests/test_apply.py` / `test_api.py` — e2e: persist/save → файл содержит `[[stem]]` каждого входа

## План действий

1. **Хелпер ensure.** В `obsidian.py`: на вход текст + список stem (или DocumentRow с `path`). Для каждого stem: если в тексте нет подстроки `[[{stem}]]` (с учётом optional heading/alias — достаточно проверки наличия `[[{stem}`), добавить в конец (или фиксированный блок) строки вида `Источник: [[stem]]` / список. Не дублировать уже присутствующие.
2. **Подключить в apply persist.** После `rewrite_wiki_links`, до записи файла: `ensure_parent_wikilinks(last_text, [Path(d.path).stem for d in docs])`.
3. **Подключить в save.** Из run взять `input_doc_ids`, загрузить документы, те же stem; apply ensure к тексту перед записью.
4. **Тесты.** Unit: пустой текст → появляются линки; текст уже с `[[stem]]` → без дубля; N родителей → N линков. Integration: apply persist и POST save.
5. **Миграция старых results** — out of scope; приёмка на новом результате.
6. **Rewrite оставить** как доп.слой — не удалять.

## Критерии приёмки (Definition of Done)

- [ ] Новый result после apply persist содержит `[[stem]]` на каждый входной документ параметров запуска.
- [ ] Новый result после `POST /runs/{id}/save` — то же.
- [ ] Stem = имя файла без расширения (`Path(path).stem`), не UI title.
- [ ] Повторная запись / уже существующий линк не плодит дубликаты.
- [ ] Rewrite title→stem по-прежнему работает (регрессия тестов `test_obsidian_links`).
- [ ] `backend/`: `ruff check .`, `pytest` зелёные.
- [ ] Ручная проверка: новый result в Obsidian — клик по `[[stem]]` открывает исходный файл.
- [ ] Старые UUID/title-results не мигрируются.
