"""Single source of truth for the SQLite schemas (app + workspace).

All ``CREATE TABLE`` statements are idempotent (``IF NOT EXISTS``).
"""

APP_USER_VERSION = 2
WORKSPACE_USER_VERSION = 1

APP_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace_registry(
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  display_name TEXT,
  opened_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_settings(
  id INTEGER PRIMARY KEY CHECK (id = 1),
  provider TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  openrouter_api_key TEXT NOT NULL DEFAULT '',
  zai_api_key TEXT NOT NULL DEFAULT '',
  skill_budget_llm_calls INTEGER NOT NULL DEFAULT 60,
  skill_budget_nested_runs INTEGER NOT NULL DEFAULT 20
);
INSERT OR IGNORE INTO app_settings(id, provider, model) VALUES (1, '', '');
"""

APP_ADDITIVE_MIGRATIONS: list[tuple[str, str, str]] = [
    (
        "app_settings",
        "openrouter_api_key",
        "ALTER TABLE app_settings ADD COLUMN openrouter_api_key TEXT NOT NULL DEFAULT ''",
    ),
    (
        "app_settings",
        "zai_api_key",
        "ALTER TABLE app_settings ADD COLUMN zai_api_key TEXT NOT NULL DEFAULT ''",
    ),
    (
        "app_settings",
        "skill_budget_llm_calls",
        "ALTER TABLE app_settings ADD COLUMN skill_budget_llm_calls INTEGER NOT NULL DEFAULT 60",
    ),
    (
        "app_settings",
        "skill_budget_nested_runs",
        "ALTER TABLE app_settings ADD COLUMN skill_budget_nested_runs INTEGER NOT NULL DEFAULT 20",
    ),
]

WORKSPACE_SCHEMA = """
CREATE TABLE IF NOT EXISTS document(
  id TEXT PRIMARY KEY,            -- uuid4 hex
  title TEXT NOT NULL,
  path TEXT NOT NULL,             -- relative path inside workspace/
  kind TEXT NOT NULL,             -- "md" | "docx" | "result_md"
  created_at TEXT NOT NULL,       -- ISO-8601 UTC
  mtime REAL,
  size INTEGER,
  content_hash TEXT,
  extracted_text TEXT
);
CREATE TABLE IF NOT EXISTS session(
  id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
  skill_id TEXT,                   -- nullable; set when editing an existing skill (CATALOG-17)
  title TEXT,
  updated_at TEXT NOT NULL,
  llm_timeout_seconds INTEGER NOT NULL DEFAULT 60
);                                -- status: planning|done
CREATE TABLE IF NOT EXISTS session_document(
  session_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  attached_at TEXT NOT NULL,
  PRIMARY KEY (session_id, document_id),
  FOREIGN KEY (session_id) REFERENCES session(id),
  FOREIGN KEY (document_id) REFERENCES document(id)
);
CREATE TABLE IF NOT EXISTS session_skill(
  session_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  attached_at TEXT NOT NULL,
  PRIMARY KEY (session_id, skill_id),
  FOREIGN KEY (session_id) REFERENCES session(id),
  FOREIGN KEY (skill_id) REFERENCES skill(id)
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
  result_text TEXT,                                              -- raw agent/script output, kept even when persist=0
  result_artifacts TEXT,                                         -- JSON object key→text (CATALOG-145)
  output_doc_ids TEXT,                                           -- JSON array of result doc ids, primary first
  user_prompt TEXT,
  parent_run_id TEXT                                             -- nested skill-as-tool run (ADR-0019)
);
CREATE TABLE IF NOT EXISTS session_artifact(
  session_id TEXT NOT NULL,
  type TEXT NOT NULL,           -- 'prompt' | 'script' | 'meta' | 'steps' | 'outputs'
  content TEXT NOT NULL,        -- text for prompt/script; JSON for meta
  is_valid INTEGER NOT NULL DEFAULT 1,
  error TEXT,                   -- validation message (script/meta)
  source TEXT NOT NULL,         -- 'llm' | 'user'
  updated_at TEXT NOT NULL,
  PRIMARY KEY (session_id, type),
  FOREIGN KEY (session_id) REFERENCES session(id)
);
CREATE TABLE IF NOT EXISTS custom_check(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  prompt TEXT NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_script_dry_run(
  session_id TEXT NOT NULL,
  slot TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  ok INTEGER NOT NULL,
  stage TEXT,
  error TEXT,
  ran_at TEXT NOT NULL,
  PRIMARY KEY (session_id, slot),
  FOREIGN KEY (session_id) REFERENCES session(id)
);
"""

SCHEMA_SQL = WORKSPACE_SCHEMA

ADDITIVE_MIGRATIONS: list[tuple[str, str, str]] = [
    ("skill_run", "input_doc_ids", "ALTER TABLE skill_run ADD COLUMN input_doc_ids TEXT"),
    ("session", "skill_id", "ALTER TABLE session ADD COLUMN skill_id TEXT"),
    (
        "skill_run",
        "persist",
        "ALTER TABLE skill_run ADD COLUMN persist INTEGER NOT NULL DEFAULT 1",
    ),
    ("skill_run", "result_text", "ALTER TABLE skill_run ADD COLUMN result_text TEXT"),
    ("skill_run", "user_prompt", "ALTER TABLE skill_run ADD COLUMN user_prompt TEXT"),
    ("session", "title", "ALTER TABLE session ADD COLUMN title TEXT"),
    ("session", "updated_at", "ALTER TABLE session ADD COLUMN updated_at TEXT"),
    (
        "session",
        "llm_timeout_seconds",
        "ALTER TABLE session ADD COLUMN llm_timeout_seconds INTEGER NOT NULL DEFAULT 60",
    ),
    ("document", "mtime", "ALTER TABLE document ADD COLUMN mtime REAL"),
    ("document", "size", "ALTER TABLE document ADD COLUMN size INTEGER"),
    ("document", "content_hash", "ALTER TABLE document ADD COLUMN content_hash TEXT"),
    (
        "document",
        "extracted_text",
        "ALTER TABLE document ADD COLUMN extracted_text TEXT",
    ),
    (
        "skill_run",
        "parent_run_id",
        "ALTER TABLE skill_run ADD COLUMN parent_run_id TEXT",
    ),
    (
        "skill_run",
        "result_artifacts",
        "ALTER TABLE skill_run ADD COLUMN result_artifacts TEXT",
    ),
    (
        "skill_run",
        "output_doc_ids",
        "ALTER TABLE skill_run ADD COLUMN output_doc_ids TEXT",
    ),
]
