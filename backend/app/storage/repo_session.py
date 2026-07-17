"""Repository for the ``session`` table.

A session is the planning conversation that precedes a skill: it is created in
``planning`` status and transitions to ``done`` once a skill is built from it.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.storage.db import Database


@dataclass
class SessionRow:
    id: str
    status: str
    created_at: str
    # Set when this session is editing an existing skill (CATALOG-17); ``None``
    # for a regular "create a new skill" planning session.
    skill_id: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_session(row: sqlite3.Row) -> SessionRow:
    return SessionRow(
        id=row["id"],
        status=row["status"],
        created_at=row["created_at"],
        skill_id=row["skill_id"],
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
            "INSERT INTO session(id, status, created_at, skill_id) VALUES (?, ?, ?, ?)",
            (session_id, status, now, skill_id),
        )
    return session_id


def get_session(db: Database, session_id: str) -> SessionRow | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, status, created_at, skill_id FROM session WHERE id = ?",  # noqa: S608
            (session_id,),
        ).fetchone()
    return _row_to_session(row) if row is not None else None


def update_session_status(db: Database, session_id: str, status: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE session SET status = ? WHERE id = ?",
            (status, session_id),
        )
