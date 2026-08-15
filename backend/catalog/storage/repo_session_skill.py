from __future__ import annotations

from datetime import datetime, timezone

from catalog.skills.config import SkillConfig
from catalog.skills.repo_skill import SkillRecord
from catalog.storage.db import Database


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def attach_skills(db: Database, session_id: str, skill_ids: list[str]) -> list[str]:
    if not skill_ids:
        return []
    now = _now_iso()
    skipped: list[str] = []
    seen_missing: set[str] = set()
    with db.connect() as conn:
        for skill_id in skill_ids:
            exists = conn.execute(
                "SELECT id FROM skill WHERE id = ?",
                (skill_id,),
            ).fetchone()
            if exists is None:
                if skill_id not in seen_missing:
                    skipped.append(skill_id)
                    seen_missing.add(skill_id)
                continue
            conn.execute(
                "INSERT OR IGNORE INTO session_skill(session_id, skill_id, attached_at) "
                "VALUES (?, ?, ?)",
                (session_id, skill_id, now),
            )
    return skipped


def detach_skills(db: Database, session_id: str, skill_ids: list[str]) -> int:
    if not skill_ids:
        return 0
    placeholders = ", ".join("?" for _ in skill_ids)
    with db.connect() as conn:
        cur = conn.execute(
            f"DELETE FROM session_skill "
            f"WHERE session_id = ? AND skill_id IN ({placeholders})",
            (session_id, *skill_ids),
        )
        return int(cur.rowcount)


def list_session_skills(db: Database, session_id: str) -> list[SkillRecord]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT s.id, s.name, s.description, s.config_json, s.status, "
            "s.created_at, s.updated_at "
            "FROM session_skill ss "
            "JOIN skill s ON s.id = ss.skill_id "
            "WHERE ss.session_id = ? "
            "ORDER BY ss.attached_at, s.created_at",
            (session_id,),
        ).fetchall()
    return [
        SkillRecord(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            status=r["status"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            config=SkillConfig.from_json(r["config_json"]),
        )
        for r in rows
    ]
