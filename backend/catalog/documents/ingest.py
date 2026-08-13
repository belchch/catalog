from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from catalog.storage.db import Database
from catalog.storage.repo_document import DocumentRow, create_document

_EXT_TO_KIND = {
    ".md": "md",
    ".docx": "docx",
    ".pdf": "pdf",
    ".csv": "csv",
    ".xlsx": "xlsx",
}


def kind_for_filename(filename: str, *, skip: bool = False) -> str | None:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _EXT_TO_KIND:
        if skip:
            return None
        raise ValueError(f"unsupported format: {ext or '<none>'}")
    return _EXT_TO_KIND[ext]


def content_hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_filename(directory: Path, filename: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    stem, ext = os.path.splitext(filename)
    if not stem.strip():
        stem = "document"
        filename = f"{stem}{ext}"
    candidate = filename
    n = 1
    while (directory / candidate).exists():
        candidate = f"{stem}-{n}{ext}"
        n += 1
    return candidate


def safe_filename(name: str, ext: str) -> str:
    stem = name.strip() or "document"
    for ch in ("/", "\\", "\0"):
        stem = stem.replace(ch, "-")
    if not stem:
        stem = "document"
    if not ext.startswith("."):
        ext = f".{ext}" if ext else ""
    return f"{stem}{ext}"


def allocate_rel_path(workspace: Path, filename: str, *, subdir: str | None = None) -> str:
    if subdir:
        directory = workspace / subdir
        name = unique_filename(directory, filename)
        return f"{subdir}/{name}"
    name = unique_filename(workspace, filename)
    return name


def ingest_file(
    db: Database,
    workspace_dir: str | Path,
    *,
    filename: str,
    content: bytes,
) -> DocumentRow:
    kind = kind_for_filename(filename)
    if kind is None:
        raise ValueError(f"unsupported format: {os.path.splitext(filename)[1] or '<none>'}")
    title = os.path.splitext(filename)[0]
    workspace = Path(workspace_dir)
    base_name = Path(filename).name or f"document{os.path.splitext(filename)[1]}"
    rel_path = allocate_rel_path(workspace, base_name)
    dest = workspace / rel_path
    dest.write_bytes(content)
    st = dest.stat()
    return create_document(
        db,
        title=title,
        path=rel_path,
        kind=kind,
        doc_id=uuid.uuid4().hex,
        mtime=st.st_mtime,
        size=st.st_size,
        content_hash=content_hash_bytes(content),
    )
