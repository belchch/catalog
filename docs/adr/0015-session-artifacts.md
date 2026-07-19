# ADR 0015: Артефакты сессии (prompt/script/meta) и build как упаковка

- **Date:** 2026-07-19
- **Status:** Accepted
- **Revises:** ADR-0002 (частично), ADR-0004 (частично), ADR-0014 (частично)

## Context

До CATALOG-53 `system_prompt` / `code` существовали только внутри
`skill.config_json` после `POST /sessions/{id}/skills`. Этот эндпоинт
синхронно вызывал LLM (`build_skill_from_session`), чтобы заново синтезировать
весь `SkillConfig` из истории чата. При таймаутах и ретраях кнопка «Создать
скилл» зависала и отваливалась.

Пользователь при этом не видел и не мог править черновик prompt/script до
момента build.

## Decision

1. **Таблица `session_artifact`** — один текущий артефакт на тип
   (`prompt` | `script` | `meta`) с upsert по `(session_id, type)`.
   `meta.content` — JSON `{name, description, kind, input_arity,
   allowed_tools, verify_checks}`.

2. **Планировщик** материализует артефакты инструментами
   `save_skill_prompt` / `save_skill_script` / `set_skill_meta` /
   `read_skill_draft` по ходу диалога. После save WS шлёт кадр
   `session_artifacts`. Полный prompt/script не дублируется простынёй в чат.

3. **REST** `GET/PATCH /sessions/{id}/artifacts…` и
   `PATCH /sessions/{id}/skill-meta` — ручное редактирование (`source=user`);
   script валидируется через `validate_script`.

4. **Build = упаковка.** Основной путь `build_skill_from_session` читает meta +
   артефакт по `kind`, собирает `SkillConfig` без LLM. Пустые/битые артефакты
   → понятная 422. Если артефактов нет вовсе (старые сессии) — legacy LLM
   fallback.

5. **Edit-сессия** (`POST /skills/{id}/edit`) засевает `session_artifact` из
   текущего конфига скилла.

`model` / `provider` / `reasoning` по-прежнему добираются в SkillSettingsModal
после build (CATALOG-6).

## Consequences

**Плюсы:**
- Build в основном пути мгновенный и без LLM.
- Черновик виден и правится до согласия на создание скилла.
- Script-ошибки ловятся при save (tool/PATCH), а не в retry-loop билда.

**Минусы / риски:**
- Планировщик должен помнить вызвать tools; иначе build даёт 422 (или LLM
  fallback только при полном отсутствии артефактов).
- Concurrent edit: ручное сохранение блокируется на UI, пока идёт ход
  планировщика (см. UI-план CATALOG-53).

## Alternatives considered

- **Короткий LLM-вызов только для `allowed_tools` на build** — частично
  возвращает задержку; отклонено в пользу фиксации tools в `set_skill_meta`.
- **Версионирование артефактов** — избыточно для среза; один текущий на тип.
- **Оставить только LLM-build** — не решает таймауты и невидимость черновика.

## Relation to ADR-0002 / ADR-0004 / ADR-0014

ADR-0002 остаётся в силе: скилл = замороженный конфиг. ADR-0004 остаётся:
скилл строится в момент согласия — но «построить» теперь значит «упаковать
готовые артефакты», а не «синтезировать из чата». ADR-0014 остаётся для
`kind=script`; артефакт `script` — его черновик до freeze.
