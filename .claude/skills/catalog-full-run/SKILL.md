---
name: catalog-full-run
description: Автономный прогон полной смены в Claude Code, одна команда — выгрузка Todo из Plane в планы (plane-todo-loop) и запуск разработки workflow'ом catalog-pipeline. /catalog-full-run <RUN_NAME> связывает фазы общим именем прогона, путями и CHAIN_STATE. Использовать явно через /catalog-full-run или когда пользователь просит прогнать всю цепочку/смену целиком — выгрузить todo и начать разработку.
disable-model-invocation: true
---

# Skill: Catalog Full Run (Claude)

Ты — **top-level оркестратор** цепочки. Фаза планов исполняется **инлайн** (читаешь SKILL.md и выполняешь сам), фаза разработки — вызовом тула **Workflow** со скриптом `.claude/workflows/catalog-pipeline.js` (весь параллелизм generator/reviewer живёт внутри workflow).

```
фаза 0 preflight
  → фаза 1 plane-todo-loop   (инлайн: Todo из Plane → планы NN-CATALOG-*.md)
  → фаза 2 catalog-pipeline  (Workflow: разработка по планам до PR)
  → финальный отчёт
```

Порт цепочки `/catalog-full-run` из Cursor. Фазы plane-deps (запись рёбер в Plane) и bugbot-автофикса **не портированы** — зависимости здесь только читаются (это делает сам plane-todo-loop при нумерации `NN-`), автофикс по ревью PR остаётся за человеком.

## Параметры запуска
- **RUN_NAME** — имя прогона. Если не задан — `shift-<YYYY-MM-DD>` (локальная дата; если каталог/стейт с этим именем уже существуют от cursor-прогона — добавить суффикс `-claude`). Из него:
  - `PLANS_DIR = docs/plan/<RUN_NAME>/`
  - `BRANCH = pipeline/<RUN_NAME>`
  - `PIPELINE_STATE = .claude/state/<RUN_NAME>.json`
  - `CHAIN_STATE = .claude/state/chain-<RUN_NAME>.json`
- **phases** — опционально (например `phases=2`). По умолчанию `0,1,2`. Явно исключённые — `skipped` с `failure_reason: "not in phases"`.
- Режим — **full auto**: вопросов не задавать; при падении фазы записать `failed`, применить гейты, дойти до финального отчёта.

## CHAIN_STATE

Файл `.claude/state/chain-<RUN_NAME>.json` (каталог в `.gitignore`). Писать атомарно (tmp + rename) после каждого перехода фазы.

```json
{
  "schema_version": 1,
  "run_name": "<RUN_NAME>",
  "plans_dir": "docs/plan/<RUN_NAME>/",
  "branch": "pipeline/<RUN_NAME>",
  "pipeline_state": ".claude/state/<RUN_NAME>.json",
  "phases": {
    "0_preflight":       { "status": "pending", "started": null, "updated": null, "failure_reason": null },
    "1_plane_todo_loop": { "status": "pending", "started": null, "updated": null, "plans": [], "iter": 0, "failure_reason": null },
    "2_catalog_pipeline":{ "status": "pending", "started": null, "updated": null, "run_id": null, "pr_url": null, "steps_done": 0, "failure_reason": null }
  }
}
```

Статусы фазы: `pending | running | done | failed | skipped`.

Если CHAIN_STATE уже существует при старте — продолжить с первой фазы в `pending`/`failed` (resume). Фазы `done`/`skipped` не переигрывать, если пользователь явно не попросил `phases=…` с ними. Для resume фазы 2 использовать `run_id` из CHAIN_STATE: `Workflow({scriptPath, resumeFromRunId})`.

## Фаза 0 — Preflight

1. Статус `running`, записать CHAIN_STATE.
2. Рабочее дерево должно быть чистым — по тому же определению, что и preflight стюарда ([.claude/agents/catalog-steward.md](../../agents/catalog-steward.md), задача `preflight` п. 1): untracked-файлы под `PLANS_DIR` и `.claude/` не считаются грязью, всё остальное — считается.
   ```bash
   PLANS_DIR="docs/plan/<RUN_NAME>/"
   git status --porcelain -uall | awk -v p="$PLANS_DIR" '
     /^\?\? / {
       f = substr($0, 4)
       if (p != "" && index(f, p) == 1) next
       if (index(f, ".claude/") == 1) next
     }
     { print }'
   ```
   Непустой вывод → `failed`, стоп всей цепочки (не чинить молча).
3. Plane доступен: `mcp__plane__get_projects` (через ToolSearch, если не загружен) содержит проект `CATALOG` (id `84997489-c485-4448-9ebe-0a06c4fa3cbc`). Ошибка → `failed`, стоп.
4. `gh auth status` — ошибка → `failed`, стоп.
5. `mkdir -p <PLANS_DIR>`.
6. Ветка `BRANCH`: есть локально или в origin → checkout; иначе `git checkout -b <BRANCH>` от `main` (после `git fetch origin` при необходимости). Несовпадение текущей ветки с уже существующим `PIPELINE_STATE.branch` — стоп с диагностикой.
7. Создать/обновить CHAIN_STATE каркасом. Фаза 0 → `done`.

## Фаза 1 — plane-todo-loop

1. Статус `running`.
2. Прочитать и исполнить **инлайн** [.claude/skills/plane-todo-loop/SKILL.md](../plane-todo-loop/SKILL.md) с параметром **PLANS_DIR** этого прогона.
3. Успех → `done`, записать `plans` (basename'ы `NN-CATALOG-*.md` в PLANS_DIR, без `*.design.md`) и `iter`.
4. Провал → `failed` + причина; фаза 2 → `skipped` («фаза 1 упала»), к отчёту.
5. **Гейт:** пронумерованных `NN-CATALOG-*.md` в PLANS_DIR ноль → фаза 2 `skipped` («нечего делать»), фаза 1 при этом `done`, к отчёту.

## Фаза 2 — catalog-pipeline (Workflow)

1. Статус `running`.
2. Запустить тул **Workflow**:
   ```
   Workflow({
     scriptPath: ".claude/workflows/catalog-pipeline.js",
     args: {
       plansDir: "<PLANS_DIR>",
       state:    "<PIPELINE_STATE>",
       branch:   "<BRANCH>"
     }
   })
   ```
   Записать `run_id` из результата запуска в CHAIN_STATE сразу, не дожидаясь конца.
3. Дождаться завершения (task-notification). Из результата workflow взять `prUrl`, число шагов `done` → записать `pr_url`, `steps_done`; статус → `done`. Если результат пуст/неожиданный — прочитать `journal.jsonl` из transcript-каталога run'а прежде чем объявлять провал.
4. Провал / прерывание → `failed` + причина; в отчёте напомнить про resume: `Workflow({scriptPath, resumeFromRunId: "<run_id>"})`.

## Финальный отчёт

- `RUN_NAME`, `BRANCH`, `PLANS_DIR`, путь CHAIN_STATE;
- по каждой фазе: статус + краткий итог (число планов / PR URL / steps_done);
- гейты, которые сработали;
- что делать дальше человеку (review PR, merge, повтор с `phases=…`, resume workflow по run_id).

## Жёсткие правила
- Фаза 1 исполняется **инлайн** тобой — не оборачивать plane-todo-loop в Task/Agent.
- Фаза 2 — только через тул Workflow с `catalog-pipeline.js`; не исполнять пайплайн вручную и не спавнить его агентов самому.
- Не коммитить `.claude/state/*` и CHAIN_STATE.
- Не мержить PR.
- Без вопросов в full auto. Грязное дерево на preflight — единственная жёсткая остановка до фаз 1–2.
- Идемпотентность по CHAIN_STATE: повторный `/catalog-full-run <тот же RUN_NAME>` продолжает с незавершённых фаз; фазу 2 возобновлять через `resumeFromRunId`.
