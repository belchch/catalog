"""Repository for the ``skill_run`` table.

A skill_run row tracks a single application of a skill to one or more input
documents (CATALOG-4): its status (``running``/``ok``/``failed``), the produced
result document, and the full agent trace serialized as ``trace_json`` for
later inspection.

The list of input documents is stored as a JSON array in ``input_doc_ids``.
The legacy ``input_doc_id`` column is kept in sync (it always holds the first
input) so older readers and the existing ``RunOut.input_doc_id`` field keep
working.

CATALOG-18: ``persist`` records which output mode the run was started with
(``True`` = auto-create a ``result_md`` document on success, matching the
pre-CATALOG-18 behaviour; ``False`` = leave the result on screen only).
``result_text`` carries the raw agent/script output regardless of ``persist``
so a preview run can still be materialized into a document later via
``POST /runs/{id}/save``.

CATALOG-56: ``user_prompt`` is an optional runtime clarification for agent
skills; it is stored on the run at ``POST /apply`` and read back by the
WebSocket stream. Script skills ignore it.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from catalog.agent.trace import Trace
from catalog.storage.db import Database

PENDING_MAX_AGE_SECONDS = 15 * 60
RUNNING_MAX_AGE_SECONDS = 60 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run(
    db: Database,
    *,
    skill_id: str,
    session_id: str | None,
    input_doc_ids: list[str],
    persist: bool = True,
    user_prompt: str | None = None,
) -> str:
    if not input_doc_ids:
        raise ValueError("create_run requires at least one input document id")
    run_id = uuid.uuid4().hex
    now = _now_iso()
    first_doc_id = input_doc_ids[0]
    ids_json = json.dumps(list(input_doc_ids), ensure_ascii=False)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO skill_run(id, skill_id, session_id, input_doc_id, "
            "input_doc_ids, output_doc_id, status, trace_json, started_at, ended_at, "
            "persist, result_text, user_prompt) "
            "VALUES (?, ?, ?, ?, ?, NULL, 'pending', NULL, ?, NULL, ?, NULL, ?)",
            (
                run_id,
                skill_id,
                session_id,
                first_doc_id,
                ids_json,
                now,
                int(persist),
                user_prompt,
            ),
        )
    return run_id


def claim_run(db: Database, run_id: str) -> bool:
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE skill_run SET status = 'running' WHERE id = ? AND status = 'pending'",
            (run_id,),
        )
        return int(cur.rowcount) == 1


def finish_run(
    db: Database,
    run_id: str,
    *,
    status: str,
    output_doc_id: str | None,
    trace: Trace,
    result_text: str | None = None,
) -> None:
    now = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "UPDATE skill_run SET status = ?, output_doc_id = ?, "
            "trace_json = ?, ended_at = ?, result_text = ? WHERE id = ?",
            (status, output_doc_id, trace.to_json(), now, result_text, run_id),
        )


def set_output_doc_id(db: Database, run_id: str, output_doc_id: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE skill_run SET output_doc_id = ? WHERE id = ?",
            (output_doc_id, run_id),
        )


def delete_runs_for_skill(db: Database, skill_id: str) -> int:
    with db.connect() as conn:
        cur = conn.execute(
            "DELETE FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        )
        return int(cur.rowcount)


def _abandon_stale_runs(
    db: Database, *, status: str, max_age_seconds: int
) -> int:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    ).isoformat()
    now = _now_iso()
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE skill_run SET status = 'cancelled', ended_at = ? "
            "WHERE status = ? AND started_at < ?",
            (now, status, cutoff),
        )
        return int(cur.rowcount)


def abandon_stale_pending_runs(
    db: Database, *, max_age_seconds: int = PENDING_MAX_AGE_SECONDS
) -> int:
    return _abandon_stale_runs(
        db, status="pending", max_age_seconds=max_age_seconds
    )


def abandon_stale_running_runs(
    db: Database, *, max_age_seconds: int = RUNNING_MAX_AGE_SECONDS
) -> int:
    return _abandon_stale_runs(
        db, status="running", max_age_seconds=max_age_seconds
    )


def has_running_runs(db: Database) -> bool:
    abandon_stale_pending_runs(db)
    abandon_stale_running_runs(db)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM skill_run WHERE status IN ('pending', 'running') LIMIT 1"
        ).fetchone()
    return row is not None


def get_run(db: Database, run_id: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, skill_id, session_id, input_doc_id, input_doc_ids, "
            "output_doc_id, status, trace_json, started_at, ended_at, "
            "persist, result_text, user_prompt "
            "FROM skill_run WHERE id = ?",  # noqa: S608
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    raw_ids = row["input_doc_ids"]
    if raw_ids:
        try:
            input_doc_ids: list[str] = list(json.loads(raw_ids))
        except (json.JSONDecodeError, TypeError):
            input_doc_ids = [row["input_doc_id"]] if row["input_doc_id"] else []
    elif row["input_doc_id"]:
        input_doc_ids = [row["input_doc_id"]]
    else:
        input_doc_ids = []
    return {
        "id": row["id"],
        "skill_id": row["skill_id"],
        "session_id": row["session_id"],
        "input_doc_id": row["input_doc_id"],
        "input_doc_ids": input_doc_ids,
        "output_doc_id": row["output_doc_id"],
        "status": row["status"],
        "trace_json": row["trace_json"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "persist": bool(row["persist"]) if row["persist"] is not None else True,
        "result_text": row["result_text"],
        "user_prompt": row["user_prompt"],
    }
