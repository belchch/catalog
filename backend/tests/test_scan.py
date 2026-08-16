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


def test_scan_skips_export_dir(db: Database, tmp_path: Path) -> None:
    from catalog.documents.export_docx import render_docx

    export = tmp_path / "export"
    export.mkdir()
    (export / "out.docx").write_bytes(render_docx("# Hi\n\nbody"))
    (tmp_path / "keep.md").write_text("x", encoding="utf-8")

    report = scan_workspace(db, tmp_path)
    assert report.added == ["keep.md"]
    assert "export/out.docx" not in report.added
    again = scan_workspace(db, tmp_path)
    assert again.added == []
    assert again.updated == []


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
    assert set(report.added) == {"sub/deep/note.md", "table.csv"}

    again = scan_workspace(db, tmp_path)
    assert again.added == []
    assert again.updated == []
    assert again.renamed == []
    assert again.removed == []


def test_unchanged_rescan_skips_file_hashing(
    db: Database, tmp_path: Path, monkeypatch
) -> None:
    from catalog.documents import scan as scan_mod

    ingest_file(db, tmp_path, filename="note.md", content=b"stable")
    calls: list[Path] = []

    def _boom(path: Path) -> str:
        calls.append(path)
        raise AssertionError("hash should not run for unchanged files")

    monkeypatch.setattr(scan_mod, "_hash_file", _boom)
    report = scan_workspace(db, tmp_path)
    assert report.added == []
    assert report.updated == []
    assert calls == []


def test_hash_file_matches_full_digest(tmp_path: Path) -> None:
    import hashlib

    from catalog.documents.scan import _hash_file

    path = tmp_path / "doc.bin"
    payload = b"x" * (1024 * 1024 + 17)
    path.write_bytes(payload)
    assert _hash_file(path) == hashlib.sha256(payload).hexdigest()


def test_scan_does_not_delete_hidden_indexed_file(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename=".notes.md", content=b"keep me")
    assert row.path == ".notes.md"
    hidden = tmp_path / row.path
    assert hidden.is_file()

    report = scan_workspace(db, tmp_path)
    assert report.removed == []
    assert get_document(db, row.id) is not None
    assert hidden.is_file()
    assert hidden.read_bytes() == b"keep me"


def test_scan_rename_keeps_id_and_session(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="old.md", content=b"same-bytes")
    session_id = create_session(db)
    attach_documents(db, session_id, [row.id])

    src = tmp_path / "old.md"
    dest = tmp_path / "renamed.md"
    src.rename(dest)

    report = scan_workspace(db, tmp_path)
    assert report.renamed == ["old.md → renamed.md"]
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
    assert report.updated == ["note.md"]
    refreshed = get_document(db, row.id)
    assert refreshed is not None
    assert refreshed.content_hash != row.content_hash


def test_scan_backfills_empty_content_hash(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="note.md", content=b"same")
    with db.connect() as conn:
        conn.execute(
            "UPDATE document SET content_hash = NULL WHERE id = ?",
            (row.id,),
        )
    cleared = get_document(db, row.id)
    assert cleared is not None
    assert not cleared.content_hash

    report = scan_workspace(db, tmp_path)
    assert report.updated == []
    assert report.added == []
    refreshed = get_document(db, row.id)
    assert refreshed is not None
    assert refreshed.content_hash
    assert refreshed.content_hash == row.content_hash


def test_scan_rename_without_content_hash_keeps_id(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="old.md", content=b"same-bytes")
    session_id = create_session(db)
    attach_documents(db, session_id, [row.id])
    with db.connect() as conn:
        conn.execute(
            "UPDATE document SET content_hash = NULL WHERE id = ?",
            (row.id,),
        )
    (tmp_path / "old.md").rename(tmp_path / "renamed.md")

    report = scan_workspace(db, tmp_path)
    assert report.renamed == ["old.md → renamed.md"]
    assert report.added == []
    assert report.removed == []
    updated = get_document(db, row.id)
    assert updated is not None
    assert updated.path == "renamed.md"
    assert updated.content_hash
    assert [d.id for d in list_session_documents(db, session_id)] == [row.id]


def test_scan_removes_missing(db: Database, tmp_path: Path) -> None:
    kept = ingest_file(db, tmp_path, filename="keep.md", content=b"keep")
    gone = ingest_file(db, tmp_path, filename="gone.md", content=b"gone")
    (tmp_path / gone.path).unlink()

    report = scan_workspace(db, tmp_path)
    assert report.removed == [gone.path]
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
