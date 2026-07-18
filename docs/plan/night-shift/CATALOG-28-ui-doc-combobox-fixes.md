# CATALOG-28 — Нужно видеть документы которые находятся в контексте чата

- **Задача Plane:** [CATALOG-28](https://app.plane.so/belchch/projects/catalog-app/work-items/28) (id: `bc1816bc-2837-426d-85fc-9cb70fe241bc`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** Починить существующий комбобокс выбора документов в composer'е чата: (1) выбор документа из списка действительно добавляет его в `selectedDocIds` и показывает чип; (2) раскрывающийся список раскрывается **вверх** от кнопки, а не уходит за низ экрана.

## Постановка задачи (актуальное ТЗ)

_(источник: последний комментарий от 2026-07-18)_

Не работает. В чате над полем для ввода сообщения есть комбобокс с выбором документов.
Список документов в комбобоксе отображается правильно.
Но при выборе документа из списка ни чего не происходит.

Вторая проблема — визуальная. Раскрывающийся список улетает в низ за экран. Расположение списка нужно перенести и сделать над кнопкой, а не под кнопкой.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_(из описания задачи)_

Объёмная архитектурная постановка про детерминированную привязку документов к chat-сессии: таблица `session_document`, `GET /sessions/{id}/documents`, расширение WS user-фрейма `{type:'user', content, doc_ids}`, чипы выбранных документов в composer, отображение состава сессии. Разбивка на 5 шагов (3 back, 2 front) с явным указанием что `@mention`-парсинг — out of scope.

Из этой постановки **уже реализовано** (см. код):
- WS `send(text, docIds?)` расширен `doc_ids` — `frontend/src/ws.ts:87-91`.
- `Chat.tsx` хранит `selectedDocIds`, рисует чипы выбранных документов, передаёт `docIds` в `onSend` — `frontend/src/components/Chat.tsx:51, 70-79, 87-94, 182-213`.
- `usePlannerSession` проксирует `docIds` дальше — `frontend/src/hooks/usePlannerSession.ts:240`.
- Используется `DocumentCombobox multiple` с `values={selectedDocIds}` и `onChange={setSelectedDocIds}` — `frontend/src/components/Chat.tsx:203-212`.

Остались два UI-бага — они и есть актуальное задание.

## Контекст

Компонент-виновник: `frontend/src/components/DocumentCombobox.tsx`.

**Баг 1 — выбор не срабатывает.** Корневой `<div>` имеет `onBlur` (`DocumentCombobox.tsx:99-103`), который зовёт `close()` если `relatedTarget` не внутри rootRef. Multiple-вариант рендерит опции как `<label>` с вложенным `<input type="checkbox">` (`DocumentCombobox.tsx:165-178`). Клик по `<label>` (а не точно по инпуту) в некоторых браузерах даёт `relatedTarget === null` на blur, и `close()` срабатывает **до** `onChange` чекбокса — реактовский state не обновляется, чип не появляется. Single-режим ( `<div role="option">` с прямым `onClick`, `DocumentCombobox.tsx:181-199`) этим не страдает, поэтому в `SkillsPanel` бага не видно.

Дополнительно усугубляет: `useEffect` с `mousedown` outside-listener (`DocumentCombobox.tsx:37-47`) дублирует логику закрытия и тоже проверяет `rootRef.contains`, но при клике внутри он корректен — основной виновник именно `onBlur`.

**Баг 2 — позиционирование.** Листбокс жёстко раскрыт вниз: `DocumentCombobox.tsx:139` (`absolute z-10 mt-1 max-h-48 w-full`). Composer чата (`frontend/src/components/Chat.tsx:215-249`) находится у нижней грани viewport → список из 10+ документов уходит за экран. Нужно раскрывать вверх, когда комбобокс стоит внизу страницы.

Компонент переиспользуется: `SkillsPanel.tsx:366-413` (4 места, single + multiple). Нельзя глобально менять направление или ломать single-поведение — нужен опциональный проп.

## Затрагиваемые файлы

- `frontend/src/components/DocumentCombobox.tsx` — исправить баг закрытия по blur (чтобы клик по option в multiple-режиме всегда доходил до `onChange`); добавить проп `placement?: 'bottom' | 'top'` (default `'bottom'`, текущее поведение), при `'top'` позиционировать listbox через `bottom-full mb-1` вместо `mt-1`.
- `frontend/src/components/Chat.tsx` — передать `placement="top"` в `<DocumentCombobox>` в composer'е (`Chat.tsx:203-212`). Других изменений в Chat не требуется.

## План действий

1. **Доказать баг 1 в коде.** В `DocumentCombobox.tsx` удалить (или ослабить) обработчик `onBlur` на root div: он дублирует `mousedown` outside-listener и некорректно срабатывает на клике по `<label>` в multiple-режиме. Минимальное изменение — убрать `onBlur` целиком (внешний клик и Escape уже закрывают список). Альтернатива — оставить `onBlur`, но игнорировать его, если mousedown начался внутри rootRef (через ref-флаг `pointerDownInside`).
2. **Управление направлением раскрытия.** Добавить в тип props:
   ```ts
   placement?: 'bottom' | 'top'  // default 'bottom'
   ```
   В className listbox ветвить:
   - `bottom` → `absolute z-10 mt-1 max-h-48 w-full ...` (как сейчас)
   - `top` → `absolute z-10 mb-1 bottom-full max-h-48 w-full ...`
3. **Применить в composer'е.** В `Chat.tsx:203` добавить `placement="top"` к `<DocumentCombobox multiple ...>`.
4. **Регрессионная проверка `SkillsPanel`.** Там `DocumentCombobox` стоит в модалке и раскрывается корректно вниз — с дефолтом `'bottom'` поведение не меняется. Убедиться, что nothing breaks.
5. **Локальная ручная проверка обоих багов:** открыть composer чата → выбрать 2 документа → чипы появляются; раскрыть список с 8+ документами → список раскрывается вверх и виден полностью.

## Критерии приёмки (Definition of Done)

- [ ] В composer чата клик по пункту multiple-комбобокса добавляет документ в `selectedDocIds` и рисует чип над полем ввода — стабильно, не «иногда».
- [ ] Повторный клик по выбранному документу снимает выбор (чип исчезает).
- [ ] Поиск внутри списка работает и после фильтрации выбор кликом корректен.
- [ ] Раскрывающийся список в composer'е раскрывается **вверх** от триггера и полностью помещается в viewport (при 10+ документах).
- [ ] В `SkillsPanel` поведение `DocumentCombobox` не изменилось: раскрытие вниз, выбор работает (single и multiple).
- [ ] Закрытие по внешнему клику и Escape сохранено во всех режимах.
- [ ] `pnpm run typecheck` зелёный.
- [ ] `pnpm run lint` зелёный.
- [ ] `pnpm run build` зелёный.
- [ ] Нет Critical/Medium замечаний от `catalog-reviewer` и `catalog-ui-reviewer` (после фазы дизайна `catalog-designer` → `CATALOG-28.design.md`).
