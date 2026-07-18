from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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


def _nullify_skill_run_refs(conn: sqlite3.Connection, doc_id: str) -> None:
    conn.execute(
        "UPDATE skill_run SET output_doc_id = NULL WHERE output_doc_id = ?",
        (doc_id,),
    )
    rows = conn.execute(
        "SELECT id, input_doc_id, input_doc_ids FROM skill_run"
    ).fetchall()
    for row in rows:
        raw_ids = row["input_doc_ids"]
        ids: list[str]
        if raw_ids:
            try:
                ids = list(json.loads(raw_ids))
            except (json.JSONDecodeError, TypeError):
                ids = [row["input_doc_id"]] if row["input_doc_id"] else []
        elif row["input_doc_id"]:
            ids = [row["input_doc_id"]]
        else:
            ids = []
        if doc_id not in ids and row["input_doc_id"] != doc_id:
            continue
        new_ids = [i for i in ids if i != doc_id]
        first = new_ids[0] if new_ids else None
        conn.execute(
            "UPDATE skill_run SET input_doc_id = ?, input_doc_ids = ? WHERE id = ?",
            (
                first,
                json.dumps(new_ids, ensure_ascii=False) if new_ids else None,
                row["id"],
            ),
        )


def delete_document(
    db: Database,
    workspace_dir: str | Path,
    doc_id: str,
) -> DocumentRow | None:
    workspace = Path(workspace_dir)
    with db.connect() as conn:
        row = conn.execute(
            f"SELECT {_SELECT_COLS} FROM document WHERE id = ?",  # noqa: S608
            (doc_id,),
        ).fetchone()
        if row is None:
            return None
        doc = _row_to_document(row)
        file_path = workspace / doc.path
        if file_path.is_file():
            file_path.unlink()
        _nullify_skill_run_refs(conn, doc_id)
        conn.execute("DELETE FROM session_document WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM document WHERE id = ?", (doc_id,))
    return doc


def reconcile_orphans(db: Database, workspace_dir: str | Path) -> list[str]:
    workspace = Path(workspace_dir)
    removed: list[str] = []
    for doc in list_documents(db):
        if not (workspace / doc.path).is_file():
            deleted = delete_document(db, workspace, doc.id)
            if deleted is not None:
                removed.append(deleted.id)
    return removed
