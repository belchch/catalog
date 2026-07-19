# CATALOG-45 — В модалке скилла модель/провайдер — из глобального выбора

- **Задача Plane:** [CATALOG-45](https://app.plane.so/belchch/projects/catalog-app/work-items/45) (id: `7d96e015-71e3-4b97-8fba-226b944e8fe8`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Цель:** При открытии модалки настройки скилла поля «Провайдер» и «Модель» предзаполнены текущим глобальным выбором пользователя (из шапки `ModelSelector`), если у самого скилла эти значения не заданы. Сейчас при пустом `preview.model`/`preview.provider` поля остаются пустыми.

## Постановка задачи (актуальное ТЗ)

_(источник: название задачи; описание и комментарии пустые)_

> В модалке создания скилла нужно, чтобы модель и провайдер проставлялись из текущего глобального выбора пользователя.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

### Что сейчас

`SkillSettingsModal` (`frontend/src/components/SkillSettingsModal.tsx`):

- Инициализация state — из `preview.model` и `preview.provider` (стр. 37-38).
- Если у скилла эти поля уже заданы (старый скилл) — всё ок.
- Если скилл новый или поля пустые — поля остаются пустыми, пользователь вынужден выбирать вручную, даже если в шапке уже выбран нужный провайдер/модель.

### Что глобально доступно

- `useSettings` (`frontend/src/hooks/useSettings.ts`) — единый источник правды о текущем выборе: `provider`, `model`, `providers`, `models`, `loading`, `changeProvider`, `changeModel`. Инстанс живёт в `App.tsx` как `settingsHook` (стр. 46).
- В `App.tsx` рендерится и `ModelSelector` (стр. 223-231, читает `settingsHook`), и `SkillSettingsModal` (стр. 346-352). **Сейчас в модалку `settingsHook` не пробрасывается** — модалка сама делает `listModels()`/`listProviders()` (стр. 47) и хранит свои `models`/`providers`.

### Дополнительный момент

`SkillSettingsModal` использует `listModels()` без указания провайдера (стр. 47) — возвращает, видимо, все модели или модели активного провайдера. СМЕНИВ провайдер в модалке, список моделей в комбобоксе не обновится (там нет логики `getProviderModels`). Это смежная проблема, но не относится напрямую к текущему ТЗ — фиксим только предзаполнение.

### Решение

Прокинуть из `App.tsx` в `SkillSettingsModal` текущие `defaultProvider` и `defaultModel` из `settingsHook`. В модалке:

```
const [provider, setProvider] = useState(preview.provider || defaultProvider)
const [model, setModel] = useState(preview.model || defaultModel)
```

Если `preview` содержит явное значение — оно приоритетнее (скилл уже сконфигурирован). Если пусто — берём глобальный выбор.

## Затрагиваемые файлы

- `frontend/src/components/SkillSettingsModal.tsx` — добавить props `defaultProvider: string` и `defaultModel: string`; использовать их в `useState` инициализации.
- `frontend/src/App.tsx` — при рендере `SkillSettingsModal` прокинуть `defaultProvider={settingsHook.provider}` и `defaultModel={settingsHook.model}`.

## План действий

1. **Расширить props модалки** (`SkillSettingsModal.tsx:12-17`):
   - Добавить `defaultProvider: string` и `defaultModel: string` в `SkillSettingsModalProps`.
2. **Использовать defaults в state** (стр. 37-38):
   - `useState(preview.provider || defaultProvider)`.
   - `useState(preview.model || defaultModel)`.
   - Глобальный выбор читается один раз при монтировании (как и `preview`) — это нормально: если пользователь меняет шапку, пока модалка открыта, можно не тащить обновление в реальном времени (упрощение; если потребуется — отдельная задача).
3. **Обновить вызов в `App.tsx`** (стр. 347-352):
   - `<SkillSettingsModal ... defaultProvider={settingsHook.provider} defaultModel={settingsHook.model} />`.
4. **Edge case**: если `defaultProvider`/`defaultModel` тоже пустые (например, бэкенд ещё не ответил при первичной загрузке) — поля остаются пустыми, как раньше. После появления `settingsHook.provider` модалка при повторном открытии возьмёт его. Это допустимое поведение; альтернатива — реактивно обновлять поля через `useEffect`, но это усложняет UX (может затереть выбор пользователя).
5. **Ручная проверка**:
   - В шапке выбрать `openrouter` + модель `X`.
   - Создать новый скилл через planner → открыть модалку → поля «Провайдер» и «Модель» уже содержат `openrouter` и `X`.
   - Изменить в шапке на другой провайдер/модель → снова открыть модалку → поля обновились.
   - Открыть старый скилл с явно заданными `preview.model`/`preview.provider` → поля показывают значения скилла, а не шапки.

## Критерии приёмки (Definition of Done)

- [ ] При открытии модалки настройки скилла с пустыми `preview.model`/`preview.provider` поля предзаполнены значениями из `useSettings` (глобальная шапка).
- [ ] При непустых `preview.*` приоритет у значений скилла, а не шапки.
- [ ] Сохранение конфигурации отправляет выбранные значения через `configureSkill` без изменений контракта.
- [ ] `App.tsx` прокидывает `defaultProvider`/`defaultModel` из `settingsHook` в `SkillSettingsModal`.
- [ ] `frontend/`: `pnpm run build` зелёный.
- [ ] `frontend/`: `pnpm run lint` зелёный.
- [ ] `frontend/`: `pnpm run typecheck` зелёный.
- [ ] Ручная проверка: новый скилл открывается с предзаполненными полями; старый скилл — со своими значениями.
