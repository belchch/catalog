# Step 06 — Backend API (FastAPI: documents, planner WS, skill build/commit/apply, run streaming)

- **Статус:** pending
- **Цель:** HTTP/WebSocket-слой, связывающий движок (03), хранилище (04) и скиллы (05) с UI. Загрузка/список документов, WS-планировщик (агент-луп чата), генерация скилла из сессии (`build`), коммит, применение, просмотр/стриминг прогона. lifespan-инициализация БД + httpx + провайдера.

## Зависимости
- Шаги 03/04/05 (без новых Python-зависимостей; `fastapi`, `uvicorn[standard]` уже стоят — `python-multipart` НУЖЕН для upload файлов).
- Новая зависимость: `python-multipart>=0.0.9` (Form/File upload в FastAPI).

## Контракты

### `app/main.py` — lifespan + роутеры
```python
@asynccontextmanager
async def lifespan(app):
    db = Database(settings.db_path); db.init_schema()
    http_client = httpx.AsyncClient(timeout=60.0, event_hooks=build_debug_hooks())
    app.state.db = db
    app.state.http_client = http_client
    app.state.provider = OpenRouterProvider(http_client, settings.api_key, settings.base_url)
    app.state.workspace = settings.workspace_dir
    try: yield
    finally: await http_client.aclose()

app = FastAPI(lifespan=lifespan)   # CORS уже есть (step-01) — оставить localhost:5173
app.include_router(documents.router)
app.include_router(sessions.router)
app.include_router(skills.router)
app.include_router(runs.router)
```

### `app/api/schemas.py` (Pydantic v2)
```python
class DocumentOut(BaseModel): id: str; title: str; kind: str; created_at: str
class SkillOut(BaseModel): id: str; name: str; description: str | None; status: str; created_at: str
class ApplyRequest(BaseModel): doc_id: str
class RunOut(BaseModel): id: str; skill_id: str; input_doc_id: str | None; output_doc_id: str | None; status: str; trace: dict | None
class BuildSkillRequest(BaseModel): session_id: str
class CommitOut(BaseModel): id: str; status: str
```

### `app/api/documents.py`
- `POST /documents` — multipart `file: UploadFile`; accepts `.md`/`.docx`; `ingest_file(...)` → `DocumentOut`.
- `GET /documents` — `list[DocumentOut]`.

### `app/api/sessions.py`
- `POST /sessions` — создаёт Session(status=planning) → `{id}`.
- `WS /sessions/{id}` — planner агент-луп.
  - Клиент шлёт текстовые сообщения (user).
  - Сервер: append user Message; запускает `run_agent` с инструментами `list_documents`/`read_document` (в стрим-режиме: токены идут пользователю); эмитит в WS события как JSON: `{type:"token", delta}`, `{type:"step"}`, `{type:"tool_call"}`, `{type:"tool_result"}`, `{type:"finish"}`.
  - Сохраняет каждое Message в БД (role/content/tool_*).
  - tool-режим: если planner должен вызвать инструменты — `use_stream=False` под-прогон (см. заметку шаг 03); упростить в срезе: planner бегает в `use_stream=False` collect, финальный текст стримится одним кадром или по чанкам. Зафиксировать решение.

### `app/api/skills.py`
- `POST /sessions/{id}/skills` — `build_skill_from_session(session_id)`:
  - Один LLM-вызов (`provider.complete`) с системным промптом «собери SkillConfig из истории сессии», tools=`[build_skill]` (один tool, schema = SkillConfig-поля) → парсинг аргументов в `SkillConfig`.
  - Валидация: `allowed_tools ⊆ registry.names()`, `verify_checks[].check ∈ registry checks`; иначе retry (до 2) с обратной связью.
  - `create_skill(status="draft")` → `{skill_id, config}`.
  - (Опционально в этом же вызове) `apply_skill(draft, current_doc_id)` → стрим прогона. В срезе: возвращаем `{skill_id}`; применение — отдельным `POST /skills/{id}/apply`. Так проще для UI.
- `POST /skills/{id}/commit` → `update_status("committed")` → `CommitOut`.
- `GET /skills` — `list[SkillOut]` (опц. `?status=`).

### `app/api/runs.py`
- `POST /skills/{id}/apply` (`ApplyRequest`) — `create_run(skill_id, input_doc_id)` → `{run_id}`.
- `GET /runs/{id}` — `RunOut` (результат + trace из БД).
- `WS /runs/{id}/stream` — достаёт skill+run, запускает `apply_skill` (async gen), форвардит события в WS; по завершении — кадр `{type:"finish", status, output_doc_id}`.

### WS-протокол (единый для sessions и runs)
```
server -> client (JSON):
  {"type":"step","iteration":N}
  {"type":"token","delta":"..."}            # только sessions (планировщик)
  {"type":"tool_call","id":"..","name":"..","arguments":{...}}
  {"type":"tool_result","id":"..","name":"..","ok":bool,"result":...}
  {"type":"verify","iteration":N,"passed":bool,"failures":[...]}   # только runs
  {"type":"finish","capped":bool,"status":"ok|failed|..."}
client -> server (sessions): {"type":"user","content":"..."} или plain text
```

## Тесты (`backend/tests/test_api.py`)
На `httpx.ASGITransport` + `TestClient`/`httpx.AsyncClient`, БД `:memory:`/tmp, FakeProvider в `app.state.provider`:
- `test_upload_and_list_documents` — `.md` upload → 200, `DocumentOut`; GET → список содержит его.
- `test_upload_unsupported_format` — `.pdf` → 422/400.
- `test_health` — регресс `/health` → ok.
- `test_ws_session_planner` — WS-подключение, отправка user, FakeProvider отдаёт финальный текст → клиент получает `token`/`finish`; Message сохранён в БД.
- `test_build_skill_from_session` — FakeProvider возвращает tool_call `build_skill` с валидным конфигом → `skill_id`, status=draft; невалидный allowed_tools → retry/ошибка.
- `test_commit_skill` → status=committed.
- `test_apply_skill_run` — create run → WS stream → `finish status=ok`, output_doc_id задан; GET /runs/{id} отдаёт trace.
- `test_apply_skill_failed` — verify не проходит → finish status=failed.

> WS-тесты на FastAPI: через `httpx-ws` или `starlette.testclient.TestClient` websocket context. Зафиксировать выбранный способ в `conftest.py`.

## Команды запуска / проверки
```bash
cd backend
.venv/bin/pip install python-multipart
.venv/bin/ruff check app/ tests/test_api.py
.venv/bin/python -m pytest tests/test_api.py -v
.venv/bin/uvicorn app.main:app --reload   # ручная проверка /docs
```

## Критерий приёмки
- [ ] `POST /documents` (md/docx) и `GET /documents` работают; неподдерживаемый формат → понятная ошибка.
- [ ] `WS /sessions/{id}` — агент-луп планировщика: токены/инструменты/finish идут клиенту; история сохраняется.
- [ ] `POST /sessions/{id}/skills` собирает валидный `SkillConfig` (с валидацией allowed_tools/verify_checks и retry) → draft-скилл.
- [ ] `POST /skills/{id}/commit`, `GET /skills`.
- [ ] `POST /skills/{id}/apply` → run; `WS /runs/{id}/stream` стримит события включая verify/finish; `GET /runs/{id}`.
- [ ] lifespan корректно поднимает/закрывает БД+httpx; `/health` жив.
- [ ] `ruff` чист; WS- и REST-тесты зелёные.
- **Нет:** UI (это шаг 07), FTS, git.

## Заметки
- CORS уже сужен до `http://localhost:5173` (step-01) — оставить.
- Стриминг токенов планировщика: если в шаге 03 stream-режим не разбирал tool_calls, planner либо бежит collect (не-стрим) и отдаёт финал одним кадром, либо стримит токены без tool-цикла. Выбрать и зафиксировать здесь; UI (07) зависит от WS-протокола выше.
- `build_skill` как tool (function-calling) предпочтительнее «free JSON» — модель уже умеет tool-calling (доказано шагом 02).
