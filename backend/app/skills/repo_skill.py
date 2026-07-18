"""Repository for the ``skill`` table.

A skill row stores the :class:`~app.skills.config.SkillConfig` verbatim as
``config_json`` (ADR-0002: a committed skill is fully reproducible from its
row). ``get_skill`` returns a dataclass carrying both the persisted metadata
(id/status/name/description) and the deserialized config, so callers in steps
06/08 can read every field from a single object.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import cast

from app.skills.config import SkillConfig, compute_tags
from app.skills.repo_run import delete_runs_for_skill
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

    Each dict includes ``kind`` and ``tags`` (parsed from ``config_json``) so
    the API can surface the skill type and capability tags (CATALOG-8) without
    a separate config fetch.
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
            config = SkillConfig.from_json(r["config_json"])
            config_kind = config.kind
            config_tags = compute_tags(config)
            config_input_arity = config.input_arity
            config_model = config.model or None
            config_provider = config.provider or None
            config_reasoning = config.reasoning or None
        except (ValueError, KeyError):
            # Unparseable/legacy config: degrade to the agent defaults so the
            # row still renders on the UI with an ``ai`` tag.
            config_kind = "agent"
            config_tags = ["ai"]
            config_input_arity = None
            config_model = None
            config_provider = None
            config_reasoning = None
        result.append(
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "status": r["status"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "kind": config_kind,
                "tags": config_tags,
                "input_arity": config_input_arity,
                "model": config_model,
                "provider": config_provider,
                "reasoning": config_reasoning,
            }
        )
    return result


def update_skill(
    db: Database,
    skill_id: str,
    *,
    name: str,
    description: str,
    config: SkillConfig,
    status: str | None = None,
) -> SkillRecord | None:
    """Fully overwrite name/description/config on an existing skill (CATALOG-17 edit).

    Unlike :func:`update_skill_config` (a narrow model/provider/reasoning
    override for the settings modal), this replaces the whole frozen config —
    the counterpart of :func:`create_skill` for the "edit an existing skill"
    flow. ``status`` is only applied when given (edit-after-committed drops
    back to ``draft``; a draft-edited skill stays draft). Returns ``None`` if
    the skill does not exist.
    """
    record = get_skill(db, skill_id)
    if record is None:
        return None
    new_status = status if status is not None else record.status
    now = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "UPDATE skill SET name = ?, description = ?, config_json = ?, "
            "status = ?, updated_at = ? WHERE id = ?",
            (name, description, config.to_json(), new_status, now, skill_id),
        )
    return replace(
        record,
        name=name,
        description=description,
        config=config,
        status=new_status,
        updated_at=now,
    )


def update_status(db: Database, skill_id: str, status: str) -> None:
    """Transition a skill's status (e.g. ``draft`` -> ``committed``)."""
    now = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "UPDATE skill SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, skill_id),
        )


def delete_skill(db: Database, skill_id: str) -> bool:
    if get_skill(db, skill_id) is None:
        return False
    delete_runs_for_skill(db, skill_id)
    with db.connect() as conn:
        conn.execute(
            "UPDATE session SET skill_id = NULL WHERE skill_id = ?",
            (skill_id,),
        )
        conn.execute("DELETE FROM skill WHERE id = ?", (skill_id,))
    return True


_UNSET = object()


def update_skill_config(
    db: Database,
    skill_id: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    reasoning: str | None = None,
    input_arity: int | None | object = _UNSET,
    name: str | None = None,
) -> SkillRecord | None:
    """Override selected config fields and persist (CATALOG-6 settings modal).

    For ``model``/``provider``/``reasoning``/``name``, only non-``None``
    arguments are applied. For ``input_arity``, pass an explicit value
    (including ``None`` for the document-list mode) or omit the argument to
    leave it unchanged. When ``name`` is set, both the ``skill.name`` column
    and ``config.name`` are updated. Returns the updated record (or ``None``
    if the skill does not exist). Intended for ``draft`` skills before
    commit; ``name`` alone is also used for committed rename (CATALOG-30).
    """
    record = get_skill(db, skill_id)
    if record is None:
        return None
    config = record.config
    if model is not None:
        config.model = model
    if provider is not None:
        config.provider = provider
    if reasoning is not None:
        config.reasoning = reasoning
    if input_arity is not _UNSET:
        config.input_arity = cast(int | None, input_arity)
    new_name = record.name
    if name is not None:
        config.name = name
        new_name = name
    now = _now_iso()
    with db.connect() as conn:
        if name is not None:
            conn.execute(
                "UPDATE skill SET name = ?, config_json = ?, updated_at = ? "
                "WHERE id = ?",
                (new_name, config.to_json(), now, skill_id),
            )
        else:
            conn.execute(
                "UPDATE skill SET config_json = ?, updated_at = ? WHERE id = ?",
                (config.to_json(), now, skill_id),
            )
    return replace(record, name=new_name, config=config, updated_at=now)
