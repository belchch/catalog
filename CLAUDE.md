# Catalog — правила для Claude Code

Контекст проекта (стек, структура, запуск, ADR) — [`AGENTS.md`](AGENTS.md).

Ниже — инварианты, которые обязаны выполняться в **любой** сессии и в **любой**
роли пайплайна `catalog-pipeline`. Порт из `.cursor/rules/catalog-pipeline-checks.mdc`,
где эти правила автоприкреплялись по `globs: docs/plan/night-shift/**,backend/**,frontend/**`.

Эти же правила продублированы в `.claude/agents/catalog-*.md`: у сабагента свой
системный промпт, и этот файл в него не попадает. Расхождение между CLAUDE.md и
ролью — баг, править надо оба места.

## Команды проверок

Гонять **по всему коду**, не только по диффу.

Backend — из `backend/`:

```bash
ruff check .
pytest
```

Frontend — из `frontend/`:

```bash
pnpm run build
pnpm run lint
pnpm run typecheck
pnpm run test
```

`pnpm run test` (`vitest run`) — такая же обязательная проверка, как остальные
три. Не прогнанная проверка не считается зелёной.

## Definition of Done шага

DoD шага пайплайна = критерии приёмки из файла плана
(`docs/plan/<RUN_NAME>/NN-CATALOG-*.md`)
+ все шесть команд выше зелёные
+ нет Critical/Medium замечаний `catalog-reviewer`.

Для UI-шага (маркер `- **Тип шага:** ui` в плане) дополнительно: нет
Critical/Medium замечаний `catalog-ui-reviewer` + выполнены критерии визуальной
приёмки из дизайн-спеки `docs/plan/<RUN_NAME>/<stem плана>.design.md`.

Последний гейт DoD — задача `finalize` у `catalog-steward`: шаг с незакрытой
частью не коммитится, а возвращается в цикл генератор↔ревьюеры.

## Секреты

- Ключи и токены — только через `.env` / переменные окружения
  (`${env:VAR}` в MCP-конфигах).
- Никогда не хардкодить их в коде, в промптах агентов и в файлах состояния.
- Никогда не коммитить `.env*` (кроме `.env.example`), `.claude/state/*`,
  `.claude/steps-results/*`, `.cursor/state/*`, `.kilo/plans/*`.

## Файл состояния пайплайна

STATE (`.claude/state/*.json`; легаси-дефолт workflow-скрипта —
`.cursor/state/night-shift.json`) читает и пишет **только оркестратор**:
parent-сессия и роль `catalog-steward`, которой оркестратор делегирует работу с
диском и git.

Подагенты `catalog-designer`, `catalog-generator`, `catalog-reviewer`,
`catalog-ui-reviewer` STATE **не читают и не пишут**. Их память о шаге — только
то, что передано во входе (`ISSUES`, `PRIOR_WORK`, `PRIOR_ISSUES`, `DIFF_BASE`)
и фактическое состояние рабочего дерева.
