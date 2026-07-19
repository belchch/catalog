# CATALOG-56 — Дизайн UI

- **Источник:** docs/plan/next-shift/CATALOG-56-ui-apply-prompt-field.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Пользователь в боковой панели скиллов открывает **committed** AI-скилл (`kind === "agent"` / тег `ai`), выбирает документ(ы) и при необходимости вводит уточняющий runtime-промпт в поле «Промпт», затем жмёт «В док» или «На экран». Промпт необязателен: пустое поле не блокирует apply. Для PYTHON/script-скилла (`kind === "script"` / тег `python`) поле не показывается — сценарий apply без изменений.

## Дерево компонентов и файлы

- `frontend/src/components/SkillsPanel.tsx` — единственное место UI: textarea «Промпт» в блоке apply committed-скилла; локальный draft `Record<skillId, string>`; условие видимости AI vs script; передача prompt в `onApply`.
- `frontend/src/App.tsx` — расширить `handleApply` / колбэк `onApply`: принять optional `prompt` и прокинуть в `skillsHook.apply`.
- `frontend/src/hooks/useSkills.ts` — расширить `apply(...)`: optional `prompt`, прокинуть в `api.applySkill`.
- `frontend/src/api.ts` — расширить `applySkill(...)`: optional `prompt`; в JSON body класть ключ `prompt` только если после `trim` строка непустая.

Новых компонентов/зависимостей не вводить: поле — inline в карточке скилла, в стиле существующих label + input в `SkillsPanel` / компактных textarea из панели артефактов.

## Layout и состояния

**Где в карточке (только `status === 'committed'`):** внутри уже существующего блока выбора документов и кнопок apply — **после** селекторов документов / hint arity=2, **перед** рядом кнопок «В док» / «На экран». Полная ширина колонки apply (`w-full`).

**Видимость поля:**

| Условие | Поле «Промпт» |
|--------|----------------|
| `skill.kind === 'script'` **или** тег `python` (и нет признаков agent/ai) | не рендерить |
| `skill.kind === 'agent'` **или** тег `ai` | рендерить |
| конфликт (маловероятно): приоритет — `kind`: `script` → скрыть, `agent` → показать | |

Хелпер видимости (логика реализации): показывать, если `kind === 'agent'` или (`tags` содержит `ai` и `kind !== 'script'`); скрывать, если `kind === 'script'` или (`tags` содержит `python` и `kind !== 'agent'`). При `kind === 'agent'` поле всегда видно независимо от тегов.

**Структура поля:**

1. Label над полем: текст `Промпт`, стиль как у «Документ» / «Документы» (`mb-0.5 text-[11px] text-slate-400`).
2. `textarea`: 2–3 видимые строки (`rows={2}` или `rows={3}`), `resize-y` с разумным `max-h` (например `max-h-28`), полная ширина.
3. Placeholder: `Уточнение для этого запуска (необязательно)`.
4. Hint под полем не обязателен; не добавлять secondary copy, чтобы не раздувать карточку.

**Состояния:**

- **default** — пустая textarea; кнопки apply зависят только от валидности выбора документов (как сейчас).
- **filled** — пользователь ввёл текст; apply доступен при валидных docIds; значение живёт в локальном state до ручной очистки / ухода со страницы.
- **whitespace-only** — визуально может быть непусто, но при apply считается пустым (`trim`); ключ `prompt` в body не отправлять.
- **loading / error apply** — без отдельного UI у поля; ошибки apply по-прежнему через `notice` в `App` / `skills.error`.
- **empty list / draft skill** — без изменений: у draft нет блока apply → поля нет.

После успешного apply значение **не** сбрасывать автоматически (повторный запуск с тем же уточнением); пользователь может стереть вручную.

## Взаимодействия

- Ввод в textarea обновляет draft только для текущего `skill.id` (изоляция между карточками).
- Клик «В док» / «На экран»: `onApply(skillId, docIds, mode, prompt?)`, где `prompt` — `trim`ned string или `undefined`/не передан, если пусто.
- Пустой промпт не влияет на `disabled` кнопок.
- Для script-карточки сигнатура вызова может по-прежнему без prompt (или с `undefined`); UI prompt не рендерит.
- Tab-порядок: документы → промпт (если есть) → «В док» → «На экран».
- Enter в textarea = новая строка (не submit apply). Apply только кнопками.

## Стиль и токены

Согласовать с тёмной панелью скиллов (`border-slate-800`, `bg-slate-900/60`):

- Label: `text-[11px] text-slate-400` (как «Документ»).
- Textarea: `w-full rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-100 placeholder:text-slate-500 outline-none focus:ring-1 focus:ring-slate-600` (или эквивалент без нового focus-токена, если в панели ring не принят — тогда как у rename `input`).
- Вертикальный ритм блока apply: `gap-1.5` как у соседних контролов.
- Не вводить indigo/fuchsia акценты на поле; акцент остаётся на кнопке «В док» (`bg-indigo-600`).

## Доступность (a11y)

- Связать label и textarea (`htmlFor` / `id` вида `skill-prompt-{skillId}` или `aria-labelledby`).
- `aria-label="Промпт"` допустим как дополнение, если label visually present.
- Поле не `required`; не ставить `aria-invalid` без серверной валидации поля.
- Контраст: `text-slate-100` на `bg-slate-800`, placeholder `text-slate-500` — как у остальных инпутов панели.

## Контракты данных (если нужны)

Предусловие backend: `CATALOG-56-code-apply-runtime-prompt.md` — `ApplyRequest.prompt: str | None`.

Цепочка UI → API:

1. `SkillsPanel.onApply(skillId, docIds, mode, prompt?: string)`
2. `App.handleApply` → `skillsHook.apply(skillId, docIds, mode, sessionId, prompt?)`
3. `api.applySkill` body:

```ts
{
  doc_ids: string[]
  persist: boolean
  session_id?: string
  prompt?: string  // только если trim(prompt).length > 0
}
```

Типы `SkillOut.kind` / `SkillOut.tags` уже есть в `api.ts` (`agent`|`script`, теги `ai` / `python`).

## Критерии визуальной приёмки

- [ ] У committed AI/agent-скилла в блоке apply видно label «Промпт» и textarea с placeholder про необязательное уточнение.
- [ ] У committed PYTHON/script-скилла поля «Промпт» нет; layout документов и кнопок как до шага.
- [ ] Поле стоит после выбора документов и перед кнопками «В док» / «На экран».
- [ ] Пустая textarea не блокирует apply при валидных документах.
- [ ] Непустой ввод сохраняется в карточке после apply (не авто-clear); очистка вручную возможна.
- [ ] Стили поля согласованы с label/input панели скиллов (компактный `text-[11px]`, `bg-slate-800`).
- [ ] Label связан с textarea для a11y; Tab доходит до поля до кнопок apply.
