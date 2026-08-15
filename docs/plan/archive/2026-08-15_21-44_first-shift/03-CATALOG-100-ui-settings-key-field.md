# CATALOG-100 — UI: в настройках не видно поле ввода ключа для провайдера без ключа

- **Задача Plane:** [CATALOG-100](https://app.plane.so/belchch/projects/catalog-app/work-items/100) (id: `1c6bf788-703c-49c5-8d00-0f8277ab7058`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 03 · независимый
- **Цель:** В карточке провайдера без ключа поле API-ключа видно сразу (рамка + плейсхолдер «Вставьте API-ключ»), disabled отличим от активного; глобальный `.field` и поведение формы не менять.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Логика `ProviderRow` верная: при `configured === false` рендерится `<input type="password" className="field">`. Поле не видно, потому что и `<li>`, и `.field` имеют `bg-surface-muted` без рамки (`--surface-muted: #f5f6f6`), плейсхолдера нет — остаётся только «Сохранить».

Сделать локально в `SettingsPanel.tsx` (фон карточки `bg-surface` и/или рамка на инпуте), **не** трогать глобальный `.field`. Плейсхолдер как на первом запуске: «Вставьте API-ключ». Disabled (env / неизвестный провайдер) визуально отличим. Не ломать сабмит, «Отмена», Escape, фокус, `aria-describedby`.

## Предыстория
_нет — комментариев к задаче не было_

## Контекст
Карточка и инпут сейчас одного тона:

```299:341:frontend/src/components/SettingsPanel.tsx
    <li className="rounded border border-line bg-surface-muted px-3 py-2">
      ...
            <input
              ...
              className="field min-w-0 flex-1"
              ...
              disabled={busy || formLocked}
```

`showForm` (`:279`) = `envManaged || !configured || replacing || !known`. `formLocked` (`:280`) = env или неизвестный провайдер. Плейсхолдера нет.

Глобальный `.field` (`index.css:176-180`): `bg-surface-muted`, без `border`, рамка только в `focus-visible:ring`. На `SetupKeyScreen` / композере поле лежит на `surface` — там контраст есть. Поэтому править только `ProviderRow`.

Эталон плейсхолдера: `frontend/src/components/SetupKeyScreen.tsx:135` — `placeholder="Вставьте API-ключ"`.

## Затрагиваемые файлы
- `frontend/src/components/SettingsPanel.tsx` — локальные классы карточки и/или инпута в `ProviderRow`; плейсхолдер; визуал `disabled`.
- `frontend/src/index.css` — не менять `.field` (явный запрет ТЗ).

## План действий
1. В `ProviderRow` отделить поле от подложки: либо `<li>` → `bg-surface`, либо на инпут добавить `border border-line bg-surface` (перебить `.field` локально). Предпочтительно рамка + `bg-surface` на инпуте — карточка может остаться muted.
2. Добавить `placeholder="Вставьте API-ключ"` на password-инпут.
3. Для `disabled={busy || formLocked}` оставить/усилить отличие: `disabled:bg-surface-muted disabled:text-ink-faint` уже в `.field`; если после смены фона карточки disabled сольётся — добавить локальный класс (например `disabled:opacity-60` или явная рамка faint).
4. Не трогать `handleSubmit`, «Отмена» (`replacing`), Escape/фокус выше по панели, `aria-describedby` / hint / error.
5. Визуально сверить: провайдер без ключа; «Заменить ключ»; env-managed; неизвестный провайдер. Соседние экраны с `.field` не регрессируют.

## Критерии приёмки (Definition of Done)
- [ ] В строке провайдера без ключа поле видно сразу, без hover и фокуса.
- [ ] Плейсхолдер: «Вставьте API-ключ».
- [ ] Заблокированное поле читается как заблокированное.
- [ ] `SetupKeyScreen`, `SkillSettingsModal`, комбобоксы, композер выглядят как раньше.
- [ ] Сабмит, «Отмена», Escape, фокус, `aria-describedby` работают как сейчас.
- [ ] Глобальный `.field` в `index.css` не изменён.
- [ ] `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` в `frontend/` зелёные.
