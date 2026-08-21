# CATALOG-155 — code: выходы в preview и configure скилла-черновика

- **Задача Plane:** [CATALOG-155](https://app.plane.so/belchch/projects/84997489-c485-4448-9ebe-0a06c4fa3cbc/issues/ca4f2f93-b6aa-4e73-bb5b-299fe9868e6c) (id: `ca4f2f93-b6aa-4e73-bb5b-299fe9868e6c`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** code
- **Очередь:** 03 · независимый от CATALOG-150 · блокирует 04 (ui-часть того же тикета)
- **Цель:** Провести декларацию выходов через контур preview/configure: `SkillPreview` отдаёт `outputs`, `SkillConfigureRequest` их принимает с семантикой `input_arity`, валидация переиспользует `parse_skill_outputs`, и решён вопрос синхронизации с артефактом сессии.

## Постановка задачи (актуальное ТЗ)
_(источник: описание задачи — комментариев не было; тикет `code + ui`, разбит на два плана — этот и `04-CATALOG-155-ui-…`)_

Тип: code + ui. Родитель: CATALOG-142. Порядок: независима от CATALOG-150, но её `OutputsList` потом подхватит флаг `multiple` автоматически.

**Контекст.** `SkillSettingsModal` — это точка, где человек подтверждает контракт скилла перед коммитом (CATALOG-6, `App.tsx:1087`). Сейчас в ней есть Имя, **Вход**, Провайдер, Модель, Режим рассуждений — и **нет Выхода**. Асимметрия бросается в глаза: `input_arity` настраивается именно здесь, а ровно симметричная ему декларация выходов — только в карточке OUTPUTS в панели артефактов (`ArtifactsPanel.tsx:906`), куда ещё надо догадаться зайти.

Хорошая новость: фронтенд к этому готов — CATALOG-146 вынес `OutputsList` отдельным компонентом с `value`/`onChange`/`rowErrors`, то есть он уже переиспользуем. Основная работа — на бэкенде: выходы не едут через этот контур вообще.

**Почему это не косметика.** Декларацию выходов пишет модель через `set_skill_outputs`. Если она ошиблась в описании или перепутала порядок (а порядок — это primary!), человек узнает об этом только после коммита и первого прогона. После коммита конфиг заморожен, и правка требует edit-сессии. Форма сохранения — последний момент, когда поправить дёшево.

**Что сделать (бэкенд-часть):**

1. **Отдавать выходы в preview.** `SkillPreview` (`api/schemas.py:224-232`) знает `input_arity`, но не знает выходов — добавить `outputs: list[SkillOutputOut]`. `_preview` в `api/skills.py` заполняет его из `SkillConfig.outputs`. (Сейчас наружу ездит только `outputs_count` в `SkillOut` — число без содержания.)
2. **Принимать выходы в configure.** `SkillConfigureRequest` (`api/schemas.py:235-256`) получает `outputs`. Семантика — **точно как у `input_arity`**: присутствие в `model_fields_set` значит «перезаписать», отсутствие — «не трогать» (`api/skills.py:1185-1186`). Пустой список — валидное значение (один выход, сегодняшнее поведение).
3. **Валидация одна на все входы.** Переиспользовать `parse_skill_outputs` (`skills/config.py:32-77`), а не писать вторую проверку в слое API: два набора правил разъедутся. Ошибки — 422 с теми же сообщениями, что в карточке артефакта.
4. **Синхрон с артефактом.** Решить и зафиксировать: правка выходов в модалке пишет в конфиг скилла-черновика — нужно ли обновлять артефакт `outputs` сессии. Иначе при повторном build правка человека молча потеряется — это главный риск задачи.

_(Пункты 5–7 ТЗ — фронтенд; они в плане `04-CATALOG-155-ui-…`.)_

## Предыстория
> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

_нет — комментариев к задаче не было_

## Контекст

**Разбиение тикета.** CATALOG-155 помечен `code + ui`; по правилу пайплайна он разложен на два плана. Этот — бэкенд-контур (preview → configure → валидация → синхрон с артефактом). Парный ui-план — `04-CATALOG-155-ui-output-block-settings-modal.md`; он идёт **после** этого и опирается на поле `outputs` в `SkillPreview` и приём `outputs` в `configureSkill`.

**Независимость от коллекций.** Шаг не зависит от CATALOG-150/153: он проводит выходы как есть. Когда `multiple` появится в `SkillOutput` (CATALOG-153), тот же `parse_skill_outputs` начнёт его валидировать, а `SkillOutputOut` — отдавать, без правок здесь. Если этот шаг едет **после** 01, поле `multiple` надо просто не потерять в `SkillOutputOut`.

**Фактическое состояние кода** (проверено):

- `SkillPreview` — [backend/catalog/api/schemas.py:224](backend/catalog/api/schemas.py:224): `name`, `description`, `kind`, `model`, `provider`, `reasoning`, `input_arity`, `allowed_tools`. Выходов нет.
- `SkillConfigureRequest` — [schemas.py:235](backend/catalog/api/schemas.py:235): `model`, `provider`, `reasoning`, `input_arity`, `name` + валидаторы. Докстринг прямо описывает семантику присутствия поля для `input_arity` — её и повторяем.
- `SkillOut.outputs_count: int = 0` — [schemas.py:91](backend/catalog/api/schemas.py:91): наружу сегодня едет только число.
- `_preview(config)` — [backend/catalog/api/skills.py:988](backend/catalog/api/skills.py:988), заполняет `input_arity` на [:997](backend/catalog/api/skills.py:997).
- Ручка configure — [api/skills.py:1175](backend/catalog/api/skills.py:1175): 409 для не-черновика, затем `configure_kwargs`; ключевые строки семантики `input_arity` — [:1185-1186](backend/catalog/api/skills.py:1185); дальше `update_skill_config(db, skill_id, **configure_kwargs)`.
- Валидация: `parse_skill_outputs` — [backend/catalog/skills/config.py:32](backend/catalog/skills/config.py:32) (возвращает `(items, errors)`), обёртка `skill_outputs_from_value` — [config.py:79](backend/catalog/skills/config.py:79) (бросает `ValueError` со склеенными сообщениями). Ограничения: `MAX_SKILL_OUTPUTS = 8` — [config.py:19](backend/catalog/skills/config.py:19), `OUTPUT_KEY_RE` — [config.py:18](backend/catalog/skills/config.py:18).
- Артефакт сессии: тул `set_skill_outputs` — [backend/catalog/skills/artifact_tools.py:786](backend/catalog/skills/artifact_tools.py:786), спека — [:990](backend/catalog/skills/artifact_tools.py:990); описание для планировщика — [backend/catalog/api/sessions.py:126](backend/catalog/api/sessions.py:126). Артефакты хранятся по `(session_id, type)` — [backend/catalog/storage/schema.py:108](backend/catalog/storage/schema.py:108).

**Пункт 4 — главный риск и единственное открытое решение.** Build собирает скилл из артефактов сессии (ADR-0015). Если правка выходов в модалке уходит только в `config_json` скилла, то повторный build из той же сессии перезапишет её артефактом, который писала модель, — и правка человека исчезнет молча. Варианты:

- **(a) писать в оба места** — configure обновляет и конфиг скилла, и артефакт `outputs` сессии, к которой привязан черновик. Правка переживает повторный build. Цена: ручка скилла начинает трогать сессию; нужна аккуратность, когда сессии нет.
- **(b) писать только в конфиг и явно принять потерю** — дешевле, но воспроизводит ровно тот баг, ради которого задача заведена.

План рекомендует **(a)**; выбор обязателен и должен быть записан в коде комментарием и в тестах.

## Затрагиваемые файлы

| Файл | Что делаем |
| --- | --- |
| [backend/catalog/api/schemas.py](backend/catalog/api/schemas.py) | новый `SkillOutputOut`; `SkillPreview.outputs`; `SkillConfigureRequest.outputs` + валидатор |
| [backend/catalog/api/skills.py](backend/catalog/api/skills.py) | `_preview` заполняет `outputs`; ручка configure пробрасывает `outputs` по семантике `model_fields_set`; 422 на невалидных |
| [backend/catalog/skills/config.py](backend/catalog/skills/config.py) | правок по существу нет — переиспользуем `parse_skill_outputs` |
| [backend/catalog/skills/artifact_tools.py](backend/catalog/skills/artifact_tools.py) | при выборе (a) — запись артефакта `outputs` сессии из configure |
| [backend/tests/test_apply.py](backend/tests/test_apply.py) / соответствующий api-тест | тесты preview, configure, 422, 409, `config_hash`, переживание повторного build |

## План действий

1. Ввести `SkillOutputOut` в [api/schemas.py](backend/catalog/api/schemas.py) — поля `key`, `description` (+ `multiple`, если CATALOG-153 уже влит и поле есть в `SkillOutput`).
2. Добавить `outputs: list[SkillOutputOut] = Field(default_factory=list)` в `SkillPreview` — [schemas.py:224](backend/catalog/api/schemas.py:224).
3. Заполнить его в `_preview` — [api/skills.py:988](backend/catalog/api/skills.py:988) из `config.outputs`, сохраняя порядок (порядок = primary, переставлять нельзя).
4. Добавить `outputs: list[dict] | None = None` в `SkillConfigureRequest` — [schemas.py:235](backend/catalog/api/schemas.py:235) и валидатор поля, который зовёт `parse_skill_outputs` и на ошибках поднимает `ValueError` со склеенными сообщениями (FastAPI отдаст 422). Второй набор правил в слое API **не писать**.
5. Обновить докстринг `SkillConfigureRequest` — семантика присутствия для `outputs` такая же, как у `input_arity`; пустой список — валидное значение «выходов нет».
6. В ручке configure — [api/skills.py:1175](backend/catalog/api/skills.py:1175) — после существующей ветки `input_arity` добавить симметричную:
   `if "outputs" in req.model_fields_set: configure_kwargs["outputs"] = <разобранные SkillOutput>`.
   Проверить, что `update_skill_config` умеет принимать `outputs`; если нет — добавить туда поддержку тем же способом, что и для прочих полей конфига.
7. Проверить, что 409 для не-черновика срабатывает **до** любой записи (сейчас так и есть — [:1175](backend/catalog/api/skills.py:1175)).
8. **Пункт 4 — синхрон с артефактом.** Реализовать вариант (a): при перезаписи выходов через configure обновить артефакт `outputs` сессии, к которой привязан скилл-черновик, тем же сериализованным JSON. Если сессия не найдена — не падать, а пропустить запись. Решение зафиксировать комментарием в коде.
9. Убедиться, что после configure `config_hash` пересчитывается (он считается из `to_json` — [apply.py:315](backend/catalog/skills/apply.py:315)); правка выходов обязана его менять.
10. Тесты: preview отдаёт выходы с описаниями и порядком; configure перезаписывает; отсутствие поля не трогает; пустой список — валиден; дубль ключа / ключ не по шаблону / пустое описание / 9-й выход → 422 с теми же сообщениями, что в карточке артефакта; не-черновик → 409; `config_hash` изменился; повторный build из той же сессии не теряет правку (пункт 8).
11. Прогнать все шесть команд из [CLAUDE.md](CLAUDE.md).

## Критерии приёмки (Definition of Done)

- [ ] `GET`-контур preview отдаёт `outputs` с ключами, описаниями и сохранённым порядком.
- [ ] `configure` перезаписывает выходы при наличии поля в теле и не трогает их при отсутствии — семантика совпадает с `input_arity`.
- [ ] Пустой список выходов — валидное значение, сохраняется без ошибки и не ломает старый сценарий.
- [ ] Дубль ключа, ключ не по шаблону, пустое описание и 9-й выход дают 422 с теми же сообщениями, что и карточка артефакта; вторая копия правил в слое API не появилась.
- [ ] `config_hash` меняется после правки выходов через configure.
- [ ] Правка выходов через configure не теряется при повторном build из той же сессии; выбранный вариант синхронизации зафиксирован в коде.
- [ ] Configure не-черновика по-прежнему 409, без побочных записей.
- [ ] Порядок выходов сохраняется на всём пути; перестановка первого меняет primary в замороженном конфиге.
- [ ] Backend: `ruff check .`, `pytest` — зелёные.
- [ ] Frontend: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck`, `pnpm run test` — зелёные.
