# CATALOG-24 — Провайдер z.ai (починка моделей)

- **Задача Plane:** [CATALOG-24](https://app.plane.so/belchch/projects/catalog-app/work-items/24) (id: `b00ba6c5-ab0b-4448-8e1c-907c532fe87d`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Цель:** Рабочий z.ai: актуальные id моделей (в т.ч. GLM 5.2), запросы без `Unknown Model` 400 для доступных GLM; каталог UI совпадает с тем, что принимает API.

## Постановка задачи (актуальное ТЗ)
_(источник: последний комментарий от 2026-07-18)_

Не работает. Нет модели glm 5.2 в z.ai. Ошибка: `zai error 400: Unknown Model, please check the model code` при выборе 4.6, 4.5 — похоже на более широкую проблему с z.ai провайдером.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

Исходное ТЗ: реализовать ZaiProvider по аналогии с OpenRouter (общий `OpenAICompatibleProvider`, фабрика, reasoning_content, env `ZAI_*`, ADR-0013). Базовая реализация в коде уже есть.

Архив: `docs/plan/archive/2026-18-08_night-shift/00-CATALOG-24-…`.

## Контекст

- `ZaiProvider` + хардкод `_ZAI_MODELS` (`glm-4.6`, `glm-4.5`, …) — `backend/app/llm/zai.py:31-77`.
- Фабрика: `factory.py` — zai при `ZAI_API_KEY`.
- Ошибка 400 Unknown Model → id в каталоге не совпадают с актуальным API z.ai (или нужен другой code/path).
- Нет `glm-5.2` (или актуального имени) в `_ZAI_MODELS`.

## Затрагиваемые файлы

- `backend/app/llm/zai.py` — обновить каталог id/имён; проверить base_url и формат model code.
- `backend/app/llm/openai_compatible.py` — если ошибка в формировании request body для z.ai.
- `backend/tests/test_zai.py` — моки + регрессия id.
- `.env.example` / `backend/.env.example` — документация ключей (если ещё не синхронизированы).

## План действий

1. Сверить актуальные model codes в документации/API z.ai (включая GLM 5.2 и рабочие 4.x).
2. Обновить `_ZAI_MODELS`; убрать/поправить мёртвые id, дающие 400.
3. Прогнать `complete`/`stream` на моках и ручной smoke с `ZAI_API_KEY`.
4. Выровнять `active_provider` с реально собранным инстансом (`main.py` / factory), если баг воспроизводится.

## Критерии приёмки (Definition of Done)

- [ ] В списке z.ai есть актуальная GLM 5.2 (корректный model code).
- [ ] Выбор рабочей модели из каталога не даёт `Unknown Model` 400.
- [ ] Тесты z.ai зелёные; `ruff` / `pytest` ок.
