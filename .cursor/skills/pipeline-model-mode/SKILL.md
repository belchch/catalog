---
name: pipeline-model-mode
description: Переключает режим моделей для цепочки catalog-pipeline. Меняет `model:` в `.cursor/agents/catalog-*.md` между двумя пресетами — `default` (Grok/Claude/Gemini) и `glm` (GLM-семейство z.ai). Использовать явно через `/pipeline-model-mode <default|glm|status|list>` или когда пользователь просит переключить/показать режим моделей пайплайна.
disable-model-invocation: true
---

# Skill: pipeline-model-mode

Переключатель режима моделей для цепочки `catalog-pipeline` (`catalog-generator`, `catalog-designer`, `catalog-reviewer`, `catalog-ui-reviewer`). Skill только переписывает поле `model:` в frontmatter агентов и пишет состояние в `state`. Он не трогает `catalog-pipeline/SKILL.md` (parent-оркестратор): модель parent'а всегда выбирает пользователь в UI/CLI.

## Режимы и пресеты

| Роль | Файл | `default` | `glm` |
|---|---|---|---|
| catalog-generator | `.cursor/agents/catalog-generator.md` | `cursor-grok-4.5[effort=high]` | `glm-5-turbo` |
| catalog-designer | `.cursor/agents/catalog-designer.md` | `claude-opus-4-8[effort=high]` | `glm-5.2` |
| catalog-reviewer | `.cursor/agents/catalog-reviewer.md` | `claude-sonnet-5[effort=high]` | `claude-sonnet-5[effort=high]` |
| catalog-ui-reviewer | `.cursor/agents/catalog-ui-reviewer.md` | `gemini-3.5-flash` | `gemini-3.5-flash` |

`reviewer` и `ui-reviewer` одинаковы в обоих режимах — пресеты оставлены в таблице явно, чтобы не было соблазна «дополировать» их под GLM.

Slug'и GLM — bare z.ai id (`glm-5.2`, `glm-5-turbo`), без суффикса `[effort=…]` и без префикса провайдера. Соответствуют каталогу `backend/app/llm/zai.py`.

## Команды

Запусти из корня репозитория:

```bash
# Показать текущий режим и результирующие модели
python .cursor/skills/pipeline-model-mode/scripts/apply_mode.py status

# Сравнить пресеты без изменений
python .cursor/skills/pipeline-model-mode/scripts/apply_mode.py list

# Установить режим
python .cursor/skills/pipeline-model-mode/scripts/apply_mode.py set default
python .cursor/skills/pipeline-model-mode/scripts/apply_mode.py set glm
```

Допустимые значения `set`: `default`, `glm`. Любое другое → скрипт выходит с ошибкой и ниччего не меняет.

## Что делает агент при запросе

1. Если пользователь назвал режим (`default` / `glm`) или команду (`status` / `list`) — запусти скрипт с нужным аргументом. Имя режима нормализуй регистром (`GLM` → `glm`, `Default` → `default`).
2. Если режим не указан — сначала `status`, затем спроси у пользователя, какой режим поставить, и только потом `set`.
3. После `set` всегда показывай вывод скрипта целиком (проверка валидации и фактические `model:` после записи).
4. Не комментируй решение пользователя — какой режим ставить, решает он. Если выбранный режим уже активен, сообщи об этом и ничего не меняй.

## Гарантии

- Скрипт атомарно переписывает каждый файл (tmp + rename), меняя ровно одну строку `^model: …` в frontmatter.
- Если в файле нет валидного frontmatter с полем `model:` — скрипт падает с диагностикой и не трогает ни один файл.
- Если slug в пресете не соответствует фактическому значению в файле (кто-то вручную правил) — `status` предупреждает о расхождении, `set` всё равно приводит файл к пресету.
- State-файл: `.cursor/state/pipeline-model-mode.json` (в `.gitignore`, лежит в уже игнорируемой `.cursor/state/`).
- Parent `catalog-pipeline/SKILL.md` не трогается никогда.

## Расширение пресетов

Чтобы добавить третий режим (например, `cheap`): заведи новый ключ в словаре `MODES` в `scripts/apply_mode.py` с теми же четырьмя ролями и обнови таблицу выше. Сами роли (четыре файла) фиксированы архитектурой `catalog-pipeline` — добавлять/убирать роли без правки parent-skill нельзя.
