"""Tests for the KB-repo scan/index rebuild (ADR-0022, ADR-0016 id stability)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.documents.scan import (
    DangerousEmptyScanError,
    guard_not_switching_to_empty_repo,
    guard_repo_not_missing,
    scan_repo,
)
from app.storage.db import Database
from app.storage.repo_document import create_document, list_documents


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "t.db"))
    db.init_schema()
    return db


def test_scan_empty_repo(tmp_path: Path) -> None:
    db = _db(tmp_path)

    summary = scan_repo(db, tmp_path)

    assert summary.added == 0
    assert list_documents(db) == []


def test_scan_adds_new_file(tmp_path: Path) -> None:
    db = _db(tmp_path)
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "note.md").write_text("hello", encoding="utf-8")

    summary = scan_repo(db, tmp_path)

    assert summary.added == 1
    docs = list_documents(db)
    assert len(docs) == 1
    assert docs[0].path == "documents/note.md"
    assert docs[0].kind == "md"


def test_scan_keeps_id_on_modification(tmp_path: Path) -> None:
    db = _db(tmp_path)
    (tmp_path / "documents").mkdir()
    f = tmp_path / "documents" / "note.md"
    f.write_text("hello", encoding="utf-8")
    scan_repo(db, tmp_path)
    original_id = list_documents(db)[0].id

    time.sleep(0.01)
    f.write_text("hello world, longer now", encoding="utf-8")
    os.utime(f, None)
    summary = scan_repo(db, tmp_path)

    docs = list_documents(db)
    assert summary.updated == 1
    assert summary.added == 0
    assert len(docs) == 1
    assert docs[0].id == original_id


def test_scan_removes_missing_file(tmp_path: Path) -> None:
    db = _db(tmp_path)
    (tmp_path / "documents").mkdir()
    f = tmp_path / "documents" / "note.md"
    f.write_text("hello", encoding="utf-8")
    scan_repo(db, tmp_path)

    f.unlink()
    summary = scan_repo(db, tmp_path)

    assert summary.removed == 1
    assert list_documents(db) == []


def test_scan_skips_unsupported_format(tmp_path: Path) -> None:
    db = _db(tmp_path)
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "note.exe").write_bytes(b"\x00\x01")

    summary = scan_repo(db, tmp_path)

    assert summary.skipped == 1
    assert list_documents(db) == []


def test_scan_indexes_results_as_result_md(tmp_path: Path) -> None:
    db = _db(tmp_path)
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "run-output.md").write_text("result", encoding="utf-8")

    summary = scan_repo(db, tmp_path)

    assert summary.added == 1
    assert list_documents(db)[0].kind == "result_md"


def test_scan_skips_broken_symlink_instead_of_crashing(tmp_path: Path) -> None:
    db = _db(tmp_path)
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "good.md").write_text("hello", encoding="utf-8")
    broken = tmp_path / "documents" / "broken.md"
    broken.symlink_to(tmp_path / "documents" / "does-not-exist.md")

    summary = scan_repo(db, tmp_path)

    assert summary.added == 1  # good.md
    assert summary.skipped == 1  # broken.md — stat() failed, not a crash
    assert len(list_documents(db)) == 1


def test_guard_allows_deleting_the_last_file_in_an_existing_repo(tmp_path: Path) -> None:
    """The repo directory itself still exists — this is routine reconcile,
    not the "path vanished" danger guard_repo_not_missing exists for."""
    db = _db(tmp_path)
    (tmp_path / "documents").mkdir()
    f = tmp_path / "documents" / "note.md"
    f.write_text("hello", encoding="utf-8")
    scan_repo(db, tmp_path)
    f.unlink()

    guard_repo_not_missing(tmp_path, db)  # must not raise
    summary = scan_repo(db, tmp_path)

    assert summary.removed == 1


def test_guard_refuses_when_repo_path_is_missing_but_index_is_not(tmp_path: Path) -> None:
    db = _db(tmp_path)
    create_document(db, title="x", path="documents/x.md", kind="md")
    missing_path = tmp_path / "does-not-exist-yet"

    with pytest.raises(DangerousEmptyScanError):
        guard_repo_not_missing(missing_path, db)


def test_guard_force_bypasses_the_check(tmp_path: Path) -> None:
    db = _db(tmp_path)
    create_document(db, title="x", path="documents/x.md", kind="md")
    missing_path = tmp_path / "does-not-exist-yet"

    guard_repo_not_missing(missing_path, db, force=True)  # must not raise


def test_guard_allows_missing_path_when_index_is_already_empty(tmp_path: Path) -> None:
    db = _db(tmp_path)
    missing_path = tmp_path / "does-not-exist-yet"

    guard_repo_not_missing(missing_path, db)  # nothing to lose — must not raise


# --- switching to an existing but empty repo (review follow-up) ------------


def _seed_indexed_repo(tmp_path: Path, name: str) -> tuple[Database, Path]:
    db = _db(tmp_path)
    root = tmp_path / name
    (root / "documents").mkdir(parents=True)
    (root / "documents" / "note.md").write_text("hello", encoding="utf-8")
    scan_repo(db, root)
    assert len(list_documents(db)) == 1
    return db, root


def test_guard_refuses_switch_to_an_existing_but_empty_directory(tmp_path: Path) -> None:
    """The path exists, so guard_repo_not_missing sees nothing wrong — but
    scanning it would still reconcile the entire index away."""
    db, _current = _seed_indexed_repo(tmp_path, "kb1")
    empty = tmp_path / "kb2"
    empty.mkdir()

    guard_repo_not_missing(empty, db)  # existing path — the old guard passes
    with pytest.raises(DangerousEmptyScanError):
        guard_not_switching_to_empty_repo(empty, db)


def test_guard_refuses_switch_to_a_repo_holding_only_unindexable_files(
    tmp_path: Path,
) -> None:
    db, _current = _seed_indexed_repo(tmp_path, "kb1")
    empty = tmp_path / "kb2"
    (empty / "documents").mkdir(parents=True)
    (empty / "documents" / "notes.txt").write_text("not an indexed kind", encoding="utf-8")

    with pytest.raises(DangerousEmptyScanError):
        guard_not_switching_to_empty_repo(empty, db)


def test_guard_allows_switch_to_a_repo_that_holds_documents(tmp_path: Path) -> None:
    db, _current = _seed_indexed_repo(tmp_path, "kb1")
    other = tmp_path / "kb2"
    (other / "documents").mkdir(parents=True)
    (other / "documents" / "other.md").write_text("real content", encoding="utf-8")

    guard_not_switching_to_empty_repo(other, db)  # a real KB — must not raise


def test_guard_allows_reconnecting_to_the_same_now_empty_repo(tmp_path: Path) -> None:
    """Same path, last document deleted — routine reconcile, not a switch."""
    db, current = _seed_indexed_repo(tmp_path, "kb1")
    (current / "documents" / "note.md").unlink()

    guard_not_switching_to_empty_repo(current, db, current_root=str(current))
    assert scan_repo(db, current).removed == 1


def test_guard_allows_switch_to_empty_repo_when_index_is_empty(tmp_path: Path) -> None:
    db = _db(tmp_path)
    empty = tmp_path / "kb2"
    empty.mkdir()

    guard_not_switching_to_empty_repo(empty, db)  # nothing to lose


def test_guard_switch_force_bypasses_the_check(tmp_path: Path) -> None:
    db, _current = _seed_indexed_repo(tmp_path, "kb1")
    empty = tmp_path / "kb2"
    empty.mkdir()

    guard_not_switching_to_empty_repo(empty, db, force=True)  # must not raise
