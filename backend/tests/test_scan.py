from __future__ import annotations

from pathlib import Path

from catalog.documents.ingest import ingest_file
from catalog.documents.scan import scan_workspace
from catalog.storage.db import Database
from catalog.storage.repo_document import get_document
from catalog.storage.repo_session import create_session
from catalog.storage.repo_session_document import attach_documents, list_session_documents
from catalog.storage.schema import (
    APP_SCHEMA,
    APP_USER_VERSION,
    WORKSPACE_USER_VERSION,
)
from catalog.storage.workspace import WorkspaceManager


def test_scan_indexes_nested_and_skips(db: Database, tmp_path: Path) -> None:
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    (nested / "note.md").write_text("# hi", encoding="utf-8")
    (tmp_path / "table.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "skip.exe").write_bytes(b"MZ")
    (tmp_path / ".secret.md").write_text("hidden", encoding="utf-8")
    catalog = tmp_path / ".catalog"
    catalog.mkdir()
    (catalog / "ignore.md").write_text("nope", encoding="utf-8")

    report = scan_workspace(db, tmp_path)
    assert len(report.added) == 2
    assert "skip.exe" in report.skipped
    assert ".secret.md" in report.skipped
    paths = {get_document(db, i).path for i in report.added}
    assert paths == {"sub/deep/note.md", "table.csv"}

    again = scan_workspace(db, tmp_path)
    assert again.added == []
    assert again.updated == []
    assert again.renamed == []
    assert again.removed == []


def test_scan_rename_keeps_id_and_session(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="old.md", content=b"same-bytes")
    session_id = create_session(db)
    attach_documents(db, session_id, [row.id])

    src = tmp_path / "old.md"
    dest = tmp_path / "renamed.md"
    src.rename(dest)

    report = scan_workspace(db, tmp_path)
    assert report.renamed == [row.id]
    assert report.added == []
    assert report.removed == []
    updated = get_document(db, row.id)
    assert updated is not None
    assert updated.path == "renamed.md"
    assert [d.id for d in list_session_documents(db, session_id)] == [row.id]


def test_scan_update_on_content_change(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="note.md", content=b"v1")
    path = tmp_path / "note.md"
    path.write_text("v2", encoding="utf-8")

    report = scan_workspace(db, tmp_path)
    assert report.updated == [row.id]
    refreshed = get_document(db, row.id)
    assert refreshed is not None
    assert refreshed.content_hash != row.content_hash


def test_scan_removes_missing(db: Database, tmp_path: Path) -> None:
    kept = ingest_file(db, tmp_path, filename="keep.md", content=b"keep")
    gone = ingest_file(db, tmp_path, filename="gone.md", content=b"gone")
    (tmp_path / gone.path).unlink()

    report = scan_workspace(db, tmp_path)
    assert report.removed == [gone.id]
    assert get_document(db, gone.id) is None
    assert get_document(db, kept.id) is not None


def test_open_workspace_runs_scan(tmp_path: Path) -> None:
    app_db = Database(":memory:")
    app_db.init_schema(APP_SCHEMA, APP_USER_VERSION, migrations=[])
    root = tmp_path / "ws"
    root.mkdir()
    (root / "hello.md").write_text("hi", encoding="utf-8")

    manager = WorkspaceManager()
    manager.bind(app_db=app_db, app_state=type("S", (), {})())
    db = manager.open(root, confirm_init=True)
    assert db.user_version() == WORKSPACE_USER_VERSION
    with db.connect() as conn:
        rows = conn.execute("SELECT path FROM document").fetchall()
    assert [r["path"] for r in rows] == ["hello.md"]
