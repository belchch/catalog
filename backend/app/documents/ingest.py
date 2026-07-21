from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from app.storage.db import Database
from app.storage.repo_document import DocumentRow, create_document

_EXT_TO_KIND = {
    ".md": "md",
    ".docx": "docx",
    ".pdf": "pdf",
    ".csv": "csv",
    ".xlsx": "xlsx",
}

_CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

_SLUG_MAX_LEN = 60


def slugify(name: str) -> str:
    """Transliterate cyrillic, sanitize to ``[a-z0-9-]`` and cap the length.

    Returns ``""`` for empty/whitespace-only or otherwise unsafe input; callers
    should fall back to ``doc_id`` in that case.
    """
    lowered = name.strip().lower()
    transliterated = "".join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in lowered)
    slug = re.sub(r"[^a-z0-9]+", "-", transliterated).strip("-")
    return slug[:_SLUG_MAX_LEN].strip("-")


def build_doc_path(title: str, doc_id: str, ext: str, subdir: str) -> str:
    slug = slugify(title)
    stem = f"{slug}-{doc_id[:8]}" if slug else doc_id
    return f"{subdir}/{stem}{ext}"


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
    is a readable slug of the original name plus a short id suffix
    (``{slug}-{doc_id[:8]}{ext}``, or ``{doc_id}{ext}`` when the slug is empty)
    so the row id and the file always agree while staying human-readable.
    """
    kind = kind_for_filename(filename)
    ext = os.path.splitext(filename)[1].lower()
    doc_id = uuid.uuid4().hex
    title = os.path.splitext(filename)[0]
    rel_path = build_doc_path(title, doc_id, ext, "documents")

    workspace = Path(workspace_dir)
    docs_dir = workspace / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (workspace / rel_path).write_bytes(content)

    return create_document(db, title=title, path=rel_path, kind=kind, doc_id=doc_id)
