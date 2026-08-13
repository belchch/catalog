"""Repository for the ``message`` table.

Stores the planner conversation turns (user / assistant / tool) so a session
history can be replayed when building a skill (step 06).
"""

from __future__ import annotations

from datetime import datetime, timezone

from catalog.storage.db import Database
from catalog.storage.repo_session import touch_session_activity


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_message(
    db: Database,
    *,
    session_id: str,
    role: str,
    content: str | None = None,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
) -> int:
    """Insert a message row and return its autoincrement id."""
    now = _now_iso()
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO message(session_id, role, content, tool_name, "
            "tool_call_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, tool_name, tool_call_id, now),
        )
    message_id = int(cur.lastrowid)
    touch_session_activity(db, session_id, role=role, content=content)
    return message_id


def list_messages(db: Database, session_id: str) -> list[dict]:
    """List messages for a session in insertion order (oldest first)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, session_id, role, content, tool_name, tool_call_id, "
            "created_at FROM message WHERE session_id = ? ORDER BY id",  # noqa: S608
            (session_id,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "session_id": r["session_id"],
            "role": r["role"],
            "content": r["content"],
            "tool_name": r["tool_name"],
            "tool_call_id": r["tool_call_id"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
