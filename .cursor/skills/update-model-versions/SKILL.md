---
name: update-model-versions
description: Обновляет зашитые slug'и моделей в `.cursor/skills` и `.cursor/agents` до последних версий того же семейства (Grok, Claude Opus/Sonnet, Gemini Flash, GLM). Использовать явно через `/update-model-versions` или когда пользователь просит обновить модели скиллов/пайплайна на latest, подтянуть свежие версии, bump model slugs.
disable-model-invocation: true
---

# Skill: update-model-versions

Cursor не резолвит `latest` / `auto` в «самую свежую версию семейства». Этот skill сам находит актуальные версии и переписывает пины.

Не трогает `~/.cursor/skills`, `~/.cursor/skills-cursor` и этот skill. Не коммитит.

## Команды

- `status` / `check` / «что устарело» — только отчёт, файлы не менять.
- `apply` / «обнови» / «подтяни latest» — найти mapping и применить.
- Если команда не названа — `status`, затем спросить, применять ли.

## Файлы в скоупе

Только то, что сканирует скрипт:

- `.cursor/skills/pipeline-model-mode/SKILL.md`
- `.cursor/skills/pipeline-model-mode/scripts/apply_mode.py`
- `.cursor/skills/bugbot-grok-fix-loop/SKILL.md`
- `.cursor/skills/catalog-pipeline/SKILL.md`
- `.cursor/agents/catalog-*.md`

Таблица в `pipeline-model-mode/SKILL.md` и словарь `MODES` в `apply_mode.py` должны остаться идентичными.

## Алгоритм

### 1. Снять текущие пины

Из корня репозитория:

```bash
python3 .cursor/skills/update-model-versions/scripts/pin_models.py scan
```

Вывод: `slug<TAB>files`. Если `MISSING` — остановиться.

### 2. Узнать latest того же семейства

Источники, в этом порядке:

1. https://cursor.com/docs/models-and-pricing (WebFetch) — список моделей Cursor.
2. Параметр `model` инструмента Task в **этом** сеансе — единственный источник правды для Task-slug'ов (`*-high-fast`, `*-thinking-high`, `*-medium`).
3. GLM: `backend/catalog/llm/zai.py`. Новый id допустим, только если он уже есть в этом каталоге.

Семейство пина не менять:

| Пин | Семейство | Не перескакивать на |
|---|---|---|
| `cursor-grok-*` / `Grok X.Y` | Grok | Composer, Auto |
| `claude-opus-*` | Claude Opus | Fable, Mythos, Sonnet |
| `claude-sonnet-*` | Claude Sonnet | Opus |
| `gemini-*-flash` | Gemini Flash | Pro / Image |
| `glm-*-turbo` | GLM turbo | flagship GLM |
| `glm-*` (не turbo) | GLM flagship | turbo |
| `composer-*` | Composer | Grok |
| `gpt-*` | та же линия GPT (`sol`/`terra`/`mini`/…) | другая линия |

Правила выбора версии:

- Берётся наибольший номер в том же семействе из docs (GA / не Hidden). Hidden — только если текущий пин уже из hidden-линейки.
- Суффиксы сохранить: `[effort=high]`, `-high-fast`, `-thinking-high`, `-medium`, `Fast`.
- Форма slug'а может смениться (`claude-opus-4-8` → `claude-opus-5`) — это ок, семейство то же.
- Человекочитаемое `Grok X.Y` обновлять вместе с `cursor-grok-X.Y`.
- `inherit` / `auto` / `fast` не трогать.
- Не добавлять модели, которых не было в scan.
- Если latest совпадает с пином — в mapping не включать.

Для Task-пина (сейчас `FIX_MODEL` в `bugbot-grok-fix-loop`): новый slug обязан быть в allowlist Task. Если подходящего Grok там нет — не выдумывать, сообщить и пропустить этот пин.

### 3. Собрать mapping

JSON-объект `старый_slug → новый_slug`. Ключи — **точные** строки из scan, не префиксы.

Показать таблицу `было → станет` (и какие пины уже актуальны). Для `status` на этом остановиться.

### 4. Применить

```bash
python3 .cursor/skills/update-model-versions/scripts/pin_models.py apply - <<'EOF'
{"old-slug":"new-slug"}
EOF
```

Скрипт режет более длинные ключи первыми. После записи:

```bash
python3 .cursor/skills/update-model-versions/scripts/pin_models.py scan
python3 .cursor/skills/pipeline-model-mode/scripts/apply_mode.py status
```

Если `apply_mode.py status` говорит, что агенты не совпадают ни с одним пресетом, а state помнит режим — `set` этот режим, чтобы frontmatter агентов снова совпал с `MODES`.

Если в `bugbot-grok-fix-loop` после замены фраза «единственный доступный Grok-slug» стала неверной (в Task allowlist больше одного Grok) — поправить формулировку.

### 5. Отчёт

- какие семейства обновлены (`old → new`);
- какие уже были latest;
- какие пропущены и почему (нет в Task allowlist, нет в `zai.py`, hidden, смена семейства);
- список изменённых файлов.

## Жёсткие правила

- Не писать в файлы `latest` / `auto` как замену версии — Cursor это не резолвит в семейство.
- Не обновлять цены, промо и «единственный slug», если это не следует из замены.
- Не расширять скоуп файлов без явной просьбы.
- Не коммитить и не пушить.
