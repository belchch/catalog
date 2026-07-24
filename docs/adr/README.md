# Architecture Decision Records

Решения по архитектуре MVP ИИ-агента «Каталог». Каждая запись: Context → Decision → Consequences → Alternatives considered.

## Index

| #  | Решение | Статус |
|----|---------|--------|
| [0001](0001-agent-loop-execution-engine.md) | Один function-calling агент-луп как движок исполнения | Accepted |
| [0002](0002-skill-as-frozen-config.md) | Скилл = замороженный конфиг агента | Accepted · уточнён 0014/0015/0017/0018 |
| [0003](0003-code-via-tool-layer.md) | Code-возможность — базовая, через слой инструментов | Accepted · уточнён 0014/0016 |
| [0004](0004-build-at-approval-lifecycle.md) | Скилл строится в момент согласия (без дистилляции) | **Superseded (поток)** → 0018, уточнён 0015/0021 |
| [0005](0005-storage-split-git-deferred.md) | ФС для контента, SQLite для системных данных; git отложен | Accepted · уточнён 0012/0017 |
| [0006](0006-results-are-documents.md) | Результаты скилла — полноправные Documents | Accepted · уточнён 0017/0019 |
| [0007](0007-verify-deterministic-registry.md) | verify = детерминированный реестр проверок + retry | Accepted |
| [0008](0008-fts-as-system-skill.md) | FTS — системный скилл, после первого среза | Accepted · **не реализовано** |
| [0009](0009-openrouter-provider.md) | LLM через OpenRouter (selector + pin + streaming) | Accepted · уточнён 0013 |
| [0010](0010-first-slice-scope.md) | Скоуп первого среза и non-goals | Accepted · часть non-goals снята |
| [0011](0011-frontend-stack-tailwind.md) | Фронтенд-стек: React (Vite) + TypeScript + Tailwind | Accepted |
| [0012](0012-data-root-and-git-repos.md) | Data-root вне репо исходников + два app-owned git-репозитория | **Superseded (п.2/4/6)** → 0022 |
| [0013](0013-multi-provider-and-zai.md) | Multi-provider LLM-фабрика + z.ai провайдер + StreamDelta contract | Accepted |
| [0014](0014-script-skills.md) | Детерминированные script-скилы (kind=script) + sandbox | Accepted |
| [0015](0015-session-artifacts.md) | Артефакты сессии (prompt/script/meta); build = упаковка без LLM | Accepted · уточнён 0021 |
| [0016](0016-session-scoped-documents.md) | Документы видны агенту только через сессию | Accepted |
| [0017](0017-skill-apply-contract.md) | Контракт apply: input_arity, runtime-уточнение, режим вывода | Accepted |
| [0018](0018-skill-lifecycle-states.md) | Жизненный цикл скилла: draft → configure → commit → apply | Accepted |
| [0019](0019-obsidian-wikilinks-provenance.md) | Связь «результат ↔ источник» через Obsidian-wikilinks | Accepted |
| [0020](0020-ingest-formats.md) | Форматы ингеста md/docx/pdf/csv/xlsx; ленивое извлечение текста | Accepted |
| [0021](0021-skill-tracks-two-phase-build.md) | Двухфазная сборка: выбор операции (tracks) + анти-доменные правила | Accepted |
| [0022](0022-kb-repo-connect-ui.md) | Подключаемый KB-репозиторий (один репо, документы+результаты+скиллы), реальные git-коммиты из UI | Accepted |

> Записи 0016–0021 заведены 2026-07-24 по итогам сверки ADR с кодом: решения
> уже были приняты и работали в проде, но нигде не зафиксированы. Тогда же
> ранние записи (0002–0006, 0008, 0010, 0012, 0015) получили пометки
> «уточнён / superseded / не реализовано» вместо молчаливого устаревания.

## Открытые долги (сверка 2026-07-24)

- **FTS** (0008) — не реализован; при реализации обязан уважать scope сессии (0016).
- **Версии документа и diff** (0005/0012/0022) — нет; «переприменить скилл на новой версии» пока невозможно (коммиты пишутся, но diff/reapply-pipeline не построен).
- **Натяжение 0015 ↔ 0021** — при выбранном треке build снова стоит LLM-вызова и игнорирует ручные правки артефактов.
- **Лимит памяти в sandbox** (0014) — отложен до subprocess-изоляции.
- **Push-credentials и авто-миграция старого layout** (0022) — push полагается на окружение (SSH-агент/`.netrc`), нет UI для секретов; переход со старого `workspace/documents`+`workspace/skills` на новый layout — ручной.

## Связанные материалы
- Исходные транскрипции: `../pre-design/` (`opus-chat.json` — фундаментальные решения; `fable-review.json` — критика и уточнения).
- Реестр проверок: `../verification-checks.md`.
- План первого среза: `~/.local/share/kilo/plans/1783886041469-first-slice-skill-loop.md`.

## Жизненный цикл ADR
Статусы: `Proposed` → `Accepted` → `Deprecated` / `Superseded`. Новое значимое решение → новый пронумерованный файл + строка в индексе. Решения не удаляются; при смене — помечаем `Superseded by ADR-00XX`.
