"""Tests for skill materialization/scan (ADR-0022 review fixes)."""

from __future__ import annotations

import json
from pathlib import Path

from app.skills.config import SkillConfig
from app.skills.repo_skill import (
    SkillRecord,
    _insert_skill_row,
    get_skill,
    materialize_skill,
    scan_skills,
    skill_file_relpath,
)
from app.storage.db import Database


def _record(**overrides) -> SkillRecord:
    config = SkillConfig(
        name=overrides.get("name", "Alpha"),
        description="test",
        system_prompt="do the thing",
        allowed_tools=["read_document"],
        model="test/model",
    )
    defaults = dict(
        id="f5608daa1234abcd",
        name="Alpha",
        description="test",
        status="committed",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        config=config,
    )
    defaults.update(overrides)
    return SkillRecord(**defaults)


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "t.db"))
    db.init_schema()
    return db


def test_materialize_skill_writes_expected_path(tmp_path: Path) -> None:
    record = _record()

    rel_path, removed = materialize_skill(tmp_path, record)

    assert rel_path == skill_file_relpath(record)
    assert removed == []
    assert (tmp_path / rel_path).is_file()


def test_materialize_skill_removes_stale_file_on_rename(tmp_path: Path) -> None:
    original = _record(name="Alpha")
    first_path, _ = materialize_skill(tmp_path, original)
    assert (tmp_path / first_path).is_file()

    renamed = _record(name="Zulu", updated_at="2026-01-02T00:00:00+00:00")
    new_path, removed = materialize_skill(tmp_path, renamed)

    assert new_path != first_path
    assert removed == [first_path]
    assert not (tmp_path / first_path).exists()
    assert (tmp_path / new_path).is_file()


def test_scan_skills_rebuilds_from_single_file(tmp_path: Path) -> None:
    db = _db(tmp_path)
    record = _record()
    materialize_skill(tmp_path, record)

    result = scan_skills(db, tmp_path)

    assert result == {"loaded": 1}


def test_scan_skills_does_not_clobber_existing_draft(tmp_path: Path) -> None:
    """An in-progress SQLite draft edit must survive a rescan (ADR-0022)."""
    db = _db(tmp_path)
    committed_payload = {
        "id": "f5608daa1234abcd",
        "name": "Alpha",
        "description": "test",
        "status": "draft",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-05T00:00:00+00:00",
        "config": {
            "name": "Alpha (edited)",
            "kind": "agent",
            "description": "test",
            "system_prompt": "NEW PROMPT",
            "allowed_tools": ["read_document"],
            "model": "test/model",
        },
    }
    _insert_skill_row(db, committed_payload)
    materialize_skill(tmp_path, _record())  # last-committed file on disk

    result = scan_skills(db, tmp_path)

    assert result == {"loaded": 0}


def test_scan_skills_picks_freshest_file_on_duplicate_id(tmp_path: Path) -> None:
    """Two files claiming the same id: newest updated_at wins, not alpha order."""
    db = _db(tmp_path)
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    old = _record(name="Alpha", updated_at="2026-01-01T00:00:00+00:00")
    new = _record(name="Zulu", updated_at="2026-01-02T00:00:00+00:00")

    def _write(record) -> Path:
        path = tmp_path / skill_file_relpath(record)
        path.write_text(
            json.dumps(
                {
                    "id": record.id,
                    "name": record.name,
                    "description": record.description,
                    "status": record.status,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    "config": json.loads(record.config.to_json()),
                }
            ),
            encoding="utf-8",
        )
        return path

    # Write both directly (bypassing materialize_skill's own cleanup) to
    # simulate a stray leftover — e.g. a manual copy or a git merge.
    old_path = _write(old)
    new_path = _write(new)
    assert old_path.name < new_path.name  # alphabetically old sorts first

    scan_skills(db, tmp_path)

    row = get_skill(db, old.id)
    assert row is not None
    assert row.name == "Zulu"  # the fresher one, not the alphabetically-first
