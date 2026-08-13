from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from catalog.storage.db import Database
from catalog.storage.schema import (
    APP_SCHEMA,
    APP_USER_VERSION,
    WORKSPACE_USER_VERSION,
)
from catalog.storage.workspace import (
    WorkspaceBusyError,
    WorkspaceManager,
    WorkspaceValidationError,
)


def _fresh_started_at() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture()
def app_db() -> Database:
    d = Database(":memory:")
    d.init_schema(APP_SCHEMA, APP_USER_VERSION, migrations=[])
    return d


def test_open_creates_index_db(tmp_path: Path, app_db: Database) -> None:
    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=type("S", (), {})())
    root = tmp_path / "folder"
    root.mkdir()
    db = manager.open(root, confirm_init=True)
    assert (root / ".catalog" / "index.db").is_file()
    assert db.user_version() == WORKSPACE_USER_VERSION
    assert manager.root == root.resolve()


def test_open_without_confirm_rejects_empty_folder(tmp_path: Path, app_db: Database) -> None:
    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=type("S", (), {})())
    root = tmp_path / "folder"
    root.mkdir()
    with pytest.raises(WorkspaceValidationError):
        manager.open(root, confirm_init=False)


def test_reopen_same_workspace_refreshes_scan(
    tmp_path: Path, app_db: Database
) -> None:
    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=type("S", (), {})())
    root = tmp_path / "folder"
    root.mkdir()
    manager.open(root, confirm_init=True)
    assert manager.last_scan is not None
    assert manager.last_scan.added == []
    (root / "late.md").write_text("hi", encoding="utf-8")
    manager.open(root, confirm_init=False)
    assert manager.last_scan is not None
    assert len(manager.last_scan.added) == 1
    with manager.current.connect() as conn:
        paths = [r["path"] for r in conn.execute("SELECT path FROM document").fetchall()]
    assert paths == ["late.md"]


def test_open_backs_up_existing_index(tmp_path: Path, app_db: Database) -> None:
    manager = WorkspaceManager()
    state = type("S", (), {})()
    manager.bind(app_db=app_db, app_state=state)
    root = tmp_path / "folder"
    root.mkdir()
    manager.open(root, confirm_init=True)
    manager.close()
    manager.open(root, confirm_init=False)
    backups = list((root / ".catalog" / "backups").glob("*.db"))
    assert len(backups) == 1


def test_incompatible_user_version_rejected(tmp_path: Path, app_db: Database) -> None:
    root = tmp_path / "folder"
    catalog = root / ".catalog"
    catalog.mkdir(parents=True)
    index = catalog / "index.db"
    bad = Database(str(index))
    bad.init_schema(user_version=999)
    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=type("S", (), {})())
    with pytest.raises(WorkspaceValidationError, match="incompatible"):
        manager.open(root, confirm_init=False)


def test_open_upgrades_older_user_version(tmp_path: Path, app_db: Database) -> None:
    root = tmp_path / "folder"
    catalog = root / ".catalog"
    catalog.mkdir(parents=True)
    index = catalog / "index.db"
    old = Database(str(index))
    old.init_schema(user_version=0)
    assert old.user_version() == 0
    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=type("S", (), {})())
    db = manager.open(root, confirm_init=False)
    assert db.user_version() == WORKSPACE_USER_VERSION
    assert manager.root == root.resolve()


def test_switch_blocked_while_run_active(tmp_path: Path, app_db: Database) -> None:
    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=type("S", (), {})())
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    db = manager.open(a, confirm_init=True)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO skill_run(id, skill_id, status, started_at) "
            "VALUES ('r1', 's1', 'running', ?)",
            (_fresh_started_at(),),
        )
    with pytest.raises(WorkspaceBusyError):
        manager.open(b, confirm_init=True)


def test_switch_blocked_while_run_pending(tmp_path: Path, app_db: Database) -> None:
    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=type("S", (), {})())
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    db = manager.open(a, confirm_init=True)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO skill_run(id, skill_id, status, started_at) "
            "VALUES ('r1', 's1', 'pending', ?)",
            (_fresh_started_at(),),
        )
    with pytest.raises(WorkspaceBusyError):
        manager.open(b, confirm_init=True)


def test_stale_pending_run_does_not_block_switch(
    tmp_path: Path, app_db: Database
) -> None:
    from catalog.skills.repo_run import get_run

    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=type("S", (), {})())
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    db = manager.open(a, confirm_init=True)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO skill_run(id, skill_id, status, started_at) "
            "VALUES ('r1', 's1', 'pending', '2020-01-01T00:00:00+00:00')"
        )
    other = manager.open(b, confirm_init=True)
    assert manager.root == b.resolve()
    assert other is manager.current
    stale = get_run(db, "r1")
    assert stale is not None
    assert stale["status"] == "cancelled"


def test_stale_running_run_does_not_block_switch(
    tmp_path: Path, app_db: Database
) -> None:
    from catalog.skills.repo_run import get_run

    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=type("S", (), {})())
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    db = manager.open(a, confirm_init=True)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO skill_run(id, skill_id, status, started_at) "
            "VALUES ('r1', 's1', 'running', '2020-01-01T00:00:00+00:00')"
        )
    other = manager.open(b, confirm_init=True)
    assert manager.root == b.resolve()
    assert other is manager.current
    stale = get_run(db, "r1")
    assert stale is not None
    assert stale["status"] == "cancelled"


def test_close_clears_current(tmp_path: Path, app_db: Database) -> None:
    state = type("S", (), {})()
    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=state)
    root = tmp_path / "folder"
    root.mkdir()
    manager.open(root, confirm_init=True)
    manager.close()
    assert manager.current is None
    assert manager.root is None
    assert state.workspace is None
    assert state.tools is None
    assert state.db is None
