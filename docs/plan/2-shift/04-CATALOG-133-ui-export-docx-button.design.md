# CATALOG-133 — Дизайн UI

- **Источник:** docs/plan/2-shift/04-CATALOG-133-ui-export-docx-button.md
- **Статус дизайна:** Ready

## Цель и пользовательский путь

Пользователь получает docx на диске в папке воркспейса, не покидая экран и не скачивая файл.

Два входа в действие:

1. **Карточка прогона (`RunView`).** Прогон завершён → в панели «Результат» пользователь видит кнопку «Выгрузить в docx» → жмёт → кнопка становится «Выгружаю…» и блокируется → рядом появляется относительный путь `export/…` с кнопкой копирования; либо сообщение об ошибке с `detail` бэкенда.
2. **Выбранный (открытый) документ.** Полноценного вьюера документа в приложении нет: «открытый документ» — это документ, выбранный в сайдбаре (`currentDocId` из `App.tsx`, подсвечен в `DocumentList`). Поэтому вторая точка входа — панель действий выбранного документа в секции «Документы»: пользователь кликает документ в списке → над списком появляется панель с названием документа и той же кнопкой → тот же цикл состояний.

Путь показываем как есть (относительно корня воркспейса) — файл уже лежит в папке пользователя, скачивание и «показать в Finder» вне скоупа.

## Дерево компонентов и файлы

| Файл | Что | Назначение |
|------|-----|-----------|
| `frontend/src/api.ts` | новое | `ExportDocxOut { ok, path, headings, tables }` + `exportDocx({ doc_ids, title?, template? })` — `POST /export/docx` через существующий `jsonFetch`, ошибки уже приходят как `ApiError` с `detail`. |
| `frontend/src/components/ExportDocxButton.tsx` | новый компонент | Вся машина состояний экспорта: кнопка + результат/ошибка + копирование пути. Единственный носитель логики, обе точки входа его переиспользуют. |
| `frontend/src/components/RunView.tsx` | изменение | Рендер `ExportDocxButton` в панели «Результат». |
| `frontend/src/components/DocumentList.tsx` | изменение | Панель действий выбранного документа с `ExportDocxButton`. |
| `frontend/src/components/ExportDocxButton.test.tsx` | новый тест | idle / loading / success c путём / error. |

Новых зависимостей нет. Иконки — уже существующие `SpinnerIcon`, `CopyIcon`, `CheckIcon` из `components/icons.tsx`; новых иконок не заводим.

### Контракт `ExportDocxButton`

```
interface ExportDocxButtonProps {
  docIds: string[]
  title?: string
  disabled?: boolean            // нет воркспейса / прогон ещё идёт
  disabledHint?: string         // подсказка в title, когда disabled
  layout?: 'inline' | 'stacked' // 'inline' по умолчанию (RunView), 'stacked' — сайдбар
}
```

Внутреннее состояние: `status: 'idle' | 'loading' | 'success' | 'error'`, `result: ExportDocxOut | null`, `error: string | null`, `copied: boolean`.

Сброс в `idle` при смене цели экспорта (`docIds.join(',')`) — переключение документа или прогона не оставляет чужой путь на экране.

## Layout и состояния

Корень компонента: `flex flex-wrap items-center gap-2` (`inline`) либо `flex flex-col items-stretch gap-1.5` (`stacked`).

| Состояние | Кнопка | Что рядом |
|-----------|--------|-----------|
| **idle** | `.btn-secondary`, подпись «Выгрузить в docx», активна | ничего |
| **disabled** (нет воркспейса, прогон не завершён, `docIds` пуст) | `.btn-secondary` + `disabled` (стиль дизабла даёт сам примитив: `surface-muted` + `ink-faint` + `cursor-not-allowed`) | `title` = `disabledHint`, по умолчанию «Нет документов для выгрузки» |
| **loading** | `disabled`, `aria-busy="true"`, подпись «Выгружаю…», слева `SpinnerIcon` (`size-3.5`, `mr-1.5`) | ничего |
| **success** (`ok: true`) | снова idle, доступна повторная выгрузка | плашка пути (см. ниже) |
| **success с расхождением** (`ok: false`, `path` есть) | снова idle | та же плашка, но в warning-палитре + текст «самопроверка не сошлась» |
| **error** | снова idle | блок ошибки |

**Плашка пути** (`role="status"`, `aria-live="polite"`): `inline-flex items-center gap-1.5 rounded-control border px-2 py-1 text-[11px]`; палитра `border-success-line bg-success-soft text-success-ink` для `ok: true` и `border-warning-line bg-warning-soft text-warning-ink` для `ok: false`. Внутри:

- путь в `<code className="font-mono">`; в `inline` — `min-w-0 truncate` + `title={path}`, в `stacked` — `break-all`;
- при `ok: false` перед путём короткий префикс «Записан, но самопроверка не сошлась:»;
- справа иконочная кнопка копирования `.btn-icon-ghost` `size-6`: `CopyIcon` → на 1.5 с `CheckIcon` c `text-success`.

**Блок ошибки** (`role="alert"`): `rounded-control border border-danger-line bg-danger-soft px-2 py-1 text-[11px] text-danger-ink break-words`, текст — результат `extractApiDetail(e)` без собственных префиксов и без «Ошибка: ». В `inline`-раскладке блок получает `basis-full`, чтобы длинный `detail` переносился на свою строку, а не сжимал кнопку.

**Размещение в `RunView`.** В правой панели «Результат», отдельным блоком под кнопкой «Сохранить как новый документ» и над телом результата — то есть после плашки «Документ создан», перед `MarkdownView`. Раскладка `inline`, отступ `mb-2`, чтобы попадать в ритм соседних блоков панели.

- `docIds` = `[outputDocId]`, если документ прогона есть; иначе `run.meta?.inputDocs ?? []`.
- `title` = заголовок выходного документа, если он известен (`outputDoc?.title`), иначе не передаём — дефолт подставит бэкенд.
- Пока `!run.finished` — кнопка `disabled`, `disabledHint` «Дождитесь завершения прогона». Кнопка при этом видна всегда (не появляется скачком в конце прогона).
- Если целевых документов нет вовсе (`docIds.length === 0`) — кнопка `disabled` с подсказкой «Нет документов для выгрузки».

**Размещение в `DocumentList`.** Панель выбранного документа между зоной загрузки файла и `<ul>` со списком: `rounded-md border border-line bg-surface px-2 py-2 flex flex-col gap-1.5`. Рендерится только когда `currentDocId` найден в `docs.documents`. Содержимое: строка названия `text-[11px] text-ink-faint truncate` + `title={doc.title}`, ниже `ExportDocxButton` в раскладке `stacked` (кнопка `w-full`), `disabled={uploadDisabled}` (тот же признак «нет воркспейса», что и у загрузки), `disabledHint` «Откройте папку воркспейса», `title={doc.title}`, `docIds={[doc.id]}`. Мультивыбор не вводим — экспортируется ровно один документ.

## Взаимодействия

- Клик по активной кнопке → `POST /export/docx`; повторные клики во время запроса невозможны (кнопка `disabled`).
- Успех → плашка пути; фокус остаётся на кнопке (не перебрасываем), появление плашки озвучивается live-регионом.
- Повторный клик после успеха → новый запрос: сначала `loading`, старая плашка убирается, затем новый путь (бэкенд выделит новое имя файла, старое сообщение не должно «залипать»).
- Ошибка → блок `role="alert"`, кнопка снова активна для ретрая; следующий запуск очищает и ошибку, и прошлый путь.
- Копирование: `navigator.clipboard.writeText(path)` с тем же legacy-fallback через скрытую `textarea`, что в `MessageCommands.tsx`; подтверждение — смена иконки на 1.5 с плюс `sr-only` live-текст «Скопировано». Отказ clipboard проглатываем молча (иконка просто не меняется) — как в существующем паттерне.
- Смена выбранного документа или закрытие/смена прогона → состояние сбрасывается в `idle`.
- Таймер подтверждения копирования чистится в `useEffect`-cleanup (иначе setState после размонтирования).
- Крайние случаи: пустой `docIds`; прогон без выходного документа и без входных (кнопка disabled); отсутствие воркспейса (409 с бэкенда всё равно покажется как `detail`, но до запроса не доходим — кнопка disabled); `ok: false` — это не ошибка запроса, путь показываем, тон warning.

## Стиль и токены

Только семантические утилиты из `docs/ui-style-guide.md`, сырые палитры Tailwind (`slate-*`, `red-*`, …) запрещены.

- Кнопка — примитив `.btn-secondary`: экспорт вторичен относительно `.btn-primary` «Сохранить как новый документ» в той же панели.
- Копирование — `.btn-icon-ghost` (тот же примитив, что у копирования сообщения в чате).
- Успех — `success-soft` / `success-line` / `success-ink`; расхождение самопроверки — `warning-*`; ошибка — `danger-soft` / `danger-line` / `danger-ink`.
- Типографика: подписи кнопок `text-xs` (из примитива), служебные строки — `text-[11px]`, путь — `font-mono`.
- Радиусы: `rounded-control` у плашек, `rounded-md` у панели в сайдбаре (как у соседнего дропзона загрузки).
- Отступы: `gap-2` между кнопкой и плашкой в `inline`, `gap-1.5` в `stacked`, `mb-2` вокруг блока в `RunView`.
- Спиннер — существующий `SpinnerIcon` c `animate-spin motion-reduce:animate-none` (уважает `prefers-reduced-motion`).
- Disabled — только через `disabled` на `<button>` (примитив даёт `surface-muted` + `ink-faint` + `cursor-not-allowed`), никакого `opacity-50`.

## Доступность (a11y)

- Кнопка — `type="button"`, доступное имя «Выгрузить в docx»; при `docIds.length > 1` уточняем через `title`/`aria-label`: «Выгрузить документы (N) в docx».
- Во время запроса — `aria-busy="true"` и `disabled`; текст подписи меняется на «Выгружаю…», спиннер `aria-hidden`.
- Успех — контейнер пути `role="status" aria-live="polite"`; ошибка — `role="alert"`.
- Кнопка копирования — `aria-label="Скопировать путь"`, подтверждение дублируется `sr-only` live-регионом «Скопировано».
- Фокус-кольцо `ring-2 ring-brand` приходит из примитивов; не переопределяем и не убираем.
- Порядок табуляции естественный: кнопка экспорта → кнопка копирования; фокус нигде не перехватывается программно.
- Контраст обеспечен токенами `*-ink` на `*-soft`; путь не кодируем только цветом — рядом всегда текстовая формулировка состояния.

## Контракты данных

`POST /export/docx` (шаг 03, CATALOG-132; `backend/catalog/api/export.py`, `backend/catalog/api/schemas.py`):

- Запрос: `{ doc_ids: string[] (min 1), title?: string, template?: string }` — пустые `title`/`template` не отправляем, дефолты на бэкенде.
- Ответ 200: `{ ok: boolean, path: string, headings: number, tables: number }`. `path` — относительный, вида `export/…docx`. `ok: false` = файл записан, но самопроверка через `extract_text` не сошлась.
- Ошибки: 404 `document not found`, 400 (в т.ч. `template not found`), 409 без воркспейса — UI показывает `detail` как есть через `extractApiDetail`.
- `headings` / `tables` в UI этого среза не показываем — только влияют на трактовку `ok`.

Источники `doc_ids` на фронте: `UseRunStreamResult.outputDocId` и `RunMeta.inputDocs` (`frontend/src/hooks/useRunStream.ts`), `currentDocId` + `docs.documents` (`App.tsx`, `useDocuments`).

## Критерии визуальной приёмки

- [ ] Кнопка «Выгрузить в docx» видна в панели «Результат» карточки прогона и в панели выбранного документа в секции «Документы».
- [ ] Кнопка использует примитив `.btn-secondary`; в `frontend/src` не появилось сырых палитр Tailwind (`slate-*`, `red-*`, `green-*`, …).
- [ ] Во время запроса кнопка `disabled`, подпись «Выгружаю…», виден `SpinnerIcon`, выставлен `aria-busy="true"`; повторный клик не отправляет второй запрос.
- [ ] Успех: плашка `success-soft` с относительным путём `export/…` в `font-mono` и кнопкой копирования; путь не обрезает соседние элементы (`truncate` + `title` в inline, `break-all` в stacked).
- [ ] `ok: false` рендерится в warning-палитре с пояснением про самопроверку, а не как ошибка.
- [ ] Ошибка: блок `danger-soft` + `border-danger-line` + `text-danger-ink` с `role="alert"`, текст равен `detail` из API; кнопка снова активна.
- [ ] Копирование меняет иконку на `CheckIcon` примерно на 1.5 с и объявляет «Скопировано» в `sr-only` live-регионе.
- [ ] Смена выбранного документа или прогона сбрасывает плашку пути/ошибки в `idle`.
- [ ] Пока прогон не завершён и когда воркспейс не открыт, кнопка задизейблена штатным `disabled` (не `opacity-50`) и имеет поясняющий `title`.
- [ ] Фокус-кольцо `ring-2 ring-brand` видно на кнопке экспорта и на кнопке копирования.
