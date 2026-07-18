# CATALOG-40 — Сломалась функция сохранить в документ

- **Задача Plane:** [CATALOG-40](https://app.plane.so/belchch/projects/catalog-app/work-items/40) (id: `2ceff00d-3bdd-4fc0-b7ba-ca817251dd5a`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** Вернуть работоспособность «сохранить в документ»: (1) apply скила из левого меню (`SkillsPanel`) запускается и в режиме `persist` создаёт документ; (2) в `RunView` (preview-режим) видна и работает кнопка «Сохранить как новый документ».

## Постановка задачи (актуальное ТЗ)

_(источник: описание задачи — комментариев не было)_

По нажатию из левого меню из скила — ничего не происходит.
Так же пропала кнопка из формы вывода в текст на экране.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было, описание и есть ТЗ._

## Контекст

Два симптома, обе причины — в существующем коде, связаны с выбором документов и условием рендера кнопки.

**Симптом 1: apply из левого меню ничего не делает.**
Кнопки «В док» / «На экран» в `SkillsPanel.tsx:419-435`:

```tsx
<button disabled={!valid || documents.length === 0} onClick={() => valid && onApply(s.id, docIds, 'persist')}>...</button>
<button disabled={!valid || documents.length === 0} onClick={() => valid && onApply(s.id, docIds, 'preview')}>...</button>
```

`valid` (`SkillsPanel.tsx:44-52`, `isSelectionValid`) требует заполненных слотов. Заполнение слотов — через `DocumentCombobox` (`SkillsPanel.tsx:366-416`). А `DocumentCombobox` сейчас сломан (см. [CATALOG-28](./CATALOG-28-ui-doc-combobox-fixes.md), [CATALOG-39](./CATALOG-39-ui-skill-param-doc-select.md)): из-за `onBlur` на root (`DocumentCombobox.tsx:99-103`) клик по option отменяется до `onChange` → `slots` не заполняются → `valid=false` → кнопки `disabled` → «ничего не происходит».

**Симптом 2: пропала кнопка в форме вывода на экране.**
Кнопка «Сохранить как новый документ» в `RunView.tsx:118-126` рендерится по условию:

```tsx
const canSaveResult = run.finished && statusOk && !outputDocId && !!run.resultText
```

`outputDocId` (`RunView.tsx:30`) = `run.outputDocId ?? savedDoc?.id ?? null`. Кнопка пропадает, если `run.outputDocId` заполнен — а это происходит только для `persist`-режима. В `preview`-режиме `outputDocId` быть не должно, кнопка должна быть. Но если apply вообще не запускается (симптом 1 — сломан выбор документа в слоте), то `RunView` не открывается, и пользователь делает вывод «кнопка пропала».

Дополнительно стоит проверить: если в `useRunStream`/`run` payload `outputDocId` ошибочно проставляется для preview-режима — кнопка реально пропадёт. Это второй кандидат на правку (помимо фикса `DocumentCombobox`).

**Связь с CATALOG-28 / CATALOG-39:** первопричина симптома 1 — та же компонента `DocumentCombobox`. Этот план покрывает end-to-end сценарий «сохранить в документ» и отдельный regression-чек условия `canSaveResult`.

## Затрагиваемые файлы

- `frontend/src/components/DocumentCombobox.tsx` — та же правка, что в CATALOG-28/39 (убрать/ослабить `onBlur` на root div, строки 99-103). Если CATALOG-28 уже смержён — возможно, изменений здесь не потребуется, только regression.
- `frontend/src/components/RunView.tsx` — regression-чек условия `canSaveResult` (`RunView.tsx:34, 118-126`) и поля `outputDocId` (`RunView.tsx:30`); убедиться, что в preview-режиме кнопка рендерится.
- `frontend/src/hooks/useRunStream.ts` — проверить, что для preview-режима run не получает `outputDocId` (если получает — баг здесь, починить).

## План действий

1. **Зафиксировать первопричину симптома 1** — зафиксировать `DocumentCombobox` (та же правка, что в CATALOG-28). Если CATALOG-28 уже вмержен — шаг пропускается, только regression.
2. **Энд-ту-энд проверка apply `persist`:** в `SkillsPanel` выбрать документ(ы) в слоте(ах) → кнопка «В док» активна → клик → `handleApply` (`App.tsx:187`) → `skillsHook.apply(...)` → `setActiveRunId(runId)` → открывается `RunView` → для persist-прогона показывается `outputDoc` и НЕ показывается кнопка «Сохранить как новый документ» (она для preview).
3. **Энд-ту-энд проверка apply `preview`:** тот же флоу, но кнопка «На экран» → `RunView` открывается → `run.outputDocId` пуст → `canSaveResult=true` → **кнопка «Сохранить как новый документ» видна** → клик → `handleSaveResult` (`App.tsx:201`) → `saveRunResult(runId)` → создаётся документ.
4. **Проверить `useRunStream`** на предмет того, что preview-прогон не получает `outputDocId` в payload от бэка. Если получает (например, бэк всегда приписывает doc) — починить на стороне парсинга стрима или отразить как отдельный backend-план.
5. **Regression:** создание/редактирование скила (`handleEditSkill`, `handleBuildSkill`) не затронуто; сохранение результата работает для нескольких прогонов подряд.

## Критерии приёмки (Definition of Done)

- [ ] В `SkillsPanel`: после выбора документа в слоте кнопка «В док» становится активной и по клику запускает apply (`setActiveRunId`, открывается `RunView`).
- [ ] В `SkillsPanel`: кнопка «На экран» аналогично работает и запускает preview-apply.
- [ ] В `RunView` для persist-режима: показывается блок «Документ создан: …», кнопка «Сохранить как новый документ» НЕ показывается (нечего сохранять — уже сохранено).
- [ ] В `RunView` для preview-режима: кнопка «Сохранить как новый документ» видна (при `run.finished`, `status==='ok'`, `resultText` есть), по клику создаёт документ, после этого скрывается и показывается «Документ создан: …».
- [ ] Сценарий «выбрал документ → В док» стабильно доходит до создания документа в списке `GET /documents`.
- [ ] `pnpm run typecheck` зелёный.
- [ ] `pnpm run lint` зелёный.
- [ ] `pnpm run build` зелёный.
- [ ] Нет Critical/Medium замечаний от `catalog-reviewer` и `catalog-ui-reviewer` (после фазы дизайна `catalog-designer` → `CATALOG-40.design.md`).
