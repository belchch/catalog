---
name: catalog-pipeline
description: Автономный ночной pipeline по шагам docs/plan/night-shift/CATALOG-*.md. Владеет общей веткой pipeline, PR, файлом состояния .cursor/state/night-shift.json и циклом generator↔reviewer (до 5 циклов на шаг). Использовать явно через /catalog-pipeline, когда нужно прогнать один или несколько шагов ночного пайплайна.
disable-model-invocation: true
---

# Skill: catalog-pipeline

Ты — **parent-оркестратор** одного или нескольких шагов ночного pipeline. Ты (а не подагенты) владеешь git, PR и файлом состояния. Подагенты `catalog-generator` и `catalog-reviewer` НИКОГДА не коммитят и не пушат — это твоя работа.

Модель парента выбирается пользователем в UI/CLI до запуска (ориентир: Grok 4.5). Эта инструкция работает независимо от того, какая модель её выполняет.

## Параметры запуска
- **STEPS** — список шагов для прогона. Если пользователь не указал явно — возьми из `.cursor/state/night-shift.json.steps`, отфильтровав `status == "pending"`, в порядке очереди из плана 2 (`docs/plan/night-shift/`): по номеру CATALOG-NN, если не указано иное.
- **BRANCH** — общая ветка pipeline. Если в state есть `branch` — используй её. Иначе спроси/уточни у пользователя (не угадывай имя ветки молча).
- **CYCLES_MAX = 5** (на шаг).
- **STATE** = `.cursor/state/night-shift.json` (см. схему ниже). Файл в `.gitignore`, никогда не коммитить.

## Подготовка (один раз перед циклом шагов)
1. Прочитай STATE, если файл существует; иначе создай по схеме с `schema_version: 1`.
2. Проверь git: `git status` — рабочее дерево должно быть чистым. Если грязное — стоп, сообщи пользователю, не «чини молча».
3. Проверь текущую ветку/HEAD против `STATE.branch` (если задан). Несовпадение → стоп с диагностикой, не переключай ветку сам без подтверждения.
4. Если ветки `BRANCH` ещё нет локально — `git fetch origin`, затем `git checkout <BRANCH>` (если есть в origin) или `git checkout -b <BRANCH>` от `main`.
5. PR: `gh pr list --head <BRANCH> --state open --json number,url`. Если есть — запомни `pr_number`/`pr_url` в STATE. Если нет и это первый шаг с изменениями — создашь после первого успешного шага.

## Контракт одного шага (СТРОГО)
Для каждого STEP по очереди:

1. `base_sha = git rev-parse HEAD`. `STATE.steps[STEP] = { status: "running", attempt: 0, base_sha, updated: <ISO> }`. Запиши STATE на диск (атомарно — временный файл + rename).
2. `ISSUES = "нет"`. Для `CYCLE = 1..CYCLES_MAX`:
   a. Если `CYCLE == 1` или у шага ещё нет `generator_agent_id` — запусти **новый** Task → subagent_type `catalog-generator` с промптом: `PLAN=<путь к STEP>, CYCLE=<CYCLE>, ISSUES=<ISSUES>`. Сохрани возвращённый agent id в `STATE.steps[STEP].generator_agent_id`.
      Иначе (цикл 2+, тот же шаг) — **resume** того же agent id с промптом: `CYCLE=<CYCLE>, ISSUES=<ISSUES>. Адресуй каждый пункт.`
   b. Запусти **свежий** (без resume) Task → subagent_type `catalog-reviewer` с промптом: `PLAN=<путь к STEP>, DIFF_BASE=<base_sha>, CYCLE=<CYCLE>, PRIOR_ISSUES=<ISSUES>`.
   c. Распарси блок `===REVIEW===` из ответа reviewer'а: `VERDICT`, `ISSUES`.
   d. Обнови `STATE.steps[STEP] = { attempt: CYCLE, verdict, findings: ISSUES, updated: <ISO> }`. Запиши STATE.
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
   - Не падай, не останавливай весь прогон без явной fail-policy пользователя — переходи к следующему STEP, если шаги независимы (см. план 2, раздел «Fail policy»). Если шаг блокирующий для следующих — стоп очереди, сообщи.

## Жёсткие правила
- Git/GitHub-операции выполняешь **только ты**, никогда не через подагентов.
- Не создавай вложенных подагентов глубже `parent → generator/reviewer` (запрещено).
- reviewer вызывается **заново** каждый цикл (без resume); generator — **резюмируется** тот же instance между циклами одного шага.
- STATE пишешь атомарно после каждого перехода. Никогда не коммить `.cursor/state/night-shift.json`.
- Не мерджи PR сам — финальное решение за Bugbot/человеком.
- Не постишь `gh pr review`/`gh pr comment` на каждый цикл — шум в PR недопустим.

## Схема `.cursor/state/night-shift.json`
```json
{
  "schema_version": 1,
  "branch": "pipeline/night-shift-2",
  "pr_number": null,
  "pr_url": null,
  "steps": {
    "CATALOG-17-skill-editing.md": {
      "status": "pending",
      "attempt": 0,
      "base_sha": null,
      "generator_agent_id": null,
      "requested_models": { "generator": "claude-sonnet-5[effort=high]", "reviewer": "claude-opus-4-8[effort=high]" },
      "actual_models": {},
      "verdict": null,
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
