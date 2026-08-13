---
name: catalog-pipeline
description: Автономный ночной pipeline по шагам docs/plan/night-shift/NN-CATALOG-*.md. Владеет общей веткой pipeline, PR, файлом состояния .cursor/state/night-shift.json и циклом generator↔reviewer (до 5 циклов на шаг). Использовать явно через /catalog-pipeline, когда нужно прогнать один или несколько шагов ночного пайплайна.
disable-model-invocation: true
---

# Skill: catalog-pipeline

Ты — **parent-оркестратор** одного или нескольких шагов ночного pipeline. Ты (а не подагенты) владеешь git, PR и файлом состояния. Подагенты `catalog-generator` и `catalog-reviewer` НИКОГДА не коммитят и не пушат — это твоя работа.

Модель парента выбирается пользователем в UI/CLI до запуска (ориентир: Grok 4.5). Эта инструкция работает независимо от того, какая модель её выполняет.

## Параметры запуска
- **STEPS** — список шагов для прогона. Если пользователь не указал явно — возьми из `.cursor/state/night-shift.json.steps`, отфильтровав `status == "pending"`, в порядке очереди из `docs/plan/night-shift/`: по числовому префиксу `NN-` в имени файла (`00-…`, `01-…`, …), не по номеру CATALOG-NN. Файлы `*.design.md` в очередь не входят.
- **BRANCH** — общая ветка pipeline. Если в state есть `branch` — используй её. Иначе спроси/уточни у пользователя (не угадывай имя ветки молча).
- **CYCLES_MAX = 5** (на шаг).
- **STATE** = `.cursor/state/night-shift.json` (см. схему ниже). Файл в `.gitignore`, никогда не коммитить.
- **UI-шаг** — шаг, в файле плана которого есть маркер `- **Тип шага:** ui`. Только для таких шагов включается фаза дизайна и UI-ревью (роли `catalog-designer` + `catalog-ui-reviewer`). Для остальных шагов поток прежний (`generator ↔ reviewer`), эти роли не запускаются.

## Подготовка (один раз перед циклом шагов)
1. Прочитай STATE, если файл существует; иначе создай по схеме с `schema_version: 1`.
2. Проверь git: `git status` — рабочее дерево должно быть чистым. Если грязное — стоп, сообщи пользователю, не «чини молча».
3. Проверь текущую ветку/HEAD против `STATE.branch` (если задан). Несовпадение → стоп с диагностикой, не переключай ветку сам без подтверждения.
4. Если ветки `BRANCH` ещё нет локально — `git fetch origin`, затем `git checkout <BRANCH>` (если есть в origin) или `git checkout -b <BRANCH>` от `main`.
5. PR: `gh pr list --head <BRANCH> --state open --json number,url`. Если есть — запомни `pr_number`/`pr_url` в STATE. Если нет и это первый шаг с изменениями — создашь после первого успешного шага.

## Контракт одного шага (СТРОГО)
Для каждого STEP по очереди:

1. `base_sha = git rev-parse HEAD`. `STATE.steps[STEP] = { status: "running", attempt: 0, base_sha, updated: <ISO> }`. Запиши STATE на диск (атомарно — временный файл + rename).
1a. **Фаза дизайна (только для UI-шага, один раз до цикла).** Если STEP помечен `- **Тип шага:** ui` и у шага ещё нет `design_path` со `Статус дизайна: Ready`:
   - `DESIGN = docs/plan/night-shift/<STEP без .md>.design.md`.
   - Запусти **новый** Task → subagent_type `catalog-designer` с промптом: `PLAN=<путь к STEP>, DESIGN=<DESIGN>`. Сохрани `STATE.steps[STEP].designer_agent_id` и `STATE.steps[STEP].design_path = <DESIGN>`. Запиши STATE.
   - Для не-UI шага DESIGN не создаётся, эта фаза пропускается.
2. `ISSUES = "нет"`. Для `CYCLE = 1..CYCLES_MAX`:
   a. Если `CYCLE == 1` или у шага ещё нет `generator_agent_id` — запусти **новый** Task → subagent_type `catalog-generator` с промптом: `PLAN=<путь к STEP>, CYCLE=<CYCLE>, ISSUES=<ISSUES>` (для UI-шага добавь `DESIGN=<design_path>`). Сохрани возвращённый agent id в `STATE.steps[STEP].generator_agent_id`.
      Иначе (цикл 2+, тот же шаг) — **resume** того же agent id с промптом: `CYCLE=<CYCLE>, ISSUES=<ISSUES>. Адресуй каждый пункт.`
   b. Запусти **свежий** (без resume) Task → subagent_type `catalog-reviewer` с промптом: `PLAN=<путь к STEP>, DIFF_BASE=<base_sha>, CYCLE=<CYCLE>, PRIOR_ISSUES=<ISSUES>`. Распарси блок `===REVIEW===`: `code_verdict`, `code_issues`.
   b2. **UI-ревью (только для UI-шага):** запусти **свежий** (без resume) Task → subagent_type `catalog-ui-reviewer` с промптом: `PLAN=<путь к STEP>, DESIGN=<design_path>, DIFF_BASE=<base_sha>, CYCLE=<CYCLE>, PRIOR_ISSUES=<ui-часть ISSUES>`. Распарси `===REVIEW===`: `ui_verdict`, `ui_issues`. Для не-UI шага `ui_verdict = APPROVED`, `ui_issues = []`.
   c. **Слияние вердиктов:** `VERDICT = APPROVED` только если И `code_verdict == APPROVED`, И `ui_verdict == APPROVED`. `ISSUES` = объединение: пункты reviewer с префиксом `[CODE]`, пункты ui-reviewer с префиксом `[UI]`.
   d. Обнови `STATE.steps[STEP] = { attempt: CYCLE, verdict, code_verdict, ui_verdict, findings: ISSUES, updated: <ISO> }`. Запиши STATE.
   e. `VERDICT == APPROVED` → перейди к шагу 3 (финализация). Иначе `ISSUES = <новые findings>`, следующий CYCLE.
3. **Финализация при APPROVED:**
   - Прогони финальные проверки по всему коду (backend: `ruff check .`, `pytest` из `backend/`; frontend: `pnpm run build`, `pnpm run lint`, `pnpm run typecheck` из `frontend/`). Если что-то красное — это твоя ошибка контроля, не commit; разберись (обычно значит reviewer одобрил зря — считай CHANGES_REQUESTED и продолжи циклы, если лимит не исчерпан).
   - `git add` только файлы, относящиеся к шагу. `git commit -m "<CATALOG-NN>: <краткое summary>"`.
   - `git push` (первый пуш ветки — `git push -u origin <BRANCH>`).
   - Если PR ещё не существует — `gh pr create --base main --head <BRANCH> --title "Pipeline: <slug>" --body "Шаги — см. .cursor/state/night-shift.json (не в git)."`. Иначе PR обновится пушем автоматически — **не вызывай `gh pr review` на каждый цикл**.
   - `STATE.steps[STEP] = { status: "done", verdict: "APPROVED", commit: <sha>, updated: <ISO> }`. Запиши STATE.
   - Опционально (не обязательно на каждый шаг): один короткий `gh pr comment` с итогом шага.
4. **Лимит циклов без APPROVED:**
   - `STATE.steps[STEP].status = "failed"`, `failure_reason = <краткое summary ISSUES>`. Запиши STATE.
   - Создай/допиши `.cursor/steps-results/<STEP без .md>.md` с сводкой ISSUES и статусом проверок (пишешь **ты**, не reviewer).
   - Не падай, не останавливай весь прогон без явной fail-policy пользователя. Смотри поле **Очередь** в плане: если у следующих pending-шагов в `blocked_by` есть упавший тикет — стоп этой цепочки, сообщи. Независимые шаги (в **Очередь** стоит «независимый») можно продолжать.

## Жёсткие правила
- Git/GitHub-операции выполняешь **только ты**, никогда не через подагентов.
- Не создавай вложенных подагентов глубже `parent → generator/reviewer` (запрещено).
- reviewer и ui-reviewer вызываются **заново** каждый цикл (без resume); generator — **резюмируется** тот же instance между циклами одного шага. designer запускается **один раз** до цикла на UI-шаге (resume только если нужно перегенерировать дизайн — по умолчанию не требуется).
- APPROVED шага возможен только при APPROVED от обоих ревьюеров (для не-UI шага ui-reviewer не запускается и считается APPROVED).
- STATE пишешь атомарно после каждого перехода. Никогда не коммить `.cursor/state/night-shift.json`.
- Не мерджи PR сам — финальное решение за Bugbot/человеком.
- Не постишь `gh pr review`/`gh pr comment` на каждый цикл — шум в PR недопустим.
- **Модели подагентов не выбираешь и не пишешь в STATE.** При `Task` **не передавай** параметр `model` — модель роли берётся из frontmatter `.cursor/agents/catalog-*.md` (переключается скилом `/pipeline-model-mode`). В STATE не заводи поля вроде `requested_models` / `actual_models`.

## Схема `.cursor/state/night-shift.json`
```json
{
  "schema_version": 1,
  "branch": "pipeline/night-shift-2",
  "pr_number": null,
  "pr_url": null,
  "steps": {
    "00-CATALOG-17-skill-editing.md": {
      "status": "pending",
      "kind": "code",
      "attempt": 0,
      "base_sha": null,
      "generator_agent_id": null,
      "designer_agent_id": null,
      "design_path": null,
      "verdict": null,
      "code_verdict": null,
      "ui_verdict": null,
      "findings": [],
      "tests": null,
      "commit": null,
      "updated": null,
      "failure_reason": null
    }
  }
}
```
Статусы шага: `pending | running | done | failed | investigated_no_repro`.
