"""Single source of truth for the SQLite schema.

All ``CREATE TABLE`` statements are idempotent (``IF NOT EXISTS``). The slice
is solo with no data, so there is no migration framework: this module is the
only place the schema is defined. Repositories for ``session``/``message``/
``skill``/``skill_run`` are added in later steps; the tables are created here
so the whole schema lives in one place.
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS document(
  id TEXT PRIMARY KEY,            -- uuid4 hex
  title TEXT NOT NULL,
  path TEXT NOT NULL,             -- relative path inside workspace/
  kind TEXT NOT NULL,             -- "md" | "docx" | "result_md"
  created_at TEXT NOT NULL        -- ISO-8601 UTC
);
CREATE TABLE IF NOT EXISTS session(
  id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
  skill_id TEXT,                   -- nullable; set when editing an existing skill (CATALOG-17)
  title TEXT,
  updated_at TEXT NOT NULL
);                                -- status: planning|done
CREATE TABLE IF NOT EXISTS session_document(
  session_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  attached_at TEXT NOT NULL,
  PRIMARY KEY (session_id, document_id),
  FOREIGN KEY (session_id) REFERENCES session(id),
  FOREIGN KEY (document_id) REFERENCES document(id)
);
CREATE TABLE IF NOT EXISTS message(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
  role TEXT NOT NULL, content TEXT, tool_name TEXT, tool_call_id TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES session(id)
);
CREATE TABLE IF NOT EXISTS skill(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
  config_json TEXT NOT NULL, status TEXT NOT NULL,            -- draft|committed
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_run(
  id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, session_id TEXT,
  input_doc_id TEXT, output_doc_id TEXT,
  input_doc_ids TEXT,                                            -- JSON array of input doc ids (CATALOG-4)
  status TEXT NOT NULL,                                         -- running|ok|failed
  trace_json TEXT, started_at TEXT NOT NULL, ended_at TEXT,
  persist INTEGER NOT NULL DEFAULT 1,                            -- 1 = auto-persist result_md (CATALOG-18)
  result_text TEXT                                               -- raw agent/script output, kept even when persist=0
);
CREATE TABLE IF NOT EXISTS session_artifact(
  session_id TEXT NOT NULL,
  type TEXT NOT NULL,           -- 'prompt' | 'script' | 'meta'
  content TEXT NOT NULL,        -- text for prompt/script; JSON for meta
  is_valid INTEGER NOT NULL DEFAULT 1,
  error TEXT,                   -- validation message (script/meta)
  source TEXT NOT NULL,         -- 'llm' | 'user'
  updated_at TEXT NOT NULL,
  PRIMARY KEY (session_id, type),
  FOREIGN KEY (session_id) REFERENCES session(id)
);
"""

# Safe additive migrations for existing databases (CATALOG-4 / CATALOG-17
# pattern). There is no migration framework: ``CREATE TABLE IF NOT EXISTS``
# only covers fresh databases, so columns added after the initial release need
# an idempotent ``ALTER TABLE`` guarded against the "duplicate column" error
# for databases that already have them. Each entry is ``(table, column, ddl)``.
ADDITIVE_MIGRATIONS: list[tuple[str, str, str]] = [
    ("skill_run", "input_doc_ids", "ALTER TABLE skill_run ADD COLUMN input_doc_ids TEXT"),
    ("session", "skill_id", "ALTER TABLE session ADD COLUMN skill_id TEXT"),
    (
        "skill_run",
        "persist",
        "ALTER TABLE skill_run ADD COLUMN persist INTEGER NOT NULL DEFAULT 1",
    ),
    ("skill_run", "result_text", "ALTER TABLE skill_run ADD COLUMN result_text TEXT"),
    ("session", "title", "ALTER TABLE session ADD COLUMN title TEXT"),
    ("session", "updated_at", "ALTER TABLE session ADD COLUMN updated_at TEXT"),
]
