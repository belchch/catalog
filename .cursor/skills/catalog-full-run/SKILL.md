---
name: catalog-full-run
description: Автономный прогон полной цепочки смены: зависимости Plane → выгрузка Todo в планы → catalog-pipeline → bugbot-автофикс. Одна команда /catalog-full-run <RUN_NAME> связывает /plane-deps, /plane-todo-loop, /catalog-pipeline и /bugbot-grok-fix-loop общим именем прогона, путями и CHAIN_STATE. Использовать явно через /catalog-full-run или когда пользователь просит прогнать всю цепочку/смену целиком.
disable-model-invocation: true
---

# Skill: Catalog Full Run

Ты — **top-level оркестратор** четырёх фаз. Фазы **не** запускаются через Task-подагентов: ты читаешь `SKILL.md` очередной фазы и исполняешь её **сам, инлайн**. Причина: `catalog-pipeline` запрещает вложенность глубже `parent → generator/reviewer`, `bugbot-grok-fix-loop` — глубже `orchestrator → bugbot/fixer`. Мета-скилл — последовательный раннер с состоянием, не диспетчер подагентов.

```
фаза 0 preflight
  → фаза 1 /plane-deps
  → фаза 2 /plane-todo-loop
  → фаза 3 /catalog-pipeline
  → фаза 4 /bugbot-grok-fix-loop
  → финальный отчёт
```

## Параметры запуска
- **RUN_NAME** — имя прогона. Если пользователь не задал — `shift-<YYYY-MM-DD>` (локальная дата). Из него:
  - `PLANS_DIR = docs/plan/<RUN_NAME>/`
  - `BRANCH = pipeline/<RUN_NAME>`
  - `PIPELINE_STATE = .cursor/state/<RUN_NAME>.json`
  - `CHAIN_STATE = .cursor/state/chain-<RUN_NAME>.json`
- **phases** — опционально список фаз для ручного добора (например `phases=2,3`). По умолчанию `0,1,2,3,4`. Пропущенные фазы помечаются `skipped` в CHAIN_STATE только если гейт их отрезал; явно исключённые пользователем — тоже `skipped` с `failure_reason: "not in phases"`.
- Режим — **full auto**: вопросов не задавать; при падении фазы записать `failed`, применить гейты, дойти до финального отчёта.

## CHAIN_STATE

Файл `.cursor/state/chain-<RUN_NAME>.json` (в `.gitignore` через `.cursor/state/`). Писать атомарно (tmp + rename) после каждого перехода фазы.

```json
{
  "schema_version": 1,
  "run_name": "<RUN_NAME>",
  "plans_dir": "docs/plan/<RUN_NAME>/",
  "branch": "pipeline/<RUN_NAME>",
  "pipeline_state": ".cursor/state/<RUN_NAME>.json",
  "phases": {
    "0_preflight": {
      "status": "pending",
      "started": null,
      "updated": null,
      "failure_reason": null
    },
    "1_plane_deps": {
      "status": "pending",
      "started": null,
      "updated": null,
      "edges_created": [],
      "failure_reason": null
    },
    "2_plane_todo_loop": {
      "status": "pending",
      "started": null,
      "updated": null,
      "plans": [],
      "iter": 0,
      "failure_reason": null
    },
    "3_catalog_pipeline": {
      "status": "pending",
      "started": null,
      "updated": null,
      "pr_url": null,
      "steps_done": 0,
      "failure_reason": null
    },
    "4_bugbot": {
      "status": "pending",
      "started": null,
      "updated": null,
      "cycles": 0,
      "result": null,
      "failure_reason": null
    }
  }
}
```

Статусы фазы: `pending | running | done | failed | skipped`.

Если CHAIN_STATE уже существует при старте — продолжить с первой фазы в `pending`/`failed` (resume). Фазы со статусом `done`/`skipped` не переигрывать, если пользователь явно не попросил `phases=…` с ними.

## Фаза 0 — Preflight

1. Статус `running`, записать CHAIN_STATE.
2. `git status` — рабочее дерево должно быть чистым. Если грязное — `failed`, стоп всей цепочки (не чинить молча).
3. MCP `user-plane` — GetMcpTools / проверка `serverStatus == ready`. Если `needsAuth` — аутентифицируй; повторный сбой → `failed`, стоп.
4. `gh auth status` — при ошибке `failed`, стоп.
5. `mkdir -p <PLANS_DIR>`.
6. Ветка `BRANCH`: если есть локально или в origin — checkout; иначе `git checkout -b <BRANCH>` от `main` (после `git fetch origin` при необходимости). Несовпадение текущей ветки с уже существующим `PIPELINE_STATE.branch` — как в catalog-pipeline: стоп с диагностикой.
7. Создать/обновить CHAIN_STATE каркасом выше. Статус фазы 0 → `done`.

## Фаза 1 — plane-deps

1. Статус `running`.
2. Прочитать и исполнить инлайн [.cursor/skills/plane-deps/SKILL.md](../plane-deps/SKILL.md).
3. Успех → `done`, записать `edges_created` (список `CATALOG-A → CATALOG-B`).
4. Провал **не критичен**: статус `failed` + `failure_reason`, **продолжить** фазу 2 (очередь планов получится плоской).

## Фаза 2 — plane-todo-loop

1. Статус `running`.
2. Прочитать и исполнить инлайн [.cursor/skills/plane-todo-loop/SKILL.md](../plane-todo-loop/SKILL.md) с параметром **PLANS_DIR** из этого прогона.
3. Успех → `done`, записать `plans` (список basename `NN-CATALOG-*.md` в PLANS_DIR, без `*.design.md`) и `iter`.
4. Провал → `failed` + причина; фазы 3 и 4 → `skipped` («фаза 2 упала»), к отчёту.
5. **Гейт:** если пронумерованных `NN-CATALOG-*.md` в PLANS_DIR ноль — фазы 3 и 4 → `skipped` («нечего делать»), к отчёту. Фаза 2 при этом `done`.

## Фаза 3 — catalog-pipeline

1. Статус `running`.
2. Прочитать и исполнить инлайн [.cursor/skills/catalog-pipeline/SKILL.md](../catalog-pipeline/SKILL.md) с:
   - `PLANS_DIR`
   - `BRANCH`
   - `STATE = PIPELINE_STATE`
3. Успех → `done`, записать `pr_url` и `steps_done` (число шагов со статусом `done` в PIPELINE_STATE).
4. Провал → `failed` + причина.
5. **Гейт:** если `steps_done == 0` или нет `pr_url` — фаза 4 → `skipped` («нет PR / коммитов»), к отчёту.

## Фаза 4 — bugbot-grok-fix-loop

1. Статус `running`.
2. Прочитать и исполнить инлайн [.cursor/skills/bugbot-grok-fix-loop/SKILL.md](../bugbot-grok-fix-loop/SKILL.md) с `PR_TARGET` = `PIPELINE_STATE.pr_url` (или `CHAIN_STATE.phases.3_catalog_pipeline.pr_url`).
3. Успех → `done`, записать `cycles` и `result` (`clean` / `stuck` / `max_iter`).
4. Провал → `failed` + причина.

## Финальный отчёт

После всех фаз (или раннего выхода по гейту) сообщить:
- `RUN_NAME`, `BRANCH`, `PLANS_DIR`, путь CHAIN_STATE;
- по каждой фазе: статус + краткий итог (рёбра / число планов / PR URL / циклы bugbot);
- гейты, которые сработали;
- что делать дальше человеку (review PR, merge, повтор с `phases=…`).

## Жёсткие правила
- Фазы исполняются **инлайн** тобой. Не оборачивать plane-deps / plane-todo-loop / catalog-pipeline / bugbot в Task.
- Подагентов внутри фазы 3 и 4 запускаешь **сам**, по контракту этих скиллов (generator/reviewer/designer/bugbot/fixer) — это не «вложенный оркестратор», а выполнение их инструкций.
- Не коммитить `.cursor/state/*` и CHAIN_STATE.
- Не мержить PR.
- Без вопросов в full auto. Грязное дерево на preflight — единственная жёсткая остановка до фаз 1–4.
- Идемпотентность по CHAIN_STATE: повторный `/catalog-full-run <тот же RUN_NAME>` продолжает с незавершённых фаз.
