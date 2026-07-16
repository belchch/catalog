# CATALOG-8 — Теги скилов на UI: ai / python

- **Задача Plane:** [CATALOG-8](https://app.plane.so/belchch/projects/catalog-app/work-items/8) (id: `7f6d39a1-bc64-4b06-a6f4-52e34fc768aa`, state: In Progress)
- **Статус плана:** Analyzed
- **Предпосылки:** CATALOG-3 (поле `kind` в SkillConfig)
- **Цель:** Показывать на UI у скилов теги-«способности»: `python` — скил содержит Python-код (детерминированная часть); `ai` — скил содержит промпт/обращается к моделям (недетерминированное поведение). Теги — производные от конфига скила (поле `kind`/`code`/наличие промпта из [CATALOG-3](https://app.plane.so/belchch/projects/catalog-app/work-items/3)). Это даёт пользователю визуальный признак: нужны ли модели, и заложена база под будущий «режим без доступа к моделям» (только скрипты).

## Контекст

Сейчас у скила **нет ни типа, ни тегов на UI**, и они не передаются с бэка:

- **Бэк — выход скила:** `SkillOut` (`backend/app/api/schemas.py:15-20`) отдаёт только `id, name, description, status, created_at`. Поля `kind`/`tags` нет. `list_skills_endpoint` (`backend/app/api/skills.py:229-242`) строит `SkillOut` из словаря `list_skills(db, ...)` (`backend/app/skills/repo_skill.py:81-105`) — тот возвращает `id/name/description/status/created_at/updated_at` и **не читает `config_json`**, поэтому тип скила сейчас вообще не доходит до API.
- **Конфиг:** `SkillConfig` (`backend/app/skills/config.py:28-40`) хранит `system_prompt, allowed_tools, model, ...` — все текущие скилы по сути «агентские» (есть промпт + модель). Поля `kind`/`code` **появятся в CATALOG-3** (`kind: "agent"|"script"`, `code` для скрипта). Эта задача опирается на них как на источник тегов.
- **Фронт:** `frontend/src/api.ts:11-17` `SkillOut` — без тегов. `frontend/src/components/SkillsPanel.tsx:29-86` рисует карточку скила: имя + бейдж `status` (`committed`/`draft`, `SkillsPanel.tsx:35-44`) + описание + кнопки Коммит/Применить. **Тегов-способностей нет.**
- **Правила тегов (из описания задачи):**
  - `python` — скил **содержит Python** (детерминированный код: `kind=="script"` или наличие `code`).
  - `ai` — скил **содержит промпт кроме скрипта** (использует LLM/модель, недетерминирован: `kind=="agent"` или непустой `system_prompt`/`model`).
  - Возможен «смешанный» скил → **оба** тега одновременно (заложить как список, а не взаимоисключающий enum).

## Затрагиваемые файлы

**Backend:**
- `backend/app/skills/config.py` — (зависит от CATALOG-3) поле `kind`/`code`; здесь — добавить хелпер вычисления тегов: `SkillConfig.tags() -> list[str]` (или отдельная функция `compute_tags(config)`): `python` если `kind=="script"` или `code`; `ai` если `kind=="agent"` или непустой `system_prompt`/`model`. До CATALOG-3 — fallback: все текущие скилы → `ai`.
- `backend/app/skills/repo_skill.py:81-105` — `list_skills` должен возвращать `config_json` (или десериализованный конфиг/`kind`), чтобы API мог посчитать теги. Иначе — вычислять теги в `list_skills_endpoint` через `get_skill`/десериализацию.
- `backend/app/api/schemas.py:15-20` — добавить `tags: list[str]` (или `kind: str` + computed tags) в `SkillOut`.
- `backend/app/api/skills.py:229-242` — при сборке `SkillOut` вычислять `tags` из конфига (через хелпер из п.1).
- `backend/tests/test_api.py` — кейсы: agent-скил → тег `ai`; script-скил (CATALOG-3) → `python`; смешанный → оба; старый скил без `kind` → `ai`.

**Frontend:**
- `frontend/src/api.ts:11-17` — добавить `tags: string[]` (или `kind`) в `SkillOut`.
- `frontend/src/components/SkillsPanel.tsx:32-48` — рендерить теги-бейджи (рядом с бейджем `status`): `python` (стиль, напр. жёлтый), `ai` (напр. фиолетовый). Переиспользовать существующий стиль бейджа (`SkillsPanel.tsx:35-44`).
- (опционально) `frontend/src/hooks/useSkills.ts` — проброс без изменений (теги едут в `SkillOut`).

## План действий

1. **Согласовать источник с CATALOG-3.** Теги вычисляются из `SkillConfig`: `python` ← `kind=="script"` или наличие `code`; `ai` ← `kind=="agent"` или непустой `system_prompt`/`model`. Если CATALOG-3 ещё не смержен — реализовать fallback (все скилы → `ai`), а UI-инфраструктуру (`tags` на `SkillOut` + рендер) добавить сразу.
2. **Хелпер тегов (backend).** В `config.py` — `compute_tags(config) -> list[str]` (или метод `SkillConfig.tags()`), покрывающий правила выше, включая смешанный случай (оба тега).
3. **Проброс конфига в list.** В `repo_skill.list_skills` отдавать `config_json` (или `kind`), чтобы эндпоинт мог посчитать теги; либо вычислять теги внутри репо/эндпоинта.
4. **SkillOut + эндпоинт.** Добавить `tags: list[str]` в `SkillOut` (`schemas.py`); в `list_skills_endpoint` (`skills.py`) считать теги через хелпер.
5. **Тесты backend.** agent→`ai`; script→`python`; mixed→оба; legacy (без `kind`)→`ai`; `GET /skills` отдаёт теги.
6. **Фронтенд — типы.** `tags: string[]` в `SkillOut` (`api.ts`).
7. **Фронтенд — UI.** В `SkillsPanel` рендерить бейджи `python`/`ai` на карточке скила (`SkillsPanel.tsx:32-48`); стили согласовать со статус-бейджем.
8. **Ручная проверка.** Список скилов показывает теги; agent-скил — `ai`; script-скил (после CATALOG-3) — `python`; смешанный — оба.

## Критерии приёмки (Definition of Done)

- [ ] `GET /skills` возвращает `tags` для каждого скила, вычисленные из конфига.
- [ ] Тег `python` ставится скилам с Python-кодом (`kind=="script"`/`code`); тег `ai` — скилам с промптом/LLM (`kind=="agent"`/`system_prompt`/`model`); смешанный скил получает оба тега.
- [ ] В UI (`SkillsPanel`) теги `python`/`ai` отображаются на карточке скила (различимы визуально).
- [ ] До введения `kind` (без CATALOG-3) теги корректно деградируют: текущие скилы помечены `ai`, UI-инфраструктура готова.
- [ ] `backend`: `pytest backend/tests` зелёные, добавлены кейсы вычисления тегов.
- [ ] `backend`: `ruff check backend` без ошибок.
- [ ] `frontend`: `npm run typecheck`/`npm run lint` проходят.
