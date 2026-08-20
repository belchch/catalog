from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from catalog.storage.db import Database


@dataclass
class DocumentRow:
    id: str
    title: str
    path: str
    kind: str
    created_at: str
    mtime: float | None = None
    size: int | None = None
    content_hash: str | None = None
    extracted_text: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_document(row: sqlite3.Row) -> DocumentRow:
    keys = set(row.keys())
    return DocumentRow(
        id=row["id"],
        title=row["title"],
        path=row["path"],
        kind=row["kind"],
        created_at=row["created_at"],
        mtime=row["mtime"] if "mtime" in keys else None,
        size=row["size"] if "size" in keys else None,
        content_hash=row["content_hash"] if "content_hash" in keys else None,
        extracted_text=row["extracted_text"] if "extracted_text" in keys else None,
    )


_SELECT_COLS = (
    "id, title, path, kind, created_at, mtime, size, content_hash, extracted_text"
)


def create_document(
    db: Database,
    *,
    title: str,
    path: str,
    kind: str,
    doc_id: str | None = None,
    mtime: float | None = None,
    size: int | None = None,
    content_hash: str | None = None,
    extracted_text: str | None = None,
) -> DocumentRow:
    if doc_id is None:
        doc_id = uuid.uuid4().hex
    created_at = _now_iso()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO document("
            "id, title, path, kind, created_at, mtime, size, content_hash, extracted_text"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                title,
                path,
                kind,
                created_at,
                mtime,
                size,
                content_hash,
                extracted_text,
            ),
        )
    return DocumentRow(
        id=doc_id,
        title=title,
        path=path,
        kind=kind,
        created_at=created_at,
        mtime=mtime,
        size=size,
        content_hash=content_hash,
        extracted_text=extracted_text,
    )


def update_document(
    db: Database,
    doc_id: str,
    *,
    path: str | None = None,
    title: str | None = None,
    kind: str | None = None,
    mtime: float | None = None,
    size: int | None = None,
    content_hash: str | None = None,
    extracted_text: str | None = None,
) -> DocumentRow | None:
    current = get_document(db, doc_id)
    if current is None:
        return None
    new_path = current.path if path is None else path
    new_title = current.title if title is None else title
    new_kind = current.kind if kind is None else kind
    new_mtime = current.mtime if mtime is None else mtime
    new_size = current.size if size is None else size
    new_hash = current.content_hash if content_hash is None else content_hash
    new_text = current.extracted_text if extracted_text is None else extracted_text
    with db.connect() as conn:
        conn.execute(
            "UPDATE document SET path = ?, title = ?, kind = ?, mtime = ?, "
            "size = ?, content_hash = ?, extracted_text = ? WHERE id = ?",
            (
                new_path,
                new_title,
                new_kind,
                new_mtime,
                new_size,
                new_hash,
                new_text,
                doc_id,
            ),
        )
    return DocumentRow(
        id=doc_id,
        title=new_title,
        path=new_path,
        kind=new_kind,
        created_at=current.created_at,
        mtime=new_mtime,
        size=new_size,
        content_hash=new_hash,
        extracted_text=new_text,
    )


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


def _parse_doc_ids(raw: object, fallback: str | None) -> list[str]:
    if raw:
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return [fallback] if fallback else []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return [fallback] if fallback else []
    if fallback:
        return [fallback]
    return []


def _nullify_skill_run_refs(conn: sqlite3.Connection, doc_id: str) -> None:
    rows = conn.execute(
        "SELECT id, input_doc_id, input_doc_ids, output_doc_id, output_doc_ids "
        "FROM skill_run"
    ).fetchall()
    for row in rows:
        input_ids = _parse_doc_ids(row["input_doc_ids"], row["input_doc_id"])
        output_ids = _parse_doc_ids(row["output_doc_ids"], row["output_doc_id"])
        input_changed = doc_id in input_ids or row["input_doc_id"] == doc_id
        output_changed = doc_id in output_ids or row["output_doc_id"] == doc_id
        if not input_changed and not output_changed:
            continue
        new_inputs = [item for item in input_ids if item != doc_id]
        new_outputs = [item for item in output_ids if item != doc_id]
        new_output_primary = row["output_doc_id"]
        if new_output_primary == doc_id:
            new_output_primary = None
        conn.execute(
            "UPDATE skill_run SET input_doc_id = ?, input_doc_ids = ?, "
            "output_doc_id = ?, output_doc_ids = ? WHERE id = ?",
            (
                new_inputs[0] if new_inputs else None,
                json.dumps(new_inputs, ensure_ascii=False) if new_inputs else None,
                new_output_primary,
                json.dumps(new_outputs, ensure_ascii=False) if new_outputs else None,
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
