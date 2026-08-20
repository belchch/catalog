# `.claude/hooks` — защита git от подагентов pipeline

## Зачем

В pipeline `catalog-pipeline` git-состоянием (ветка, коммиты, push, PR) владеет
**только** `catalog-steward`. Генератор, ревьюеры и дизайнер имеют доступ к
`Bash`, то есть технически способны сделать `git commit`/`git checkout` и
испортить состояние шага. Хук `pipeline-git-guard.sh` делает этот запрет
физическим, а не только текстовым в промпте агента.

Это порт `.cursor/hooks/pipeline-git-guard.sh` + `.cursor/hooks.json`.

## Как это работает в Claude Code

Регистрация — `.claude/settings.json`, событие `PreToolUse` с матчерами
`Bash` и `Write|Edit|NotebookEdit`.

Ключевое отличие от Cursor: **лок-файл не нужен**. В Cursor «мы внутри
подагента» определялось счётчиком в `.cursor/state/.pipeline-subagent-lock`,
который ставил `subagentStart` и снимал `subagentStop`. В Claude Code
PreToolUse-payload сам содержит поля `agent_id` и `agent_type`, поэтому хук
без состояния знает, кто именно вызывает команду.

Проверено эмпирически на `claude 2.1.228` (пробный хук, логирующий payload):

| Откуда вызов | `agent_id` | `agent_type` | `session_id` |
|---|---|---|---|
| main-тред (оркестратор) | отсутствует | отсутствует | `d1e10c8e-…` |
| подагент через Agent-тул | `a73fa3798bb7e07c7` | `Explore` | `d1e10c8e-…` (**тот же**) |
| подагент через `Workflow`/`agent({agentType})` | `a651fef9b7758898d` | `probe-agent` | тот же |

То есть `session_id` подагента **не** отличается от родительского — различать
роли можно только по `agent_type`/`agent_id`. `SubagentStart` в Claude Code
существует (полный список событий включает `SubagentStart` и `SubagentStop`,
матчер у обоих — тип агента), но для этой задачи он не нужен.

Формат ответа хука:

* запрет — stdout `{"hookSpecificOutput":{"hookEventName":"PreToolUse",
  "permissionDecision":"deny","permissionDecisionReason":"…"}}`, exit 0;
  `permissionDecisionReason` уходит модели как blocking error;
* разрешение — **пустой stdout**, exit 0. Осознанно не печатаем
  `permissionDecision:"allow"`: «allow» из хука обходит штатную систему прав
  Claude Code для этого вызова, а задача хука — только запрещать.
  (Cursor-версия печатала `{"permission":"allow"}`, там это было безопасно.)

## Что именно запрещено

Только для агентов из списка `GUARDED_AGENTS`
(`catalog-generator`, `catalog-reviewer`, `catalog-designer`,
`catalog-ui-reviewer`):

* `git <глоб. опции> {commit|push|checkout|switch|reset|merge|rebase|
  cherry-pick|revert|worktree|remote|stash|clean|update-ref|symbolic-ref|
  filter-branch}` — в том числе `git -C dir commit`, `git --no-pager push`,
  `cd backend && git commit`;
* `git branch -d/-D/-m/-M/--delete/--move/--force`, `git tag -d/-f/-a/-s/-m`;
* `gh pr create|merge|review|close|reopen|edit|comment|ready|lock|unlock`;
* `gh issue create|close|reopen|edit|comment|delete`, `gh release …`,
  `gh repo create|delete|edit|fork|sync`, `gh workflow run`, `gh secret`,
  `gh variable set`;
* `gh api … -X|--method POST|PATCH|PUT|DELETE`;
* запись через `Write`/`Edit`/`NotebookEdit` внутрь каталога `.git/`.

Разрешено (и покрыто тестами): `git status/diff/log/show/rev-parse`,
`git branch --show-current`, `git add`, `gh pr view/diff/list`.

`catalog-steward` и main-тред оркестратора не ограничены ничем.

## Режимы

Переменная окружения `PIPELINE_GIT_GUARD_MODE`:

* `guarded-agents` (по умолчанию) — запрет действует только на агентов из
  `GUARDED_AGENTS`; поведение 1:1 с Cursor-версией;
* `all-subagents` — запрет действует на **любого** подагента, кроме
  `ALLOWED_AGENTS` (`catalog-steward`). Строже, но заденет и обычные
  `general-purpose`/`Explore`-подагенты в этом проекте.

## Чего защита НЕ покрывает — честный список

1. **Это не песочница, а сопоставление строки команды с регэкспом.** Обходится
   косвенным запуском: `sh -c 'git commit …'`, `bash script.sh` с git внутри,
   `python -c "subprocess.run(['git','commit'])"`, `eval "$(printf …)"`, alias,
   свой враппер с именем не `git`. Ровно та же дыра была в Cursor-версии.
   Гарантия здесь — «не сделать случайно», а не «не сделать намеренно».
2. **Ложные срабатывания на текст.** Команда, где строка `git commit`
   встречается как данные (`grep -r 'git commit' .`, `echo "git push"`), будет
   запрещена. Тоже унаследовано от Cursor-версии.
3. **Покрыты только инструменты `Bash`, `Write`, `Edit`, `NotebookEdit`.**
   MCP-инструменты, умеющие git/GitHub, не покрыты — матчер пришлось бы
   расширять под конкретные имена таких инструментов.
4. **Хуки читаются при старте сессии.** Правку `settings.json` или скрипта
   уже запущенная сессия Claude Code не подхватит — нужен перезапуск.
5. **Хуки не выполняются в недоверенном каталоге и в safe mode**
   (`--bare` пропускает хуки целиком). Если проект не помечен доверенным,
   защиты нет.
6. **Список агентов захардкожен.** Новый подагент pipeline с доступом к `Bash`
   надо руками добавить в `GUARDED_AGENTS` (или включить режим
   `all-subagents`).
7. **Нет `jq` — нет разбора payload.** В этом случае хук намеренно
   fail-closed: запрещает любые команды, содержащие `git `/`gh `, всем ролям,
   включая steward. Отказ шумный и чинится `brew install jq`; тихой дыры не
   остаётся.
8. **Альтернатива через `permissions.deny` в `settings.json` не подходит.**
   Правила вида `Bash(git commit:*)` применяются к сессии целиком и не умеют
   различать роль вызывающего, поэтому заблокировали бы и `catalog-steward`,
   которому commit/push/`gh pr create` нужны по задаче `finalize`.
   Per-agent-скоупа у `permissions` нет; во frontmatter агента есть
   `tools`, `disallowedTools`, `permissionMode`, `hooks` — но `disallowedTools`
   умеет убирать только инструмент целиком (`Bash`), а он генератору нужен
   для `ruff`/`pytest`/`pnpm`. Поэтому выбран PreToolUse-хук.

## Состояние на диске

Хук **stateless**: не создаёт ни лок-файлов, ни логов. Никаких новых
gitignore-правил не требуется (`.claude/state/` и `.claude/steps-results/`
уже игнорируются и используются только steward'ом).

## Тесты

```bash
bash .claude/hooks/pipeline-git-guard.test.sh
```

51 кейс: запрет/разрешение по ролям, глобальные опции git, составные
команды, границы слова (`/usr/bin/git commit` — запрет, `mygit commit` — нет),
`gh`, запись в `.git/`, оба режима. Плюс скрипты проходят `bash -n`.
