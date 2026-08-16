from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from catalog.storage.db import Database


@dataclass
class CustomCheckRow:
    id: str
    name: str
    prompt: str
    hidden: bool
    created_at: str
    updated_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_check(row) -> CustomCheckRow:
    return CustomCheckRow(
        id=row["id"],
        name=row["name"],
        prompt=row["prompt"],
        hidden=bool(row["hidden"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_custom_check(db: Database, *, name: str, prompt: str) -> CustomCheckRow:
    check_id = uuid.uuid4().hex
    now = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO custom_check(id, name, prompt, hidden, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            (check_id, name.strip(), prompt.strip(), now, now),
        )
    row = get_custom_check(db, check_id)
    if row is None:
        raise RuntimeError("custom check insert did not persist")
    return row


def get_custom_check(db: Database, check_id: str) -> CustomCheckRow | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, name, prompt, hidden, created_at, updated_at "
            "FROM custom_check WHERE id = ?",
            (check_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_check(row)


def list_custom_checks(
    db: Database, *, include_hidden: bool = False
) -> list[CustomCheckRow]:
    sql = (
        "SELECT id, name, prompt, hidden, created_at, updated_at "
        "FROM custom_check"
    )
    if not include_hidden:
        sql += " WHERE hidden = 0"
    sql += " ORDER BY created_at DESC"
    with db.connect() as conn:
        rows = conn.execute(sql).fetchall()
    return [_row_to_check(r) for r in rows]


def hide_custom_check(db: Database, check_id: str) -> bool:
    now = _now_iso()
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE custom_check SET hidden = 1, updated_at = ? WHERE id = ?",
            (now, check_id),
        )
        return int(cur.rowcount) == 1
