from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.storage.db import Database


@dataclass
class DocumentRow:
    id: str
    title: str
    path: str
    kind: str
    created_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_document(row: sqlite3.Row) -> DocumentRow:
    return DocumentRow(
        id=row["id"],
        title=row["title"],
        path=row["path"],
        kind=row["kind"],
        created_at=row["created_at"],
    )


_SELECT_COLS = "id, title, path, kind, created_at"


def create_document(
    db: Database,
    *,
    title: str,
    path: str,
    kind: str,
    doc_id: str | None = None,
) -> DocumentRow:
    """Insert a document row and return it.

    ``doc_id`` is generated (uuid4 hex) when not supplied. ``ingest_file`` passes
    an explicit id so the stored ``path`` (which embeds the id) and the row id
    stay in sync; standalone callers (e.g. skill results in step 05) rely on the
    generated id.
    """
    if doc_id is None:
        doc_id = uuid.uuid4().hex
    created_at = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO document(id, title, path, kind, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (doc_id, title, path, kind, created_at),
        )
    return DocumentRow(id=doc_id, title=title, path=path, kind=kind, created_at=created_at)


def get_document(db: Database, doc_id: str) -> DocumentRow | None:
    with db.connect() as conn:
        row = conn.execute(
            f"SELECT {_SELECT_COLS} FROM document WHERE id = ?",  # noqa: S608
            (doc_id,),
        ).fetchone()
    return _row_to_document(row) if row is not None else None


def list_documents(db: Database) -> list[DocumentRow]:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT {_SELECT_COLS} FROM document ORDER BY created_at"  # noqa: S608
        ).fetchall()
    return [_row_to_document(r) for r in rows]


def list_documents_by_kind(db: Database, kind: str) -> list[DocumentRow]:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT {_SELECT_COLS} FROM document WHERE kind = ? "  # noqa: S608
            "ORDER BY created_at",
            (kind,),
        ).fetchall()
    return [_row_to_document(r) for r in rows]
