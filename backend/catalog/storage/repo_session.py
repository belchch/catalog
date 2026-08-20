"""Repository for the ``session`` table.

A session is the planning conversation that precedes a skill: it is created in
``planning`` status and transitions to ``done`` once a skill is built from it.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from catalog.llm.timeout import DEFAULT_LLM_TIMEOUT_SECONDS
from catalog.storage.db import Database

_TITLE_MAX_LEN = 80

_SESSION_COLUMNS = (
    "id, status, created_at, skill_id, title, updated_at, llm_timeout_seconds"
)


@dataclass
class SessionRow:
    id: str
    status: str
    created_at: str
    skill_id: str | None = None
    title: str | None = None
    updated_at: str | None = None
    llm_timeout_seconds: int = DEFAULT_LLM_TIMEOUT_SECONDS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title_from_content(content: str) -> str:
    line = content.strip().splitlines()[0].strip() if content.strip() else ""
    if len(line) > _TITLE_MAX_LEN:
        return line[:_TITLE_MAX_LEN].rstrip() + "…"
    return line


def _row_to_session(row: sqlite3.Row) -> SessionRow:
    created_at = row["created_at"]
    updated_at = row["updated_at"] if "updated_at" in row.keys() else None
    if "llm_timeout_seconds" in row.keys() and row["llm_timeout_seconds"] is not None:
        timeout = int(row["llm_timeout_seconds"])
    else:
        timeout = DEFAULT_LLM_TIMEOUT_SECONDS
    return SessionRow(
        id=row["id"],
        status=row["status"],
        created_at=created_at,
        skill_id=row["skill_id"],
        title=row["title"] if "title" in row.keys() else None,
        updated_at=updated_at or created_at,
        llm_timeout_seconds=timeout,
    )


def create_session(
    db: Database, *, status: str = "planning", skill_id: str | None = None
) -> str:
    """Insert a session row and return its id.

    ``skill_id`` (CATALOG-17) marks this as an edit session for an existing
    skill; ``None`` (the default) is a regular new-skill planning session.
    """
    session_id = uuid.uuid4().hex
    now = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO session(id, status, created_at, skill_id, title, updated_at, "
            "llm_timeout_seconds) VALUES (?, ?, ?, ?, NULL, ?, ?)",
            (
                session_id,
                status,
                now,
                skill_id,
                now,
                DEFAULT_LLM_TIMEOUT_SECONDS,
            ),
        )
    return session_id


def get_session(db: Database, session_id: str) -> SessionRow | None:
    with db.connect() as conn:
        row = conn.execute(
            f"SELECT {_SESSION_COLUMNS} FROM session WHERE id = ?",
            (session_id,),
        ).fetchone()
    return _row_to_session(row) if row is not None else None


def get_session_by_skill_id(db: Database, skill_id: str) -> SessionRow | None:
    """Find the session linked to a draft skill via ``session.skill_id``.

    Only edit sessions (``POST /skills/{id}/edit``, CATALOG-17) set this
    column, so a skill that has never been through an edit session has no
    linked session and this returns ``None`` — callers must treat that as
    "nothing to sync", not an error (CATALOG-155). If several sessions ever
    point at the same skill (repeated edits without cleanup), the most
    recently touched one wins.
    """
    with db.connect() as conn:
        row = conn.execute(
            f"SELECT {_SESSION_COLUMNS} FROM session WHERE skill_id = ? "
            "ORDER BY COALESCE(updated_at, created_at) DESC, created_at DESC "
            "LIMIT 1",
            (skill_id,),
        ).fetchone()
    return _row_to_session(row) if row is not None else None


def list_sessions(
    db: Database,
    *,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> list[SessionRow]:
    params: list[object] = []
    if status is not None:
        sql = (
            f"SELECT {_SESSION_COLUMNS} "
            "FROM session WHERE status = ? "
            "ORDER BY COALESCE(updated_at, created_at) DESC, created_at DESC "
            "LIMIT ? OFFSET ?"
        )
        params.extend([status, limit, offset])
    else:
        sql = (
            f"SELECT {_SESSION_COLUMNS} "
            "FROM session "
            "ORDER BY COALESCE(updated_at, created_at) DESC, created_at DESC "
            "LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
    with db.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_session(r) for r in rows]


def delete_session(db: Database, session_id: str) -> bool:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM session WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM session_artifact WHERE session_id = ?", (session_id,))
        conn.execute(
            "DELETE FROM session_script_dry_run WHERE session_id = ?",
            (session_id,),
        )
        conn.execute("DELETE FROM session_document WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM session_skill WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM message WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM session WHERE id = ?", (session_id,))
    return True


def touch_session_activity(
    db: Database,
    session_id: str,
    *,
    role: str,
    content: str | None,
) -> None:
    now = _now_iso()
    with db.connect() as conn:
        if role == "user" and content:
            title = _title_from_content(content)
            if title:
                conn.execute(
                    "UPDATE session SET updated_at = ?, "
                    "title = COALESCE(title, ?) WHERE id = ?",
                    (now, title, session_id),
                )
                return
        conn.execute(
            "UPDATE session SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )


def update_session_status(db: Database, session_id: str, status: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE session SET status = ? WHERE id = ?",
            (status, session_id),
        )


def update_session_llm_timeout(
    db: Database, session_id: str, llm_timeout_seconds: int
) -> SessionRow | None:
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE session SET llm_timeout_seconds = ? WHERE id = ?",
            (llm_timeout_seconds, session_id),
        )
        if cur.rowcount == 0:
            return None
    return get_session(db, session_id)
