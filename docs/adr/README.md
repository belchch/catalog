# Architecture Decision Records

Решения по архитектуре MVP ИИ-агента «Каталог». Каждая запись: Context → Decision → Consequences → Alternatives considered.

## Index

| #  | Решение | Статус |
|----|---------|--------|
| [0001](0001-agent-loop-execution-engine.md) | Один function-calling агент-луп как движок исполнения | Accepted |
| [0002](0002-skill-as-frozen-config.md) | Скилл = замороженный конфиг агента | Accepted |
| [0003](0003-code-via-tool-layer.md) | Code-возможность — базовая, через слой инструментов | Accepted |
| [0004](0004-build-at-approval-lifecycle.md) | Скилл строится в момент согласия (без дистилляции) | Accepted |
| [0005](0005-storage-split-git-deferred.md) | ФС для контента, SQLite для системных данных; git отложен | Accepted |
| [0006](0006-results-are-documents.md) | Результаты скилла — полноправные Documents | Accepted |
| [0007](0007-verify-deterministic-registry.md) | verify = детерминированный реестр проверок + retry | Accepted |
| [0008](0008-fts-as-system-skill.md) | FTS — системный скилл, после первого среза | Accepted |
| [0009](0009-openrouter-provider.md) | LLM через OpenRouter (selector + pin + streaming) | Accepted |
| [0010](0010-first-slice-scope.md) | Скоуп первого среза и non-goals | Accepted |
| [0011](0011-frontend-stack-tailwind.md) | Фронтенд-стек: React (Vite) + TypeScript + Tailwind | Accepted |
| [0012](0012-data-root-and-git-repos.md) | Data-root вне репо исходников + два app-owned git-репозитория | Accepted |

## Связанные материалы
- Исходные транскрипции: `../pre-design/` (`opus-chat.json` — фундаментальные решения; `fable-review.json` — критика и уточнения).
- Реестр проверок: `../verification-checks.md`.
- План первого среза: `~/.local/share/kilo/plans/1783886041469-first-slice-skill-loop.md`.

## Жизненный цикл ADR
Статусы: `Proposed` → `Accepted` → `Deprecated` / `Superseded`. Новое значимое решение → новый пронумерованный файл + строка в индексе. Решения не удаляются; при смене — помечаем `Superseded by ADR-00XX`.
