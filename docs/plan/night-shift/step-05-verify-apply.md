# Step 05 — verify + apply_skill (реестр проверок, retry, результат=Document)

- **Статус:** pending
- **Цель:** детерминированные проверки (`verify`) из `verification-checks.md`, retry-цикл поверх агент-лупа, и `apply_skill` — полный прогон скилла по документу с сохранением результата как `Document(kind=result_md)` и строки `SkillRun`. Также `SkillConfig` + репозиторий скиллов. Без API/UI.

## Зависимости
- Шаг 03 (`run_agent`, `run_agent_collect`, `Trace`, `ToolRegistry`, `Message`).
- Шаг 04 (`Database`, `repo_document.create_document`, `extract_text`, `build_document_tools`).
- Без новых зависимостей (markdown-проверки — минимальный парсинг: regex/`str`; можно `markdown-it-py` опционально — решение ниже).

## Контракты

### `app/skills/config.py`
```python
@dataclass
class VerifyCheck:
    check: str                      # id из verification-checks.md
    params: dict = field(default_factory=dict)

@dataclass
class SkillConfig:
    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str]        # subset имён из реестра
    model: str                      # OpenRouter slug
    temperature: float = 0.0
    max_iterations: int = 8
    max_retries: int = 2
    verify_checks: list[VerifyCheck] = field(default_factory=list)
    output_kind: str = "md"

    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, s: str) -> "SkillConfig": ...
```

### `app/skills/verify.py`
```python
@dataclass
class VerifyResult:
    passed: bool
    failures: list[str]             # человеко-читаемые причины

CheckFn = Callable[[str, dict], str | None]   # (text, params) -> None если ок, иначе причина

# Реестр: id -> CheckFn
def register_check(check_id: str, fn: CheckFn) -> None: ...

def run_verify(text: str, checks: list[VerifyCheck]) -> VerifyResult: ...
```
Реализовать в срезе (из `verification-checks.md`):
- `non_empty` — `text.strip()` непустой.
- `min_length` / `max_length` — `params:{min?,max?,unit:"chars"|"lines"}`.
- `regex_matches` — `params:{pattern}`.
- `no_leftover_placeholders` — отсутствие `{...}`, `<...>`, `TODO`.
- `markdown_well_formed` — минимум: есть строки, заголовки `#` корректны, таблицы (если есть) имеют строку-разделитель `|---|`. (Без тяжёлого парсера; если `markdown-it-py` уже стоит — использовать.)
- `has_section` — `params:{heading, level?}` → поиск `^#{level}\s+heading`.
- `has_field` — `params:{key}` → regex `^key:\s*.+`.
- `table_parses` — `params:{min_rows?,min_cols?}`.

Несуществующий `check` → `VerifyResult(passed=False, failures=["unknown check: <id>"])` (fail-closed).

### `app/skills/repo_skill.py`
```python
def create_skill(db, *, name, description, config: SkillConfig, status="draft") -> str: ...
def get_skill(db, skill_id) -> SkillConfig | None: ...           # + id, status, name, description
def list_skills(db, status: str | None = None) -> list[dict]: ...
def update_status(db, skill_id, status: str) -> None: ...        # draft->committed
```

### `app/skills/repo_run.py`
```python
def create_run(db, *, skill_id, session_id, input_doc_id) -> str: ...    # status="running"
def finish_run(db, run_id, *, status, output_doc_id, trace: Trace) -> None: ...
def get_run(db, run_id) -> dict | None: ...
```

### `app/skills/apply.py`
```python
@dataclass
class ApplyResult:
    output_doc_id: str | None
    status: str                     # "ok" | "failed"
    result_text: str | None
    trace: Trace

async def apply_skill(
    *,
    provider: LLMProvider,
    db: Database,
    workspace_dir: str,
    skill: SkillConfig,
    input_doc_id: str,
    base_tools: ToolRegistry,       # все инструменты (build_document_tools + будущие)
    session_id: str | None = None,
) -> AsyncIterator[AgentEvent]:    # пробрасывает события run_agent наружу (для WS-стриминга)
    ...
```
Логика:
```
1. doc = get_document(input_doc_id); если нет -> FinishEvent error / raise ValueError.
2. tools = subset base_tools по skill.allowed_tools (ToolRegistry.filter(allowed_names)).
   - если allowed_tools содержит неизвестное имя -> fail-closed (ValueError/trace).
3. user_msg = Message("user", f"Обработай документ {input_doc_id} ({doc.title}).") 
   + инструменты read_document доступны агенту, чтобы достать текст.
4. trace = Trace(); last_text=None; passed=False
   for r in 0..skill.max_retries:
       text, run_trace, capped = await run_agent_collect(
           provider=provider, model=skill.model, system_prompt=skill.system_prompt,
           messages=[user_msg], tools=tools, temperature=skill.temperature,
           max_iterations=skill.max_iterations, use_stream=False)   # tool-цикл -> не-стрим
       trace.entries += run_trace.entries; last_text = text
       v = run_verify(text or "", skill.verify_checks)
       emit VerifyEvent(r+1, v)        # новое событие (добавить в events.py шага 03)
       if v.passed: passed=True; break
       if r < max_retries:
           messages += [assistant(text), user("verify failed: {v.failures}; исправь и повтори")]
5. if passed:
       out = create_document(db, title=f"{skill.name} — {doc.title}", 
                             path=f"results/{out_id}.md", kind="result_md")
       write text -> workspace/results/{out_id}.md
       status="ok"
   else: status="failed"; out_id=None (результат last_text всё равно в trace/UI)
6. finish_run(db, run_id, status=status, output_doc_id=out_id, trace=trace)
7. yield FinishEvent(last_text, "capped"/"stop"..., capped=(not passed and last capped))
8. (collect-обёртка apply_skill_collect(...) -> ApplyResult для шага, где стриминг не нужен)
```

> Добавить в `events.py` (шаг 03) `VerifyEvent(iteration, result: VerifyResult)` —步-05 его использует; если шаг 03 уже принят, добавить как минимальное расширение без ломания контракта.

## Тесты
`backend/tests/test_verify.py`:
- каждый check на pass/fail (non_empty, has_section с/без level, table_parses min_rows, no_leftover_placeholders и т.д.).
- `unknown check` → fail-closed.
- `run_verify` комбинирует несколько проверок.

`backend/tests/test_apply.py` (на FakeProvider + БД `:memory:` + tmp workspace):
- `test_apply_success_first_try` — FakeProvider даёт текст, проходящий verify → status=ok, result_md-документ создан, output_doc_id задан.
- `test_apply_retry_then_success` — скрипт: плохой текст → retry → хороший → passed, status=ok, в trace виден retry.
- `test_apply_verify_never_passes` — всегда плохой текст, max_retries исчерпан → status=failed, output_doc_id=None, last_text сохранён в trace.
- `test_apply_filters_tools` — skill.allowed_tools subset; spy что агенту переданы только разрешённые specs.
- `test_apply_unknown_allowed_tool` — allowed_tools содержит неизвестное имя → fail-closed (ошибка, без прогона).

## Команды запуска / проверки
```bash
cd backend
.venv/bin/ruff check app/skills/ tests/test_verify.py tests/test_apply.py
.venv/bin/python -m pytest tests/test_verify.py tests/test_apply.py -v
```

## Критерий приёмки
- [ ] Реализованы все проверки из `verification-checks.md` базового+markdown блоков; неизвестная — fail-closed.
- [ ] `apply_skill` крутит run_agent + verify-retry, до `max_retries`; успех → `Document(result_md)` + `SkillRun(status=ok)`; провал → `status=failed` с сохранённым trace.
- [ ] `allowed_tools` фильтрует реестр; неизвестное имя → fail-closed.
- [ ] `SkillConfig` сериализуется/десериализуется в JSON (для колонки `config_json`).
- [ ] `ruff` чист; тесты зелёные.
- **Нет:** FastAPI-эндпоинтов, UI, FTS, git. «Создать скилл из чата» (build) — здесь конфиг есть, но генерация конфига из сессии — шаг 06.

## Заметки
- `apply_skill` — async generator (проброс событий) ИЛИ collect-обёртка; оба нужны: WS-стриминг (06) итерирует генератор, «Создать скилл» синхронно ждёт результат.
- Генерация `SkillConfig` из чат-сессии (LLM-вызов со structured output) — отдельная функция `build_skill_from_session(...)`, отнести в шаг 06 (там же WS-планировщик и сессии). Здесь — только потребитель конфига.
- Маркдаун-проверки: если решено тянуть `markdown-it-py`, зафиксировать в ADR; иначе — regex-минимум (документирован как «достаточный для среза»).
