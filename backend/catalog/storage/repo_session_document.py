from __future__ import annotations

from datetime import datetime, timezone

from catalog.storage.db import Database
from catalog.storage.repo_document import DocumentRow


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def attach_documents(db: Database, session_id: str, doc_ids: list[str]) -> None:
    if not doc_ids:
        return
    now = _now_iso()
    with db.connect() as conn:
        for doc_id in doc_ids:
            exists = conn.execute(
                "SELECT id FROM document WHERE id = ?",
                (doc_id,),
            ).fetchone()
            if exists is None:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO session_document(session_id, document_id, attached_at) "
                "VALUES (?, ?, ?)",
                (session_id, doc_id, now),
            )


def detach_documents(db: Database, session_id: str, doc_ids: list[str]) -> int:
    if not doc_ids:
        return 0
    placeholders = ", ".join("?" for _ in doc_ids)
    with db.connect() as conn:
        cur = conn.execute(
            f"DELETE FROM session_document "
            f"WHERE session_id = ? AND document_id IN ({placeholders})",
            (session_id, *doc_ids),
        )
        return int(cur.rowcount)


def list_session_documents(db: Database, session_id: str) -> list[DocumentRow]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT d.id, d.title, d.path, d.kind, d.created_at "
            "FROM session_document sd "
            "JOIN document d ON d.id = sd.document_id "
            "WHERE sd.session_id = ? "
            "ORDER BY sd.attached_at, d.created_at",
            (session_id,),
        ).fetchall()
    return [
        DocumentRow(
            id=r["id"],
            title=r["title"],
            path=r["path"],
            kind=r["kind"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
