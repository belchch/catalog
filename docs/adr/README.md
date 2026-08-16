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
| [0012](0012-data-root-and-git-repos.md) | Data-root вне репо исходников + два app-owned git-репозитория | Accepted (частично superseded [0016](0016-workspace-as-folder.md)) |
| [0013](0013-multi-provider-and-zai.md) | Multi-provider LLM-фабрика + z.ai провайдер + StreamDelta contract | Accepted |
| [0014](0014-script-skills.md) | Детерминированные script-скилы (kind=script) + sandbox | Accepted |
| [0015](0015-session-artifacts.md) | Артефакты сессии (prompt/script/meta); build = упаковка без LLM | Accepted |
| [0016](0016-workspace-as-folder.md) | Workspace-as-folder: воркспейс = папка; `.catalog/index.db` + глобальный реестр | Accepted |
| [0017](0017-folder-picker-via-backend-browse.md) | Folder-picker — серверный обзор ФС (`/fs/browse` в пределах `APP_FS_ROOT`), не системный диалог | Accepted |
| [0018](0018-pipeline-skills.md) | Pipeline-скилы (kind=pipeline): python + LLM в одном скиле | Accepted |
| [0019](0019-skill-as-session-tool.md) | Пользовательский script-скилл как вызываемый тул сессии | Accepted |
| [0020](0020-llm-judge-custom-checks.md) | LLM-судья — второй тип проверки, не в детерминированном реестре | Accepted |
| [0021](0021-skill-tool-budget.md) | Ограничитель вложенных skill-тулов: глубина 2, бюджет хода, дедлайн | Accepted |
| [0022](0022-pipeline-skill-step.md) | Шаг pipeline типа skill: снапшот на сборке, вложенный apply в рантайме | Accepted |

## Связанные материалы
- Исходные транскрипции: `../pre-design/` (`opus-chat.json` — фундаментальные решения; `fable-review.json` — критика и уточнения).
- Реестр проверок: `../verification-checks.md`.
- План первого среза: `~/.local/share/kilo/plans/1783886041469-first-slice-skill-loop.md`.

## Жизненный цикл ADR
Статусы: `Proposed` → `Accepted` → `Deprecated` / `Superseded`. Новое значимое решение → новый пронумерованный файл + строка в индексе. Решения не удаляются; при смене — помечаем `Superseded by ADR-00XX`.
