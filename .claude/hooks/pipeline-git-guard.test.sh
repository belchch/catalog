#!/bin/bash
# Самотест pipeline-git-guard.sh: кормим хук синтетическими PreToolUse-payload'ами
# и проверяем решение. Запуск: bash .claude/hooks/pipeline-git-guard.test.sh
set -uo pipefail

GUARD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/pipeline-git-guard.sh"
PASS=0; FAIL=0

# decide <agent_type> <tool_name> <command|file_path> -> "deny" | "allow"
decide() {
  local agent="$1" tool="$2" arg="$3" payload out
  if [[ "$tool" == "Bash" ]]; then
    payload=$(jq -n --arg a "$agent" --arg c "$arg" \
      '{hook_event_name:"PreToolUse",tool_name:"Bash",agent_type:$a,agent_id:"a1",tool_input:{command:$c}}')
  else
    payload=$(jq -n --arg a "$agent" --arg t "$tool" --arg f "$arg" \
      '{hook_event_name:"PreToolUse",tool_name:$t,agent_type:$a,agent_id:"a1",tool_input:{file_path:$f}}')
  fi
  out=$(printf '%s' "$payload" | "$GUARD")
  if [[ -z "$out" ]]; then echo allow
  else printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision'; fi
}

check() { # <expected> <agent> <tool> <arg>
  local want="$1" got
  got=$(decide "$2" "$3" "$4")
  if [[ "$got" == "$want" ]]; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
    printf 'FAIL  want=%-5s got=%-5s agent=%-20s tool=%-12s %s\n' "$want" "$got" "$2" "$3" "$4"
  fi
}

# --- подагенты pipeline: git-мутации запрещены -------------------------------
check deny  catalog-generator   Bash 'git commit -m "CATALOG-1: x"'
check deny  catalog-generator   Bash 'cd backend && git push -u origin feat'
check deny  catalog-generator   Bash 'git -C /repo commit -m x'
check deny  catalog-generator   Bash 'git --no-pager checkout main'
check deny  catalog-generator   Bash 'git checkout -b feature/x'
check deny  catalog-generator   Bash 'git reset --hard HEAD~1'
check deny  catalog-generator   Bash 'git rebase main'
check deny  catalog-generator   Bash 'git merge origin/main'
check deny  catalog-generator   Bash 'git switch main'
check deny  catalog-generator   Bash 'git stash'
check deny  catalog-generator   Bash 'git clean -fd'
check deny  catalog-generator   Bash 'git remote add upstream git@github.com:x/y.git'
check deny  catalog-generator   Bash 'git branch -D feature/x'
check deny  catalog-generator   Bash 'git tag -d v1'
check deny  catalog-designer    Bash 'git checkout -b design/x'
check deny  catalog-reviewer    Bash 'git commit --amend --no-edit'
check deny  catalog-ui-reviewer Bash 'git push --force'

check deny  catalog-generator   Bash '/usr/bin/git commit -m x'
check deny  catalog-generator   Bash 'PAGER=cat git push'
check allow catalog-generator   Bash 'mygit commit -m x'
check allow catalog-generator   Bash 'pnpm run lint && pnpm run typecheck'

# --- читающие git-команды разрешены -----------------------------------------
check allow catalog-generator   Bash 'git status --short'
check allow catalog-generator   Bash 'git add -A'
check allow catalog-generator   Bash 'git diff HEAD'
check allow catalog-reviewer    Bash 'git diff abc123...HEAD -- frontend/'
check allow catalog-generator   Bash 'git log --oneline -5'
check allow catalog-generator   Bash 'git rev-parse HEAD'
check allow catalog-generator   Bash 'git branch --show-current'
check allow catalog-generator   Bash 'git show --stat HEAD'
check allow catalog-generator   Bash 'cd backend && ruff check . && pytest -q'

# --- gh ----------------------------------------------------------------------
check deny  catalog-reviewer    Bash 'gh pr create --base main --head feat'
check deny  catalog-reviewer    Bash 'gh pr comment 12 --body "nope"'
check deny  catalog-generator   Bash 'gh pr merge 12 --squash'
check deny  catalog-generator   Bash 'gh api repos/o/r/pulls -X POST -f title=x'
check allow catalog-reviewer    Bash 'gh pr view 12 --json state'
check allow catalog-reviewer    Bash 'gh pr diff 12'
check allow catalog-reviewer    Bash 'gh pr list --head feat --state open'

# --- запись внутрь .git ------------------------------------------------------
check deny  catalog-generator   Write '/repo/.git/HEAD'
check deny  catalog-generator   Edit  '/repo/.git/config'
check allow catalog-generator   Write '/repo/backend/catalog/x.py'
check allow catalog-generator   Edit  '/repo/frontend/src/.gitignore'

# --- steward и main-тред не ограничены ---------------------------------------
check allow catalog-steward     Bash 'git commit -m "CATALOG-1: x"'
check allow catalog-steward     Bash 'git push -u origin feat'
check allow catalog-steward     Bash 'gh pr create --base main --head feat'
check allow ""                  Bash 'git commit -m "orchestrator"'
check allow general-purpose     Bash 'git commit -m "другой подагент, режим guarded-agents"'

# --- режим all-subagents -----------------------------------------------------
export PIPELINE_GIT_GUARD_MODE=all-subagents
check deny  general-purpose   Bash 'git commit -m x'
check deny  Explore           Bash 'git push'
check allow catalog-steward   Bash 'git commit -m x'
check allow ""                Bash 'git commit -m x'
check allow general-purpose   Bash 'git status'
unset PIPELINE_GIT_GUARD_MODE

printf 'ИТОГО: pass=%d fail=%d\n' "$PASS" "$FAIL"
[[ $FAIL -eq 0 ]]
