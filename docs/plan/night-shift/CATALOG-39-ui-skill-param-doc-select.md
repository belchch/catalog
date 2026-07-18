# CATALOG-39 — Не работает выбор документов для любых типов параметров в скилах

- **Задача Plane:** [CATALOG-39](https://app.plane.so/belchch/projects/catalog-app/work-items/39) (id: `9d0d6f15-a405-41eb-89c2-4bf58729dc53`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** Починить выбор документов в `DocumentCombobox` при использовании в `SkillsPanel` (слоты параметров скила): клик по пункту списка должен записывать выбранное значение для всех видов параметров — single (`arity=1`, `arity=2`) и multiple (`arity=null`).

## Постановка задачи (актуальное ТЗ)

_(источник: название задачи — описание пустое, комментариев не было)_

Не работает выбор документов для любых типов параметров в скилах.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было, описание пустое, ТЗ = название._

## Контекст

Та же компонента-виновник, что в [CATALOG-28](./CATALOG-28-ui-doc-combobox-fixes.md) — `frontend/src/components/DocumentCombobox.tsx`. Здесь рассматривается её применение в `frontend/src/components/SkillsPanel.tsx` для слотов параметров скила (3 варианта):

- **single, `arity=1`** — `SkillsPanel.tsx:366-372`: `value/onChange`, control через `setSlots(s.id, 1, [id])`.
- **single, `arity=2`** — `SkillsPanel.tsx:379-399`: два независимых `DocumentCombobox` для слотов 0 и 1, каждый с `value/onChange`.
- **multiple, `arity=null`** — `SkillsPanel.tsx:409-416`: `multiple values/onChange`, control через `setSlots(s.id, null, ids)`.

Все три варианта — один и тот же баг. Корневые причины (детально разобрано в плане CATALOG-28):

1. **`onBlur` на root div** (`DocumentCombobox.tsx:99-103`). При mousedown на option браузер уводит фокус с триггер-кнопки: `relatedTarget === null` (option-div и option-label не focusable) → `close()` срабатывает **до** того, как `onClick`/`onChange` обработается. Для single-режима (`<div role="option">` с `onClick`, `DocumentCombobox.tsx:181-199`) клик по option отменяется/не доходит, для multiple-режима (`<label>` + checkbox, `DocumentCombobox.tsx:165-178`) `onChange` чекбокса не успевает записать значение.

2. **`useEffect` outside-listener** (`DocumentCombobox.tsx:37-47`) дублирует закрытие — для клика внутри корректен, но усугубляет гонку с blur.

Из-за этого: выбираешь документ в слоте скила → ничего не происходит, кнопка «В док»/«На экран» остаётся disabled (валидность не проходит).

**Связь с CATALOG-28:** баг один — тот же `DocumentCombobox`. Фикс в CATALOG-28 (убрать/ослабить `onBlur`) чинит и CATALOG-39. Этот план фиксирует ту же правку с прицелом на `SkillsPanel` как основное место проявления и Regression-чеки именно по слотам параметров.

## Затрагиваемые файлы

- `frontend/src/components/DocumentCombobox.tsx` — убрать/ослабить `onBlur` на root div (строки 99-103), чтобы клик по option в обоих режимах доходил до `onChange`. Та же правка, что в CATALOG-28; если CATALOG-28 уже смержён — изменения для CATALOG-39 могут отсутствовать (только regression-чеки).
- (без изменений в `SkillsPanel.tsx` — там логика верная, ломается только сам `DocumentCombobox`).

## План действий

1. **Проверить состояние `DocumentCombobox.tsx`.** Если план CATALOG-28 уже выполнен — `onBlur` уже убран/ослаблен; дальше только regression-проверка. Если нет — выполнить ту же правку: удалить `onBlur` на root div (`DocumentCombobox.tsx:99-103`), полагаясь на `mousedown` outside-listener и Escape.
2. **Проверить single-режим (`arity=1`).** В `SkillsPanel`: выбрать документ в одном слоте → `setSlots(s.id, 1, [id])` отрабатывает → в `value` записывается id → кнопка «В док»/«На экран» становится активной.
3. **Проверить two-slot single (`arity=2`).** Заполнить оба слота разными документами → валидность проходит (`isSelectionValid`, `SkillsPanel.tsx:44-52`), кнопки активны. Проверить, что повторный клик по уже выбранному документу в другом слоте тоже работает (обновляет значение).
4. **Проверить multiple (`arity=null`).** Выбрать 2+ документов → `setSlots(s.id, null, ids)` отрабатывает → чекбоксы отображают состояние, `docIds.length` корректно отображается в `(${docIds.length})` (`SkillsPanel.tsx:426, 434`).
5. **Регрессия по composer'у (CATALOG-28).** Убедиться, что правка `DocumentCombobox` не сломала выбор документов в чате.

## Критерии приёмки (Definition of Done)

- [ ] Для скила с `input_arity=1`: клик по документу в слоте записывает значение и активирует кнопки «В док»/«На экран».
- [ ] Для скила с `input_arity=2`: клик в каждом из двух слотов независимо записывает значение; оба слота заполняются → валидность проходит.
- [ ] Для скила с `input_arity=null` (multi): клики по чекбоксам добавляют/снимают документы, счётчик `(${docIds.length})` обновляется.
- [ ] Поиск внутри списка работает и после фильтрации выбор кликом корректен во всех режимах.
- [ ] Закрытие по внешнему клику и Escape сохранено во всех режимах и слотах.
- [ ] Выбор документов в composer чата (CATALOG-28) продолжает работать.
- [ ] `pnpm run typecheck` зелёный.
- [ ] `pnpm run lint` зелёный.
- [ ] `pnpm run build` зелёный.
- [ ] Нет Critical/Medium замечаний от `catalog-reviewer` и `catalog-ui-reviewer` (после фазы дизайна `catalog-designer` → `CATALOG-39.design.md`).
