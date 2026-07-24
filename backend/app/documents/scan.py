"""Index the connected KB repo by scanning its working tree (ADR-0022).

The repo (``documents/`` + ``results/``) is the source of truth for files;
SQLite stays a rebuildable index over it. ``scan_repo`` reconciles the two:
new files become rows, changed files keep their existing row id (ADR-0016 —
``session_document``/``skill_run`` foreign keys must not break), and files no
longer on disk are dropped via :func:`app.storage.repo_document.reconcile_orphans`.
``skills/`` is scanned separately by :mod:`app.skills.repo_skill`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.documents.ingest import kind_for_filename
from app.storage.db import Database
from app.storage.repo_document import (
    create_document,
    list_documents,
    reconcile_orphans,
    update_document_stat,
)

_SCANNED_SUBDIRS = ("documents", "results")


@dataclass
class ScanSummary:
    added: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0


def _kind_for(subdir: str, filename: str) -> str | None:
    if subdir == "results":
        return "result_md" if filename.lower().endswith(".md") else None
    try:
        return kind_for_filename(filename)
    except ValueError:
        return None


def scan_repo(db: Database, repo_root: str | Path) -> ScanSummary:
    root = Path(repo_root)
    by_path = {doc.path: doc for doc in list_documents(db)}
    summary = ScanSummary()

    for subdir in _SCANNED_SUBDIRS:
        base = root / subdir
        if not base.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for filename in filenames:
                kind = _kind_for(subdir, filename)
                if kind is None:
                    summary.skipped += 1
                    continue
                abs_path = Path(dirpath) / filename
                rel_path = abs_path.relative_to(root).as_posix()
                stat = abs_path.stat()
                existing = by_path.get(rel_path)
                if existing is not None:
                    if existing.mtime != stat.st_mtime or existing.size != stat.st_size:
                        update_document_stat(
                            db, existing.id, mtime=stat.st_mtime, size=stat.st_size
                        )
                        summary.updated += 1
                    continue
                title = os.path.splitext(filename)[0]
                create_document(
                    db,
                    title=title,
                    path=rel_path,
                    kind=kind,
                    mtime=stat.st_mtime,
                    size=stat.st_size,
                )
                summary.added += 1

    summary.removed = len(reconcile_orphans(db, root))
    return summary
