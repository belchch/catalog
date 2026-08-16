# CATALOG-120 — Пользовательские AI-проверки (backend)

- **Задача Plane:** [CATALOG-120](https://app.plane.so/belchch/projects/catalog-app/work-items/120) (id: `4bda473d-5c4c-40a1-a724-d467540342f6`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 06 · blocked_by CATALOG-114
- **Цель:** LLM-судья — второй тип проверки (не в детерминированном реестре): хранение в workspace-БД, резолв в `run_verify` после зелёных детерминированных, fail-closed, без удаления (только скрытие).

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было; это code-часть code+ui тикета)_

Тип: code + ui — этот файл только backend. Зависит от CATALOG-114.

- ADR-0020: LLM-судья как отдельный тип.
- Таблица в workspace-БД.
- `run_verify`: сначала детерминированные, судья только если они зелёные. Verify до 3 раз — каждый судья умножается на это.
- Судья получает результат и критерий, не системный промпт исполнителя.
- Удаление не делаем — скрытие из выбора; `run_verify` fail-closed, если скилл ссылается на скрытую проверку.

Парный UI: `docs/plan/day-shift/07-CATALOG-120-ui-verify-checks-picker.md` (после этого плана).

Референс: `backup-pre-revert-0234` (`repo_custom_check.py`, ADR-0020 удалены revert'ом).

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловие: `docs/plan/day-shift/00-CATALOG-114-code-verify-checks-enum.md` (общая валидация params и enum встроенных check id).

- `docs/adr` — ADR-0007 отклоняет «верификация только LLM»; новый тип не смешивать с `registered_checks()`.
- `backend/catalog/skills/verify.py:45` — `run_verify` резолвит только встроенный реестр.
- `backend/catalog/storage/schema.py` — таблицы workspace-БД; кастомных проверок нет.
- Валидация 114 не должна принимать произвольные id как встроенные — кастомные резолвятся отдельно.

## Затрагиваемые файлы
- `docs/adr/0020-llm-judge-custom-checks.md` — новый.
- `backend/catalog/storage/schema.py` — таблица custom checks (+ hidden flag).
- `backend/catalog/storage/repo_custom_check.py` — новый.
- `backend/catalog/skills/verify.py` — резолв + порядок + вызов LLM.
- `backend/catalog/api/` — REST list/create/hide + пробный прогон на примере.
- `backend/tests/test_verify.py` — порядок, fail-closed, скрытая ссылка.

## План действий
1. ADR-0020: второй тип, не расширение ADR-0007.
2. Схема + репозиторий (create, list visible, hide; delete нет).
3. `run_verify`: детерминированные из 114; если все ok — судьи; скрытый/неизвестный custom id → fail.
4. Судья: вход = текст результата + критерий пользователя; без system prompt скилла.
5. REST для UI-плана: список стандартных+моих, создать, скрыть, preview на примере.
6. Тесты порядка и fail-closed.

## Критерии приёмки (Definition of Done)
- [ ] ADR-0020 есть; встроенный реестр не содержит LLM-проверок.
- [ ] Судья не бежит, пока детерминированные красные.
- [ ] Скрытая, но процитированная проверка валит `run_verify`.
- [ ] Нет API удаления.
- [ ] `ruff check .`, `pytest` из `backend/`.
