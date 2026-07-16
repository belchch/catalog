# Step 04 — Хранилище + инструменты документов (SQLite, FS, ingest, list/read)

- **Статус:** pending
- **Цель:** персистентный слой среза — SQLite-схема (Document/Session/Message/Skill/SkillRun), хранение файлов в `workspace/`, ingest `.md`/`.docx` с извлечением текста, и регистрация инструментов `list_documents`/`read_document` в `ToolRegistry` из шага 03. Без verify, агента, API, UI.

## Зависимости
- Шаг 03 (`ToolRegistry`, `ToolSpec`).
- Новые зависимости: `python-docx>=1.1` (извлечение текста из `.docx`). SQLite — через `sqlite3` (stdlib), без ORM.
- `APP_WORKSPACE` из `app.config` (по умолчанию `workspace`).

## Контракты

### `app/storage/schema.py`
```python
SCHEMA_SQL = """                  # idempotent CREATE TABLE IF NOT EXISTS
CREATE TABLE IF NOT EXISTS document(
  id TEXT PRIMARY KEY,            -- uuid4 hex
  title TEXT NOT NULL,
  path TEXT NOT NULL,             -- относительный путь в workspace/
  kind TEXT NOT NULL,             -- "md" | "docx" | "result_md"
  created_at TEXT NOT NULL        -- ISO-8601 UTC
);
CREATE TABLE IF NOT EXISTS session(
  id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL);   -- status: planning|done
CREATE TABLE IF NOT EXISTS message(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
  role TEXT NOT NULL, content TEXT, tool_name TEXT, tool_call_id TEXT, created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES session(id));
CREATE TABLE IF NOT EXISTS skill(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
  config_json TEXT NOT NULL, status TEXT NOT NULL,            -- draft|committed
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS skill_run(
  id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, session_id TEXT,
  input_doc_id TEXT, output_doc_id TEXT,
  status TEXT NOT NULL,                                         -- running|ok|failed
  trace_json TEXT, started_at TEXT NOT NULL, ended_at TEXT);
"""
```

### `app/storage/db.py`
```python
class Database:
    def __init__(self, path: str): ...          # ":memory:" для тестов
    def init_schema(self) -> None: ...          # executescript(SCHEMA_SQL)
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]: ...   # row_factory = sqlite3.Row
```
- Один файл БД: `workspace/catalog.db` (или `:memory:` в тестах). Подключение открывается на операцию (WAL можно не включать в срезе — solo).

### `app/storage/repo_document.py`
```python
@dataclass
class DocumentRow:
    id: str; title: str; path: str; kind: str; created_at: str

def create_document(db, *, title, path, kind) -> DocumentRow: ...   # генерит id (uuid4 hex)
def get_document(db, doc_id) -> DocumentRow | None: ...
def list_documents(db) -> list[DocumentRow]: ...
def list_documents_by_kind(db, kind) -> list[DocumentRow]: ...
```

### `app/documents/ingest.py`
```python
def ingest_file(db, workspace_dir, *, filename: str, content: bytes) -> DocumentRow:
    # 1. kind = ".md"->"md", ".docx"->"docx"; иначе ValueError("unsupported format")
    # 2. path = f"documents/{doc_id}.{ext}" внутри workspace_dir
    # 3. записать content в файл
    # 4. row = create_document(title=filename без расширения, path, kind)
    # 5. return row
```
- `.docx` текст извлекается **по требованию** в `read_document`, а не при ingest (хранить оригинал). Для `.md` — храним как есть.
- `workspace/documents/<id>.<ext>` — плоская раскладка.

### `app/documents/extract.py`
```python
def extract_text(path: str, kind: str) -> str:
    # "md"   -> читать файл (utf-8)
    # "docx" -> python-docx: "\n".join(p.text for p in doc.paragraphs)
```

### `app/documents/tools.py` — инструменты агента
```python
def build_document_tools(db, workspace_dir) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="list_documents",
        description="List all ingested documents with their id, title and kind.",
        parameters={"type": "object", "properties": {}},
    ), _list_documents)
    reg.register(ToolSpec(
        name="read_document",
        description="Read the full text of a document by its id.",
        parameters={"type": "object",
                    "properties": {"doc_id": {"type": "string"}},
                    "required": ["doc_id"]},
    ), _read_document)
    return reg
```
- `_list_documents(db, workspace_dir)` → возвращает `[{id, title, kind}, ...]`.
- `_read_document(db, workspace_dir, *, doc_id)` → `{title, kind, text}` через `extract_text`; нет документа → `{"error": "document not found"}` (строка-результат для агента, не исключение).
- Инструменты — замыкания над `(db, workspace_dir)`, async-обёртки (`async def`).

## Тесты (`backend/tests/test_storage.py`)
На БД `:memory:` + `tmp_path` для файлов:
- `test_schema_creates_all_tables` — после `init_schema` все 5 таблиц существуют (PRAGMA).
- `test_ingest_md_and_read` — ingest `.md` → DocumentRow(kind=md); `read_document` возвращает текст.
- `test_ingest_docx_and_read` — ingest с реальным мини-`.docx` (собрать через python-docx в фикстуре) → extract_text отдаёт параграфы.
- `test_unsupported_format_raises` — `.pdf` → ValueError.
- `test_list_documents` — 3 документа → список из 3.
- `test_read_unknown_doc_error` — `read_document(doc_id="nope")` → `{"error": ...}`.
- `test_document_tools_registered` — `build_document_tools` регистрирует ровно `list_documents`, `read_document`; `specs()` корректны.

## Команды запуска / проверки
```bash
cd backend
.venv/bin/pip install python-docx
.venv/bin/ruff check app/storage/ app/documents/ tests/test_storage.py
.venv/bin/python -m pytest tests/test_storage.py -v
```

## Критерий приёмки
- [ ] SQLite-схема создаётся идемпотентно; все 5 таблиц на месте.
- [ ] Ingest `.md` и `.docx` → строка в `document` + файл в `workspace/documents/`; неподдерживаемый формат → понятная ошибка.
- [ ] `read_document` достаёт текст (md — сырой, docx — параграфы); неизвестный id → `{"error": ...}`.
- [ ] `build_document_tools` регистрирует `list_documents` и `read_document` с корректными JSON-Schema.
- [ ] `ruff` чист; тесты зелёные.
- **Нет:** агента, verify, скиллов, FastAPI-эндпоинтов, UI, FTS, git/версий.

## Заметки
- `result_md`-документы (результаты скиллов) создаются в шаге 05 через тот же `repo_document.create_document(kind="result_md")`; схему и ingest здесь готовим полностью, чтобы шаг 05 только писал.
- `skill`/`skill_run`/`session`/`message` таблицы создаём сейчас (единая схема), репозитории под них — в шагах 05/06.
- Без миграционного фреймворка: срез — solo, единственный источник схемы `schema.py`. При изменении схемы в срезе — ADR + дроп/пересоздание (данных нет).
