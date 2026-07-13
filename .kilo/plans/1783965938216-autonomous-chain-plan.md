# План: Автономная работа + цепочка генератор↔ревьюер через GitHub PR

Цель: план составляю локально (Plan-режим). По `/chain` агент автономно, без вопросов, прогоняет циклы генератор↔ревьюер через GitHub PR (до 3), останавливаясь по APPROVED.

## Решения (утверждено)
1. **Автоапрув:** `"*": "allow"` (всё incl. будущие MCP — catch-all покрывает `{server}_{tool}`). Guard: `doom_loop: "ask"`. Защита `.env` встроенная.
2. **Вопросы:** только в Plan-режиме. `code`/`generator`/`reviewer` → `permission.question: "deny"` (жёстко). Plan-режим не трогаем.
3. **GitHub:** локальный `gh` CLI (авторизован `belchch`, scope `repo`, remote `origin`, база `master`).
4. **Цепочка:** команда `/chain <план> [циклы]`, гонит `code`-агент, внутри Task→`generator`/`reviewer`.
5. **APPROVED:** PR оставить открытым — мердж за человеком.
6. **Не сошлось за 3 цикла:** PR оставить открытым + итоговый коммент.
7. **Модели:** generator/reviewer/оркестратор — все glm-5.2 (единственный провайдер Z.ai). Риск self-confirmation смягчается разными промптами (генерация vs критика) и температурой 0. Архитектура позволяет переключить reviewer на другую модель одной строкой `model:` в frontmatter, когда появится второй провайдер.

## Поток
```
Plan (локально, Plan-режим) → файл плана
   │  /chain <plan>
   ▼
[code-агент: оркестратор, держит BRANCH + PR_URL между циклами]
   │
   ├─ cycle 1: generator → impl + ruff/pytest/pnpm green → branch от master → commit → push → gh pr create (base master) → PR_URL
   │           reviewer → gh pr diff + проверки → gh pr review (--request-changes|--approve) → VERDICT
   │           APPROVED? → стоп (PR человеку)
   │
   ├─ cycle 2: generator → правки по ISSUES → commit → push в ту же ветку (PR авто-обновится) → ...
   │           reviewer → повторный review → VERDICT
   │           APPROVED? → стоп
   │
   └─ cycle 3 (аналогично). Если нет APPROVED → gh pr comment (саммари) + PR открыт.
```

## Механизм (почему работает)
- Top-level `"*": "allow"` — catch-all (last-match-wins); `doom_loop: "ask"` ставим ПОСЛЕ, иначе останется allow.
- `agent.code` мерджится поверх встроенного (меняем только `permission`) — системный промпт не трогаем; Plan-режим — отдельный агент, не страдает.
- Subagent'ы в `.kilo/agents/` вызываются через Task; `question:deny` + scoped `edit`/`bash` разделяют роли.
- gh — обычный bash, покрывается global allow. Для reviewer bash ограничен read-only + `gh pr *` (чтобы только постить review, не ломать репо).

## Артефакты (4 файла)

### 1. `.kilo/kilo.jsonc` — перезаписать
```jsonc
{
  "$schema": "https://app.kilo.ai/config.json",
  "permission": {
    "*": "allow",
    "doom_loop": "ask"
  },
  "agent": {
    "code": {
      "permission": {
        "question": "deny",
        "doom_loop": "ask"
      }
    }
  }
}
```
Порядок: `"*": "allow"` ПЕРВЫМ, `doom_loop: "ask"` ПОСЛЕ. `.env` защищён по умолчанию.

### 2. `.kilo/agents/generator.md` — создать
```markdown
---
description: Реализует план, доводит проверки до зелёного, коммитит, пушит ветку, открывает PR (цикл 1) или дописывает коммиты (циклы 2+). Из /chain. Никогда не спрашивает.
mode: subagent
steps: 35
temperature: 0
permission:
  question: deny
  doom_loop: ask
---

Ты — **генератор**. Реализуй план и доставь его в виде PR на GitHub.

## Вход (передаёт оркестратор)
- PLAN — путь к плану/шагу.
- BRANCH — имя ветки (например agent/<slug>), база master.
- CYCLE — номер цикла (1 = первый).
- PR_URL — URL/номер PR (с цикла 2; иначе «нет»).
- ISSUES — замечания ревьюера (с цикла 2; иначе «нет»).

## Что делать
1. Прочитай PLAN + README.md, docs/adr/, docs/verification-checks.md.
2. Внеси минимальные изменения по плану/конвенциям. С цикла 2 — адресуй каждое замечание из ISSUES.
3. Добейся зелёного: backend — ruff check ., pytest (из backend/); frontend — pnpm run build/lint/typecheck (из frontend/).
4. Git/GitHub (через gh, remote origin, база master):
   - Цикл 1: проверь gh pr list --head <BRANCH> --state open --json number,url. Если открытый PR есть — используй его. Иначе: git checkout -b <BRANCH> (от master), проиндексируй ТОЛЬКО относящиеся к плану файлы, закоммить, git push -u origin <BRANCH>, gh pr create --base master --head <BRANCH> --title "<из плана>" --body "План: <PLAN>".
   - Циклы 2+: закоммить исправления, git push в ту же ветку (PR обновится сам).
5. Ключи только в .env; не коммить секреты.

## Правила
- НЕ задавай вопросов (права нет) — решения сам.
- Коммитить/пушить/PR — ОБЯЗАТЕЛЬНО (часть потока). PR создаётся один раз.
- Не трогай чужие ветки/PR.

## Вернуть
- Цикл 1: BRANCH, PR_URL(или номер), сводку изменений + статус проверок.
- Циклы 2+: список закрытых замечаний + статус проверок.
```

### 3. `.kilo/agents/reviewer.md` — создать
```markdown
---
description: Ревьюит PR против плана, постит GitHub-ревью (request-changes/approve) и саммари. Код не правит. Никогда не спрашивает.
mode: subagent
steps: 22
temperature: 0
permission:
  question: deny
  doom_loop: ask
  edit:
    "*": deny
    "review/**": allow
  bash:
    "*": deny
    "ruff *": allow
    "pytest *": allow
    "pnpm run build": allow
    "pnpm run lint": allow
    "pnpm run typecheck": allow
    "git status *": allow
    "git diff *": allow
    "git log *": allow
    "gh pr *": allow
    "rg *": allow
    "ls *": allow
---

Ты — **ревьюер**. Дифф берёшь из PR, замечания постишь в PR (GitHub review). Код не правишь.

## Вход
- PLAN — путь к плану/шагу.
- PR — номер/URL PR.
- CYCLE — номер цикла.

## Что делать
1. Прочитай PLAN и критерии приёмки.
2. Дифф PR: gh pr diff <PR> (или git diff master...HEAD).
3. Прогони проверки: ruff check ., pytest, pnpm run build/lint/typecheck.
4. Сравни с планом/ADR: баги, отклонения, нарушения конвенций.
5. Запости ревью в PR одной командой:
   - CHANGES_REQUESTED → gh pr review <PR> --request-changes --body "<саммари по тяжести>"
   - APPROVED → gh pr review <PR> --approve --body "<саммари>"
6. (Опционально) дублируй отчёт в review/<YYYY-MM-DD>-<slug>-cycle<N>.md по шаблону репозитория.

## Вернуть (ровно этот блок в конце)
\`\`\`
===REVIEW===
VERDICT: APPROVED
или
VERDICT: CHANGES_REQUESTED
ISSUES:
- [Critical] path/file.py:LINE — что не так
- [Medium] ...
- [Low] ...
===END===
\`\`\`
VERDICT=APPROVED только если нет Critical/Medium и проверки зелёные.

## Правила
- НЕ задавай вопросов. НЕ правь код/ветку. НЕ мерджи.
- Ревью обязательно постишь в PR через gh pr review.
```
Порядок в `edit`/`bash`: `"*": deny` ПЕРВЫМ, allow ПОСЛЕ (last-match-wins).

### 4. `.kilo/commands/chain.md` — создать
```markdown
---
description: Автономная цепочка генератор↔ревьюер через GitHub PR по плану. Без вопросов.
agent: code
---
Запусти автономную цепочку «генератор → ревьюер» с доставкой через GitHub PR.
ПЛАН (обязательный): $1
ЦИКЛЫ (необязательный, по умолчанию 3): $2
Полная строка: $ARGUMENTS

## Подготовка
1. PLAN = $1 (если пусто — последний файл из .kilo/plans/). N = $2 или 3.
2. SLUG = имя файла плана без leading-таймстампа и .md (напр. step-02-review-fixes).
3. BRANCH = agent/<SLUG>. База = master.
4. Состояние: CYCLE=1, PR_URL=(нет), ISSUES="нет".

## Алгоритм (строго, без вопросов)
Для CYCLE = 1..N:
1. Task → generator: «PLAN=<PLAN>, BRANCH=<BRANCH>, CYCLE=<CYCLE>, PR_URL=<PR_URL или "нет">, ISSUES=<ISSUES>.» Из ответа забери BRANCH и PR_URL (цикл 1), сохрани в контексте.
2. Task → reviewer: «PLAN=<PLAN>, PR=<PR_URL/номер>, CYCLE=<CYCLE>.»
3. Распарси VERDICT и ISSUES из блока ===REVIEW===.
4. VERDICT == APPROVED → СТОП (успех), PR оставить человеку.
5. Иначе ISSUES = распарсенное, следующий цикл.

Если после N нет APPROVED: gh pr comment <PR> --body "Достигнут лимит циклов (N). Незакрытые замечания: <ISSUES>." и оставить PR открытым.

## Итог
Сообщи: финальный вердикт, PR_URL, статус (APPROVED / лимит циклов).

## Жёсткие правила
- НИКАКИХ вопросов — права question нет.
- PR создаётся ОДИН раз (цикл 1); дальше доп-коммиты в ту же ветку.
- Не мерджи PR — решение за человеком.
- Правки кода — только через generator.
- Предполагается чистый working tree на master перед запуском.
```

## Порядок выполнения
1. Перезаписать `.kilo/kilo.jsonc`.
2. Создать `.kilo/agents/generator.md`.
3. Создать `.kilo/agents/reviewer.md`.
4. Создать `.kilo/commands/chain.md`.
5. Перезапустить окно/сессию, чтобы Kilo подхватил агентов и команду (`/agents`, `/chain`).

## Риски и митигация
- **PR — реальный side-effect:** первый прогон создаст настоящий PR на GitHub. Валидировать на тривиальном/документном плане или throwaway-ветке.
- **`gh pr review --request-changes`** может быть ограничен branch protection (требуются назначенные ревьюеры). Для solo-репо ок; при защите веток — добавить бота соовнейблером или смягчить на `gh pr comment`.
- **Грязный working tree на master:** генератор может закоммитить лишнее. Митигация: generator индексирует только относящиеся к плану файлы; запускать /chain из чистого дерева.
- **Перезапуск /chain с тем же планом:** ветка/PR уже есть. Митигация: generator в цикле 1 проверяет `gh pr list --head <BRANCH>` и переиспользует открытый PR.
- **Prompt-driven цикл ненадёжен:** модель может отклониться. Митигация: `question:deny` (не застрянет), `doom_loop:ask` (предохранитель), явный алгоритм, bounded `steps`.
- **reviewer bash scope:** `gh pr *` разрешает и `gh pr merge` — но в промпте reviewer'у явно запрещён мердж; при паранойе сузить до `gh pr diff/view/review/comment`.

## Валидация
- После применения: `/agents` показывает generator/reviewer (subagent); `/chain` доступен; попытка `question` из code-агента блокируется.
- Дымовой прогон на тривиальном плане (напр. док-правка): `/chain .kilo/plans/<trivial>.md 1` → создаётся ветка `agent/...`, открывается PR, ревьюер постит review, вопросов нет.
- Проверка: `gh pr view <num>` (есть review), `git log master..HEAD` (есть коммиты), мержа нет.

## Вне скоупа / следующим шагом
- Авто-мердж PR (сейчас — человеку).
- Инлайн-комментарии по строкам (сейчас PR-level review).
- GitHub MCP-сервер (сейчас gh CLI).
- Авто-очистка веток после мержа.
- Разные модели для ревьюера (текущий провайдер — только Z.ai/glm-5.2; апгрейд при появлении второго провайдера).
- Конкретные MCP-серверы (пока не подключены; catch-all покроет их появление).
