# CATALOG-116 — UI: разгрузка композера чата

- **Задача Plane:** [CATALOG-116](https://app.plane.so/belchch/projects/catalog-app/work-items/116) (id: `2e6ef64b-f50e-4b5f-b380-eede43db3fb3`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Очередь:** 02 · blocking CATALOG-118
- **Цель:** Схлопнуть шесть вертикальных блоков композера в полосу вложений + компактную панель (`+` и слот инструментов). Высота композера не растёт с числом документов. Поведение отправки подсказок — как CATALOG-90 (`sendCurrent`).

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было)_

Тип: ui. Шаг 3 из 7. Независим от CATALOG-114/115. Вместе с CATALOG-117 блокирует CATALOG-118.

- Нижняя панель: `+` (добавить документ) и иконка инструментов с бейджем-счётчиком (скрыт при нуле). Поповер — CATALOG-118, здесь только слот/кнопка.
- Полоса карточек над композером: `bg-surface-muted`, тип, название, `KIND · размер`, крестик.
- Схлопнуть `sessionDocuments` и `selectedDocs`; убрать заголовок, подпись и combobox `w-44`.
- Suggestions — одна строка, `overflow-x`.
- «Создать скилл» — в хедер чата.
- Сохранить CATALOG-90: подсказка шлёт `selectedDocIds`/`selectedDocs` через `sendCurrent`; repeat — `onSend(content)` без документов композера.

Токены только из `docs/ui-style-guide.md`. Референс: `backup-pre-revert-0234`, композер OpenRouter.

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст
На `pipeline/day-shift` (от `cfbe5f7`) композер старый:

- `frontend/src/components/Chat.tsx` — секция «Документы в сессии», чипсы `selectedDocs`, combobox, suggestions вызывают `onSend(s)` без документов, `onRepeat={onSend}`.
- `Chat.test.tsx` на этой ветке нет (тесты CATALOG-90 живут в night-shift). Добавить их здесь под новый UI.
- `frontend/src/App.tsx` рендерит `Chat` и кнопку создания скилла через проп `onCreateSkill`.
- Слот инструментов: пропсы-заглушки (`attachedSkillCount`, `onOpenTools`) без реализации поповера — CATALOG-118 подключит.

## Затрагиваемые файлы
- `frontend/src/components/Chat.tsx` — новый layout композера, `sendCurrent`, слот инструментов.
- `frontend/src/App.tsx` — кнопка «Создать скилл» в хедере чата; пропсы слота.
- `frontend/src/index.css` / `docs/ui-style-guide.md` — только если нужны существующие примитивы (не сырые палитры).
- `frontend/src/components/Chat.test.tsx` — новый файл: suggestions + docs, repeat без docs, submit с docs.
- `frontend/src/components/DocumentCombobox.tsx` — оставить как пикер по кнопке `+`, не как постоянный `w-44`.

## План действий
1. Ввести `sendCurrent` и перевести submit / suggestions на него; `onRepeat={(content) => onSend(content)}`.
2. Собрать `attachmentDocs` = session + pending selected; одна полоса карточек.
3. Убрать секцию/чипсы/постоянный combobox; `+` открывает пикер документов.
4. Suggestions в один ряд с `overflow-x`.
5. Вынести «Создать скилл» в хедер чата (`App.tsx` или шапка `Chat`).
6. Слот иконки инструментов + опциональный `attachedSkillCount` (0 по умолчанию).
7. Тесты под новый UI (роль кнопки `+` / «Добавить документ»).

## Критерии приёмки (Definition of Done)
- [ ] Документ виден ровно в одном месте; высота композера стабильна при 0/1/10 документах.
- [ ] Подсказка уносит текущий выбор документов; повторный клик — без них.
- [ ] Repeat не трогает выбор композера.
- [ ] Иконка инструментов есть, поповер не обязателен (CATALOG-118).
- [ ] Только токены style guide.
- [ ] `pnpm run build`, `lint`, `typecheck`, `test`.
