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
| [0023](0023-script-dry-run.md) | Dry-run script-скилла до заморозки: прогон черновика в той же песочнице | Accepted |
| [0024](0024-named-skill-outputs.md) | Именованные выходы скилла: primary + companions, общий контракт для agent / script / pipeline | Accepted |
| [0025](0025-collection-skill-outputs.md) | Коллекционный выход скилла: `multiple: true` и N документов на элемент | Accepted |

## Связанные материалы
- Исходные транскрипции: `../pre-design/` (`opus-chat.json` — фундаментальные решения; `fable-review.json` — критика и уточнения).
- Реестр проверок: `../verification-checks.md`.
- План первого среза: `~/.local/share/kilo/plans/1783886041469-first-slice-skill-loop.md`.

## Жизненный цикл ADR
Статусы: `Proposed` → `Accepted` → `Deprecated` / `Superseded`. Новое значимое решение → новый пронумерованный файл + строка в индексе. Решения не удаляются; при смене — помечаем `Superseded by ADR-00XX`.

Частичная замена не вводит новый статус: запись остаётся `Accepted`, факт замены живёт в поле `Superseded by` и в короткой пометке индекса `Accepted (частично superseded NNNN)`.

## Словарь связей

Связи живут **в шапке**. Раздел `## Relation to …` в новых ADR не заводится. Существующие такие разделы в ADR-0014…0024 не мигрировать и не удалять.

Закрытый список глаголов — новые не вводить. Исторические синонимы (`Refines`, `Refined by`, `Updated by`) в уже принятых ADR не править; в новых записях вместо них — `Clarifies`. Связи в ADR-0001…0008 задним числом не проставлять.

| Глагол | Определение | Пара / обратная ссылка |
|--------|-------------|------------------------|
| `Extends` / `Extended by` | Новая запись добавляет измерение к принятому решению, не отменяя его. | Пара. `Extended by` желательна у живого предка, но не обязательна для исторических ADR-0001…0008. |
| `Revises` | Частичный пересмотр принятого решения. Типичная форма: `Revises: ADR-XXXX (частично)`. Предок остаётся `Accepted`. | Пары нет. |
| `Supersedes` / `Superseded by` | Замена решения — полная или частичная (с пометкой `частично`). | Пара обязательна: если A пишет `Supersedes: B`, у B должно быть `Superseded by: A` — кроме ADR-0001…0008. |
| `Clarifies` | Уточняет формулировку, не меняя решение. Сюда схлопываются `Refines`, `Refined by`, `Updated by`. | Обратная ссылка не обязательна. |
| `Related` | Соседняя запись или тикет без изменения решения (в дереве это в основном `CATALOG-N`). Не синоним `Extends`: `Extends` — наследование решения, `Related` — перекрёстная отсылка. | Пары нет. |
| `Does not change` | Явное ограждение скоупа: перечисленные ADR остаются в силе. Не связь. | Не применимо. |
