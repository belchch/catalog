from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from catalog.storage.db import Database

ARTIFACT_TYPES = ("prompt", "script", "meta", "steps")
ARTIFACT_SOURCES = ("llm", "user")
SCRIPT_DRY_RUN_SLOT = "script"
_DRY_RUN_ERROR_LIMIT = 400


@dataclass
class ArtifactRow:
    session_id: str
    type: str
    content: str
    is_valid: bool
    error: str | None
    source: str
    updated_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_artifact(row: sqlite3.Row) -> ArtifactRow:
    return ArtifactRow(
        session_id=row["session_id"],
        type=row["type"],
        content=row["content"],
        is_valid=bool(row["is_valid"]),
        error=row["error"],
        source=row["source"],
        updated_at=row["updated_at"],
    )


def upsert_artifact(
    db: Database,
    *,
    session_id: str,
    type: str,
    content: str,
    source: str,
    is_valid: bool = True,
    error: str | None = None,
) -> ArtifactRow:
    if type not in ARTIFACT_TYPES:
        raise ValueError(f"unknown artifact type: {type!r}")
    if source not in ARTIFACT_SOURCES:
        raise ValueError(f"unknown artifact source: {source!r}")
    now = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO session_artifact("
            "session_id, type, content, is_valid, error, source, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, type) DO UPDATE SET "
            "content = excluded.content, "
            "is_valid = excluded.is_valid, "
            "error = excluded.error, "
            "source = excluded.source, "
            "updated_at = excluded.updated_at",
            (
                session_id,
                type,
                content,
                1 if is_valid else 0,
                error,
                source,
                now,
            ),
        )
        row = conn.execute(
            "SELECT session_id, type, content, is_valid, error, source, updated_at "
            "FROM session_artifact WHERE session_id = ? AND type = ?",
            (session_id, type),
        ).fetchone()
    assert row is not None
    return _row_to_artifact(row)


def get_artifact(
    db: Database, session_id: str, type: str
) -> ArtifactRow | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT session_id, type, content, is_valid, error, source, updated_at "
            "FROM session_artifact WHERE session_id = ? AND type = ?",
            (session_id, type),
        ).fetchone()
    return _row_to_artifact(row) if row is not None else None


def list_artifacts(db: Database, session_id: str) -> list[ArtifactRow]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT session_id, type, content, is_valid, error, source, updated_at "
            "FROM session_artifact WHERE session_id = ? "
            "ORDER BY CASE type WHEN 'meta' THEN 0 WHEN 'prompt' THEN 1 "
            "WHEN 'script' THEN 2 WHEN 'steps' THEN 3 ELSE 4 END",
            (session_id,),
        ).fetchall()
    return [_row_to_artifact(r) for r in rows]


def delete_artifact(db: Database, session_id: str, type: str) -> bool:
    with db.connect() as conn:
        cur = conn.execute(
            "DELETE FROM session_artifact WHERE session_id = ? AND type = ?",
            (session_id, type),
        )
        return cur.rowcount > 0


def delete_session_artifacts(db: Database, session_id: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM session_artifact WHERE session_id = ?",
            (session_id,),
        )
        conn.execute(
            "DELETE FROM session_script_dry_run WHERE session_id = ?",
            (session_id,),
        )


@dataclass
class ScriptDryRunRow:
    session_id: str
    slot: str
    sha256: str
    ok: bool
    stage: str | None
    error: str | None
    time: str


def dry_run_slot(step_index: int | None = None) -> str:
    if step_index is None:
        return SCRIPT_DRY_RUN_SLOT
    return f"steps:{step_index}"


def code_sha256(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _short_dry_run_error(error: str | None) -> str | None:
    if error is None:
        return None
    if len(error) <= _DRY_RUN_ERROR_LIMIT:
        return error
    marker = "(line "
    idx = error.rfind(marker)
    if idx < 0:
        return error[:_DRY_RUN_ERROR_LIMIT] + "…"
    suffix = error[idx:]
    if len(suffix) >= _DRY_RUN_ERROR_LIMIT:
        return suffix[:_DRY_RUN_ERROR_LIMIT] + "…"
    budget = _DRY_RUN_ERROR_LIMIT - len(suffix)
    return error[:budget] + "…" + suffix


def _row_to_dry_run(row: sqlite3.Row) -> ScriptDryRunRow:
    return ScriptDryRunRow(
        session_id=row["session_id"],
        slot=row["slot"],
        sha256=row["sha256"],
        ok=bool(row["ok"]),
        stage=row["stage"],
        error=row["error"],
        time=row["ran_at"],
    )


def upsert_script_dry_run(
    db: Database,
    *,
    session_id: str,
    slot: str,
    sha256: str,
    ok: bool,
    stage: str | None = None,
    error: str | None = None,
) -> ScriptDryRunRow:
    now = _now_iso()
    short_error = _short_dry_run_error(error)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO session_script_dry_run("
            "session_id, slot, sha256, ok, stage, error, ran_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, slot) DO UPDATE SET "
            "sha256 = excluded.sha256, "
            "ok = excluded.ok, "
            "stage = excluded.stage, "
            "error = excluded.error, "
            "ran_at = excluded.ran_at",
            (
                session_id,
                slot,
                sha256,
                1 if ok else 0,
                stage,
                short_error,
                now,
            ),
        )
        row = conn.execute(
            "SELECT session_id, slot, sha256, ok, stage, error, ran_at "
            "FROM session_script_dry_run WHERE session_id = ? AND slot = ?",
            (session_id, slot),
        ).fetchone()
    assert row is not None
    return _row_to_dry_run(row)


def get_script_dry_run(
    db: Database, session_id: str, slot: str
) -> ScriptDryRunRow | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT session_id, slot, sha256, ok, stage, error, ran_at "
            "FROM session_script_dry_run WHERE session_id = ? AND slot = ?",
            (session_id, slot),
        ).fetchone()
    return _row_to_dry_run(row) if row is not None else None


def list_script_dry_runs(db: Database, session_id: str) -> list[ScriptDryRunRow]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT session_id, slot, sha256, ok, stage, error, ran_at "
            "FROM session_script_dry_run WHERE session_id = ? "
            "ORDER BY slot",
            (session_id,),
        ).fetchall()
    return [_row_to_dry_run(r) for r in rows]


def has_green_script_dry_run(
    db: Database, session_id: str, code: str, *, slot: str
) -> bool:
    digest = code_sha256(code)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM session_script_dry_run "
            "WHERE session_id = ? AND slot = ? AND sha256 = ? AND ok = 1 "
            "LIMIT 1",
            (session_id, slot, digest),
        ).fetchone()
    return row is not None
