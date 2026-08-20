#!/bin/bash
# pipeline-git-guard.sh — PreToolUse-хук: запрещает подагентам pipeline
# `catalog-pipeline` менять git-состояние (ветка/индекс/коммиты/PR).
#
# Порт .cursor/hooks/pipeline-git-guard.sh. В Cursor «мы внутри подагента»
# определялось лок-файлом, который ставил/снимал subagentStart/subagentStop.
# В Claude Code это не нужно: PreToolUse-payload сам содержит поля
# `agent_type` и `agent_id` (проверено на claude 2.1.228 — у вызова из main-
# треда оба поля отсутствуют, у вызова изнутри подагента agent_type равен
# имени агента из frontmatter). Лок-файлов и состояния хук не создаёт.
#
# Контракт: stdin — JSON PreToolUse; stdout — либо ничего (решение отдаём
# обычной системе прав), либо JSON с permissionDecision=deny; exit всегда 0.
# Сознательно НЕ печатаем permissionDecision=allow: «allow» из хука обходит
# штатные проверки прав, а нам нужно только запрещать, не разрешать лишнее.
#
# Ограничения — см. .claude/hooks/README.md.

set -uo pipefail

# ---------------------------------------------------------------- настройки

# Режим:
#   guarded-agents — запрещаем только перечисленным в GUARDED_AGENTS (по
#                    умолчанию; поведение 1:1 с Cursor-версией);
#   all-subagents  — запрещаем любому подагенту, кроме ALLOWED_AGENTS.
GUARD_MODE="${PIPELINE_GIT_GUARD_MODE:-guarded-agents}"

# Подагенты pipeline, которым git-мутации запрещены.
GUARDED_AGENTS="catalog-generator catalog-reviewer catalog-designer catalog-ui-reviewer"

# Подагенты, которым git-мутации разрешены (владелец git в pipeline).
ALLOWED_AGENTS="catalog-steward"

# git-подкоманды, меняющие ветку/HEAD/индекс/историю/удалёнку.
GIT_SUBCOMMANDS='commit|push|checkout|switch|reset|merge|rebase|cherry-pick|revert|worktree|remote|stash|clean|update-ref|symbolic-ref|filter-branch'

# ------------------------------------------------------------------- helpers

deny() {
  # $1 — текст причины (уходит модели как blockingError и показывается юзеру)
  jq -n --arg r "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

allow() { exit 0; }

in_list() { # $1 — иголка, $2 — список через пробел
  local w
  for w in $2; do [[ "$w" == "$1" ]] && return 0; done
  return 1
}

INPUT=$(cat)

# jq обязателен. Если его нет — не делаем вид, что защита работает:
# закрываем git/gh-мутации всем (включая steward). Отказ шумный и чинится
# установкой jq, тихой дыры не остаётся.
if ! command -v jq >/dev/null 2>&1; then
  if printf '%s' "$INPUT" | grep -Eq '(git|gh)[[:space:]]'; then
    printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"pipeline-git-guard: в PATH нет jq, хук не может разобрать payload и не пропускает git/gh-команды. Установите jq (brew install jq)."}}'
  fi
  exit 0
fi

AGENT_TYPE=$(printf '%s' "$INPUT" | jq -r '.agent_type // ""')
TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // ""')

# Пустой agent_type = вызов из main-треда (оркестратор) — не наше дело.
[[ -z "$AGENT_TYPE" ]] && allow

case "$GUARD_MODE" in
  all-subagents)  in_list "$AGENT_TYPE" "$ALLOWED_AGENTS" && allow ;;
  *)              in_list "$AGENT_TYPE" "$GUARDED_AGENTS" || allow ;;
esac

WHO="Подагент '$AGENT_TYPE'"
OWNER="git/GitHub в pipeline catalog-pipeline владеет только catalog-steward (задача finalize)."
SRC="Правило: .claude/hooks/pipeline-git-guard.sh."

# --------------------------------------------------------- запись в .git/*

if [[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" || "$TOOL_NAME" == "NotebookEdit" ]]; then
  FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // .tool_input.notebook_path // ""')
  if [[ "$FILE_PATH" == *"/.git/"* || "$FILE_PATH" == ".git/"* || "$FILE_PATH" == *"/.git" || "$FILE_PATH" == ".git" ]]; then
    deny "$WHO не может писать внутрь .git ($FILE_PATH). $OWNER $SRC"
  fi
  allow
fi

# ------------------------------------------------------------- Bash-команды

[[ "$TOOL_NAME" != "Bash" ]] && allow

COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""')
[[ -z "$COMMAND" ]] && allow

# `git [глобальные опции] <подкоманда>`: между `git` и подкомандой допускаем
# любое число опций (`-C dir`, `-c k=v`, `--no-pager`, `--git-dir=...`).
# Левая граница пускает `/usr/bin/git commit` и `cd x && git commit`,
# но не `mygit commit` (другой бинарник).
WORD_START='(^|[^[:alnum:]_-])'
GIT_PREFIX="${WORD_START}git([[:space:]]+(-[cC][[:space:]]+[^[:space:]]+|-[^[:space:]]+))*[[:space:]]+"

if printf '%s' "$COMMAND" | grep -Eq "${GIT_PREFIX}(${GIT_SUBCOMMANDS})([[:space:]]|$)"; then
  deny "$WHO не имеет права менять git-состояние: '$COMMAND'. Разрешены только читающие git-команды (status/diff/log/show/rev-parse) и \`git add\` для самопроверки диффа. $OWNER Верни результат работы без git-операций. $SRC"
fi

# git branch -d/-D/-m/-M/--delete/--move/--force и git tag -d/--delete/-f
if printf '%s' "$COMMAND" | grep -Eq "${GIT_PREFIX}branch[[:space:]]+(-[dDmMf]|--delete|--move|--force)"; then
  deny "$WHO не может удалять/переименовывать ветки: '$COMMAND'. $OWNER $SRC"
fi
if printf '%s' "$COMMAND" | grep -Eq "${GIT_PREFIX}tag[[:space:]]+(-[dfams]|--delete|--force)"; then
  deny "$WHO не может создавать/удалять теги: '$COMMAND'. $OWNER $SRC"
fi

# gh: всё, что создаёт или меняет объекты на GitHub. Читающее
# (gh pr view/diff/list/checks, gh issue view/list, gh run view) — разрешено.
GH_PREFIX="${WORD_START}gh[[:space:]]+"
if printf '%s' "$COMMAND" | grep -Eq "${GH_PREFIX}pr[[:space:]]+(create|merge|review|close|reopen|edit|comment|ready|lock|unlock)([[:space:]]|$)"; then
  deny "$WHO не работает с PR: '$COMMAND'. PR создаёт и обновляет только catalog-steward, ревью-вердикт возвращай структурой, а не в GitHub. $SRC"
fi
if printf '%s' "$COMMAND" | grep -Eq "${GH_PREFIX}(issue[[:space:]]+(create|close|reopen|edit|comment|delete)|release[[:space:]]+(create|delete|edit|upload)|repo[[:space:]]+(create|delete|edit|fork|sync)|workflow[[:space:]]+run|secret[[:space:]]|variable[[:space:]]+set)([[:space:]]|$)"; then
  deny "$WHO не имеет права менять состояние на GitHub: '$COMMAND'. $OWNER $SRC"
fi
if printf '%s' "$COMMAND" | grep -Eq "${GH_PREFIX}api[[:space:]].*(-X|--method)[[:space:]]+(POST|PATCH|PUT|DELETE)"; then
  deny "$WHO не имеет права на пишущие вызовы GitHub API: '$COMMAND'. $OWNER $SRC"
fi

allow
