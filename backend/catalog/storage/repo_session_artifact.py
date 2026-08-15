from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from catalog.storage.db import Database

ARTIFACT_TYPES = ("prompt", "script", "meta", "steps")
ARTIFACT_SOURCES = ("llm", "user")


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
