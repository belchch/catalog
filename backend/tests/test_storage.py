from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from app.documents.extract import extract_text
from app.documents.ingest import ingest_file, slugify
from app.documents.tools import build_document_tools
from app.storage.db import Database
from app.storage.repo_document import (
    DocumentRow,
    create_document,
    get_document,
    list_documents,
    list_documents_by_kind,
)


@pytest.fixture()
def db() -> Database:
    d = Database(":memory:")
    d.init_schema()
    return d


def _table_names(db: Database) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r["name"] for r in rows}


def test_schema_creates_all_tables(db: Database) -> None:
    assert {
        "document",
        "session",
        "message",
        "skill",
        "skill_run",
    } <= _table_names(db)


def test_init_schema_is_idempotent(db: Database) -> None:
    db.init_schema()  # second run must not raise
    assert {
        "document",
        "session",
        "message",
        "skill",
        "skill_run",
    } <= _table_names(db)


def test_create_and_get_document(db: Database) -> None:
    row = create_document(db, title="T", path="documents/x.md", kind="md")
    assert isinstance(row, DocumentRow)
    assert len(row.id) == 32  # uuid4 hex
    assert row.title == "T"

    fetched = get_document(db, row.id)
    assert fetched is not None
    assert fetched.id == row.id
    assert fetched.kind == "md"
    assert fetched.path == "documents/x.md"

    assert get_document(db, "missing") is None


def test_list_documents_and_by_kind(db: Database) -> None:
    create_document(db, title="a", path="documents/a.md", kind="md")
    create_document(db, title="b", path="documents/b.md", kind="md")
    create_document(db, title="c", path="documents/c.docx", kind="docx")

    assert len(list_documents(db)) == 3
    assert len(list_documents_by_kind(db, "md")) == 2
    assert len(list_documents_by_kind(db, "docx")) == 1
    assert list_documents_by_kind(db, "result_md") == []


def test_ingest_md_and_read(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="note.md", content=b"# Hello\nworld")
    assert row.kind == "md"
    assert row.title == "note"
    # On-disk filename is a readable slug plus the id's short suffix.
    assert row.path == f"documents/note-{row.id[:8]}.md"
    # File written verbatim.
    assert (tmp_path / row.path).read_bytes() == b"# Hello\nworld"

    text = extract_text(str(tmp_path / row.path), row.kind)
    assert "Hello" in text
    assert text == "# Hello\nworld"


def test_ingest_docx_and_read(db: Database, tmp_path: Path) -> None:
    import docx

    doc = docx.Document()
    doc.add_paragraph("First paragraph")
    doc.add_paragraph("Second paragraph")
    src = tmp_path / "src.docx"
    doc.save(str(src))
    content = src.read_bytes()

    row = ingest_file(db, tmp_path, filename="report.docx", content=content)
    assert row.kind == "docx"
    assert row.title == "report"
    assert row.path == f"documents/report-{row.id[:8]}.docx"

    text = extract_text(str(tmp_path / row.path), row.kind)
    assert text == "First paragraph\nSecond paragraph"


def test_unsupported_format_raises(db: Database, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ingest_file(db, tmp_path, filename="file.pdf", content=b"%PDF-1.4")


def test_slugify_transliterates_cyrillic() -> None:
    assert slugify("Пример Документ") == "primer-dokument"


def test_slugify_sanitizes_spaces_and_special_chars() -> None:
    assert slugify("  My File!! (v2).final  ") == "my-file-v2-final"


def test_slugify_empty_or_blank_returns_empty() -> None:
    assert slugify("") == ""
    assert slugify("   ") == ""
    assert slugify("---") == ""


def test_slugify_caps_length() -> None:
    long_name = "a" * 100
    slug = slugify(long_name)
    assert len(slug) <= 60


def test_ingest_cyrillic_filename_uses_readable_slug(db: Database, tmp_path: Path) -> None:
    row = ingest_file(
        db, tmp_path, filename="Пример Документ.md", content=b"content"
    )
    assert row.title == "Пример Документ"
    assert row.path == f"documents/primer-dokument-{row.id[:8]}.md"
    assert (tmp_path / row.path).read_bytes() == b"content"


def test_ingest_blank_filename_falls_back_to_doc_id(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="   .md", content=b"content")
    assert row.path == f"documents/{row.id}.md"
    assert (tmp_path / row.path).read_bytes() == b"content"


def test_ingest_garbage_filename_falls_back_to_doc_id(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="@@@!!!.md", content=b"content")
    assert row.title == "@@@!!!"
    assert row.path == f"documents/{row.id}.md"
    assert (tmp_path / row.path).read_bytes() == b"content"


def test_ingest_primer_md_keeps_original_title(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="Пример.md", content=b"# hi")
    assert row.title == "Пример"
    assert row.path == f"documents/primer-{row.id[:8]}.md"
    assert not row.path.endswith(f"/{row.id}.md")


def test_ingest_path_id_prefix_matches_row_id(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="Отчёт по продажам.md", content=b"x")
    stem = row.path.removeprefix("documents/").removesuffix(".md")
    assert stem.endswith(row.id[:8])
    assert row.id.startswith(row.id[:8])


def test_ingest_docx_extension_still_validated(db: Database, tmp_path: Path) -> None:
    import docx

    doc = docx.Document()
    doc.add_paragraph("Текст")
    src = tmp_path / "src.docx"
    doc.save(str(src))

    row = ingest_file(
        db, tmp_path, filename="Годовой отчёт.docx", content=src.read_bytes()
    )
    assert row.kind == "docx"
    assert row.path == f"documents/godovoy-otchyot-{row.id[:8]}.docx"


def test_read_unknown_doc_error(db: Database, tmp_path: Path) -> None:
    reg = build_document_tools(db, tmp_path)
    entry = reg.get("read_document")
    assert entry is not None
    _, read_fn = entry

    async def _run() -> dict:
        return await read_fn(doc_id="nope")

    assert asyncio.run(_run()) == {"error": "document not found"}


def test_list_documents_tool(db: Database, tmp_path: Path) -> None:
    ingest_file(db, tmp_path, filename="a.md", content=b"a")
    ingest_file(db, tmp_path, filename="b.md", content=b"b")
    reg = build_document_tools(db, tmp_path)
    entry = reg.get("list_documents")
    assert entry is not None
    _, list_fn = entry

    async def _run() -> list[dict]:
        return await list_fn()

    items = asyncio.run(_run())
    assert len(items) == 2
    assert {it["kind"] for it in items} == {"md"}
    assert all({"id", "title", "kind"} == set(it) for it in items)


def test_read_document_tool_md(db: Database, tmp_path: Path) -> None:
    row = ingest_file(db, tmp_path, filename="note.md", content=b"body text")
    reg = build_document_tools(db, tmp_path)
    entry = reg.get("read_document")
    assert entry is not None
    _, read_fn = entry

    async def _run() -> dict:
        return await read_fn(doc_id=row.id)

    result = asyncio.run(_run())
    assert result == {"title": "note", "kind": "md", "text": "body text"}


def test_document_tools_registered(db: Database, tmp_path: Path) -> None:
    reg = build_document_tools(db, tmp_path)
    assert reg.names() == ["list_documents", "read_document"]

    specs = {s.name: s for s in reg.specs()}
    assert specs["list_documents"].parameters == {"type": "object", "properties": {}}
    assert specs["read_document"].parameters == {
        "type": "object",
        "properties": {"doc_id": {"type": "string"}},
        "required": ["doc_id"],
    }


def test_row_factory_is_set(db: Database) -> None:
    # connect() must yield connections whose rows are sqlite3.Row.
    with db.connect() as conn:
        assert conn.row_factory is sqlite3.Row
