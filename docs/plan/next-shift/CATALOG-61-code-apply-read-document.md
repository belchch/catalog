# CATALOG-61 — Не вызывается document-read при выполнении скилла

- **Задача Plane:** [CATALOG-61](https://app.plane.so/belchch/projects/catalog-app/work-items/61) (id: `a5feb10d-fa2d-4dc0-9adb-3aec2eda10f9`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** При apply agent-скилла модель обязана иметь доступ к тексту входных документов (через `read_document` и/или явную подачу контента). Сейчас агент отвечает «вставьте текст резюме» без tool-call — контент недоступен, результат галлюцинация.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи)_

Контент документа в скилле недоступен модели; ответы не основаны на данных, модель галлюцинирует. Нет вызова `document-read` (`read_document`).

Воспроизведение из UI: `kind: agent`, `docs: 1`, model google/gemini-3.5-flash / openrouter. В трейсе только «Итерация 1» и «Проверка (итерация 1)» — без tool-call. Результат: модель пишет, что не может заглянуть в файл, и просит вставить резюме/вакансию вручную. System prompt скилла говорит про «прикреплённый документ», что усиливает ложное ожидание, будто текст уже в контексте.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

Agent apply (`backend/app/skills/apply.py`):

1. Tools: `base_tools.filter(skill.allowed_tools)` (`135`) — **fail-closed subset**. Пустой `allowed_tools` → пустой registry → у LLM **нет** `read_document`.
2. Start user message (`253–269`) передаёт только `doc_id`, title, stem/`[[...]]` hint — **не текст** документа. Script path наоборот инлайнит текст через `extract_text` (`193–198`).
3. Tool зарегистрирован как `read_document` (`backend/app/documents/tools.py:61–75`), не `document-read`.
4. ADR-0003: document tools — базовый слой, не бонус; на практике skill config может собрать agent без `read_document` в `allowed_tools` (build не требует его: `skills.py` `_validate_config` только проверяет известность имён).

Итог бага: либо tools пустые/без `read_document`, либо модель не вызывает tool, потому что промпт («прикреплённый документ») + отсутствие явного «вызови read_document» создают иллюзию, что контент уже дан. UI лишь отражает отсутствие `tool_call` в стриме — чинить UI не требуется.

## Затрагиваемые файлы

- `backend/app/skills/apply.py` — гарантия доступа к тексту входов для agent path (tools + start message / prompt).
- `backend/app/skills/config.py` / `backend/app/api/skills.py` — при необходимости: валидация/auto-add `read_document` для `kind=agent` при build/configure/artifact pack.
- `backend/app/documents/tools.py` — только если меняется контракт read (скорее нет).
- `backend/tests/test_apply.py` — кейсы: agent с `allowed_tools=[]` или без `read_document`; провайдер видит tool; контент реально доходит (tool_call или inline в messages).
- При затронутой сборке — точечно `test_api.py` / `test_session_artifacts.py`.
- Frontend — вне объёма (кроме ручной проверки трейса).

## План действий

1. **Подтвердить root cause** на фикстуре: apply agent с `allowed_tools=[]` и с `["read_document"]` — сравнить `provider.seen_tools` и поведение fake-модели без tool_call.
2. **Гарантия tools:** для `kind=agent` при apply всегда включать `read_document` в рабочий registry (union с `skill.allowed_tools`), даже если конфиг его забыл. Опционально `list_documents` — по ADR желательно, но для бага критичен именно read входов.
3. **Гарантия контента (выбрать один основной путь, второй — усиление):**
   - **A (предпочтительно по надёжности):** в start user message инлайнить текст каждого `input_doc_id` (как script path), с пометкой id/title; `read_document` оставить для доп. чтения.
   - **B (строгий tool-layer):** не инлайнить, но жёстко в start message: «текст НЕ в контексте; сначала вызови `read_document(doc_id=...)` для каждого входа»; при желании — server-side prefetch tool_result до первого LLM-хода.
   - Рекомендация плана: **A + обязательный `read_document` в tools** — закрывает галлюцинации даже при «ленивой» модели; B один недостаточно (модель уже доказала, что может не вызвать tool).
4. Убрать/смягчить в runtime-обёртке формулировки, будто документ «уже прикреплён как файл в чат» без текста; id в сообщении оставить.
5. На build/validate agent: если `allowed_tools` пуст или без `read_document` — auto-add или явная ошибка валидации (предпочтительно auto-add для back-compat существующих скиллов).
6. Тесты: (1) apply с `allowed_tools=[]` → в complete всё равно есть `read_document`; (2) при inline — messages содержат фрагмент текста документа; (3) регресс `test_apply_filters_tools` — list_documents по-прежнему не утекает, если не в union-политике; (4) сценарий «модель без tool_call» всё равно получает данные, если выбран путь A.

## Критерии приёмки (Definition of Done)

- [ ] Apply agent-скилла с одним входным документом: модель получает текст документа (inline и/или успешный `read_document` в трейсе), не просит «вставьте резюме».
- [ ] Даже при `allowed_tools` без `read_document` (legacy/кривой конфиг) apply не оставляет агента без доступа к тексту входов.
- [ ] В трейсе UI при необходимости tool-path виден вызов `read_document` (если контент только через tool); при inline-path — допустимо отсутствие tool_call, но результат опирается на данные документа.
- [ ] Регресс: filter по-прежнему не отдаёт неизвестные tools; script path не ломается.
- [ ] Тесты в `test_apply.py` (и смежные) зелёные; из `backend/`: `ruff check .`, `pytest`.
- [ ] Ручная проверка кейса HR/cover-letter из описания задачи.
