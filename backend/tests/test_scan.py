"""Tests for the KB-repo scan/index rebuild (ADR-0022, ADR-0016 id stability)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.documents.scan import scan_repo
from app.storage.db import Database
from app.storage.repo_document import list_documents


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
