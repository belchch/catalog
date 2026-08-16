# CATALOG-114 — Реестр verify_checks: enum в схеме тулов и валидация params

- **Задача Plane:** [CATALOG-114](https://app.plane.so/belchch/projects/catalog-app/work-items/114) (id: `d54db27a-efe5-450c-b5be-b924c867aa20`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 00 · blocking CATALOG-120
- **Цель:** Планировщик видит реестр проверок в схеме тулов (`enum` + шпаргалка params) и не может сохранить `min_length`/`max_length` без обязательного параметра. Оба пути (`set_skill_meta` и legacy `build_skill`) используют одну функцию валидации.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: code. Шаг 1 из 7. Независим на старте. Блокирует CATALOG-120.

Модель обязана заполнять `verify_checks`, но списка не видит: в схеме `set_skill_meta` поле `check` — `{"type": "string"}`, `registered_checks()` только постфактум. Отсюда угадывание id и пустышки вроде `min_length` без `min`.

- `artifact_tools.py`: `check` → `enum` из `available_checks`; в `description` тула — шпаргалка params из `docs/verification-checks.md`.
- `_validate_meta_fields`: `min_length` без `min` и `max_length` без `max` — ошибка.
- То же в `_BUILD_SKILL_PARAMETERS` (`backend/catalog/api/skills.py`).
- Валидацию оформить одной общей функцией.

DoD: без ретраев на `unknown verify check`; проверка без обязательного параметра не сохраняется. Тест: `set_skill_meta` с `min_length` без `min` отклоняется.

Референс (не копировать вслепую): тег `backup-pre-revert-0234`.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Сейчас схема тула не ограничивает id проверки:

- `backend/catalog/skills/artifact_tools.py:330-339` — `check: {"type": "string"}`.
- `backend/catalog/skills/artifact_tools.py:53-73` — `_validate_meta_fields` ловит только `unknown verify check`, params не смотрит.
- `backend/catalog/api/skills.py:238-247` — то же в `_BUILD_SKILL_PARAMETERS`.
- `backend/catalog/skills/verify.py:81-87` — `_check_min_length` при отсутствии `min` молча проходит.
- Реестр и человеческие описания: `docs/verification-checks.md`, `registered_checks()` в `verify.py:40`.

## Затрагиваемые файлы
- `backend/catalog/skills/verify.py` — общая функция валидации params (required keys по id).
- `backend/catalog/skills/artifact_tools.py` — enum в схеме, шпаргалка в description, вызов общей валидации.
- `backend/catalog/api/skills.py` — то же для `_BUILD_SKILL_PARAMETERS` / build_skill.
- `backend/tests/test_session_artifacts.py` или `backend/tests/test_verify.py` — отказ `min_length` без `min`.
- `docs/verification-checks.md` — только если шпаргалка требует уточнения формулировок (не обязательно).

## План действий
1. Вынести проверку осмысленности params (`min_length`→`min`, `max_length`→`max`; остальные required из реестра — `pattern`, `heading`, `key` и т.д. по `docs/verification-checks.md`) в одну функцию рядом с `registered_checks`.
2. Вызвать её из `_validate_meta_fields` и из пути `build_skill`.
3. В схемах `set_skill_meta` и `_BUILD_SKILL_PARAMETERS` заменить `check` на `enum: available_checks` / `registered_checks()`.
4. В description тулов добавить краткую шпаргалку params.
5. Тест: `min_length` без `min` → ошибка; валидный `min_length` с `min` проходит; неизвестный check по-прежнему ошибка.

## Критерии приёмки (Definition of Done)
- [ ] `set_skill_meta` / `build_skill` схема: `check` — enum из реестра.
- [ ] Description тула содержит шпаргалку params.
- [ ] `min_length` без `min` и `max_length` без `max` отклоняются одной общей функцией.
- [ ] Тест на отказ без обязательного параметра зелёный.
- [ ] `ruff check .`, `pytest` из `backend/`.
