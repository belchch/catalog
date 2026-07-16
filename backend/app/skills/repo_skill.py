"""Repository for the ``skill`` table.

A skill row stores the :class:`~app.skills.config.SkillConfig` verbatim as
``config_json`` (ADR-0002: a committed skill is fully reproducible from its
row). ``get_skill`` returns a dataclass carrying both the persisted metadata
(id/status/name/description) and the deserialized config, so callers in steps
06/08 can read every field from a single object.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.skills.config import SkillConfig
from app.storage.db import Database


@dataclass
class SkillRecord:
    """A skill row plus its deserialized config."""

    id: str
    name: str
    description: str | None
    status: str
    created_at: str
    updated_at: str
    config: SkillConfig


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_record(row: sqlite3.Row) -> SkillRecord:
    return SkillRecord(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        config=SkillConfig.from_json(row["config_json"]),
    )


def create_skill(
    db: Database,
    *,
    name: str,
    description: str,
    config: SkillConfig,
    status: str = "draft",
) -> str:
    """Insert a skill row and return its id."""
    skill_id = uuid.uuid4().hex
    now = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO skill(id, name, description, config_json, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (skill_id, name, description, config.to_json(), status, now, now),
        )
    return skill_id


def get_skill(db: Database, skill_id: str) -> SkillRecord | None:
    """Fetch a single skill by id, or ``None`` if not found."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, name, description, config_json, status, created_at, "
            "updated_at FROM skill WHERE id = ?",  # noqa: S608
            (skill_id,),
        ).fetchone()
    return _row_to_record(row) if row is not None else None


def list_skills(db: Database, status: str | None = None) -> list[dict]:
    """List skills, optionally filtered by status (newest first).

    Each dict includes ``kind`` (parsed from ``config_json``) so the API can
    surface the skill type without a separate config fetch.
    """
    with db.connect() as conn:
        if status is not None:
            rows = conn.execute(
                "SELECT id, name, description, config_json, status, created_at, "
                "updated_at FROM skill WHERE status = ? ORDER BY created_at DESC",  # noqa: S608
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, description, config_json, status, created_at, "
                "updated_at FROM skill ORDER BY created_at DESC"  # noqa: S608
            ).fetchall()
    result: list[dict] = []
    for r in rows:
        try:
            config_kind = json.loads(r["config_json"]).get("kind", "agent")
        except (ValueError, KeyError):
            config_kind = "agent"
        result.append(
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "status": r["status"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "kind": config_kind,
            }
        )
    return result


def update_status(db: Database, skill_id: str, status: str) -> None:
    """Transition a skill's status (e.g. ``draft`` -> ``committed``)."""
    now = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "UPDATE skill SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, skill_id),
        )
