# CATALOG-120 — UI: попап выбора и создания AI-проверок

- **Задача Plane:** [CATALOG-120](https://app.plane.so/belchch/projects/catalog-app/work-items/120) (id: `4bda473d-5c4c-40a1-a724-d467540342f6`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 07 · предусловие: 06 (code того же тикета) · blocked_by CATALOG-114
- **Цель:** Вместо текстового поля `verify_checks` в ArtifactsPanel — попап: «Стандартные», «Мои проверки», «Новая проверка» с прогоном на примере. Модель по-прежнему предлагает набор, пользователь правит руками.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было; это ui-часть code+ui тикета)_

Тип: ui, после code того же тикета. Зависит от CATALOG-114 (каталог стандартных) и от code-плана 120 (REST кастомных).

- Попап вместо input в `ArtifactsPanel.tsx` (~619).
- Секции «Стандартные» (девять встроенных человеческими словами) и «Мои проверки».
- Форма: название, промпт-утверждение, «прогнать на примере» с вердиктом.
- Удаление не делаем.

Токены: `docs/ui-style-guide.md`. Референс: `backup-pre-revert-0234` (`VerifyChecksPicker.tsx` удалён).

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
Предусловия: `docs/plan/day-shift/00-CATALOG-114-code-verify-checks-enum.md` и `docs/plan/day-shift/06-CATALOG-120-code-custom-ai-checks.md`.

- `frontend/src/components/ArtifactsPanel.tsx:618-630` — одно текстовое поле `non_empty, markdown_well_formed`.
- `VerifyChecksPicker.tsx` отсутствует.
- Человеческие имена стандартных — `docs/verification-checks.md`.

## Затрагиваемые файлы
- `frontend/src/components/VerifyChecksPicker.tsx` — новый попап + форма.
- `frontend/src/components/ArtifactsPanel.tsx` — заменить text input.
- `frontend/src/api.ts` — клиент REST из code-плана.
- Тест пикера при необходимости.

## План действий
1. Клиент API list/create/hide/preview из code-плана.
2. Пикер: две секции, мультивыбор, человеческие подписи девяти встроенных.
3. Форма новой проверки + preview вердикт.
4. Сохранение meta пишет структурированный `verify_checks`, не CSV-строку (если текущий draft — строка, перевести аккуратно).
5. Скрытие «моей» проверки убирает её из выбора, не ломает уже сохранённые скиллы (backend fail-closed — UI не предлагает hidden).

## Критерии приёмки (Definition of Done)
- [ ] Текстовое поле `verify_checks` в meta заменено попапом.
- [ ] Есть «Стандартные», «Мои», «Новая проверка» с прогоном на примере.
- [ ] Нет UI удаления.
- [ ] Только токены style guide.
- [ ] `pnpm run build`, `lint`, `typecheck`, `test`.
