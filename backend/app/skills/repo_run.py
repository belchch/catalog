"""Repository for the ``skill_run`` table.

A skill_run row tracks a single application of a skill to an input document:
its status (``running``/``ok``/``failed``), the produced result document, and
the full agent trace serialized as ``trace_json`` for later inspection.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.agent.trace import Trace
from app.storage.db import Database


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run(
    db: Database,
    *,
    skill_id: str,
    session_id: str | None,
    input_doc_id: str | None,
) -> str:
    """Insert a skill_run row with ``status='running'`` and return its id."""
    run_id = uuid.uuid4().hex
    now = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO skill_run(id, skill_id, session_id, input_doc_id, "
            "output_doc_id, status, trace_json, started_at, ended_at) "
            "VALUES (?, ?, ?, ?, NULL, 'running', NULL, ?, NULL)",
            (run_id, skill_id, session_id, input_doc_id, now),
        )
    return run_id


def finish_run(
    db: Database,
    run_id: str,
    *,
    status: str,
    output_doc_id: str | None,
    trace: Trace,
) -> None:
    """Mark a run finished: set status, output doc, trace, and ended_at."""
    now = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "UPDATE skill_run SET status = ?, output_doc_id = ?, "
            "trace_json = ?, ended_at = ? WHERE id = ?",
            (status, output_doc_id, trace.to_json(), now, run_id),
        )


def get_run(db: Database, run_id: str) -> dict | None:
    """Fetch a skill_run row as a dict, or ``None`` if not found."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, skill_id, session_id, input_doc_id, output_doc_id, "
            "status, trace_json, started_at, ended_at "
            "FROM skill_run WHERE id = ?",  # noqa: S608
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "skill_id": row["skill_id"],
        "session_id": row["session_id"],
        "input_doc_id": row["input_doc_id"],
        "output_doc_id": row["output_doc_id"],
        "status": row["status"],
        "trace_json": row["trace_json"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
    }
