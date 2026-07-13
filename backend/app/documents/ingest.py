from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.storage.db import Database
from app.storage.repo_document import DocumentRow, create_document

_EXT_TO_KIND = {".md": "md", ".docx": "docx"}


def kind_for_filename(filename: str) -> str:
    """Map a filename extension to a document kind, or raise ``ValueError``."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _EXT_TO_KIND:
        raise ValueError(f"unsupported format: {ext or '<none>'}")
    return _EXT_TO_KIND[ext]


def ingest_file(
    db: Database,
    workspace_dir: str | Path,
    *,
    filename: str,
    content: bytes,
) -> DocumentRow:
    """Persist a document's bytes under ``workspace/documents/`` and record it.

    The original bytes are stored verbatim (for ``.docx`` the text is extracted
    lazily by :func:`read_document`, not at ingest time). The on-disk filename
    embeds the generated document id so the row id and the file always agree.
    """
    kind = kind_for_filename(filename)
    ext = os.path.splitext(filename)[1].lower()
    doc_id = uuid.uuid4().hex
    rel_path = f"documents/{doc_id}{ext}"

    workspace = Path(workspace_dir)
    docs_dir = workspace / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (workspace / rel_path).write_bytes(content)

    title = os.path.splitext(filename)[0]
    return create_document(db, title=title, path=rel_path, kind=kind, doc_id=doc_id)
