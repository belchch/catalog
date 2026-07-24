"""Index the connected KB repo by scanning its working tree (ADR-0022).

The repo (``documents/`` + ``results/``) is the source of truth for files;
SQLite stays a rebuildable index over it. ``scan_repo`` reconciles the two:
new files become rows, changed files keep their existing row id (ADR-0016 —
``session_document``/``skill_run`` foreign keys must not break), and files no
longer on disk are dropped via :func:`app.storage.repo_document.reconcile_orphans`
— including the fully-expected case of the last remaining file being deleted.
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


class DangerousEmptyScanError(RuntimeError):
    """Refused: about to auto-create a repo at a path that doesn't exist yet.

    Raised by :func:`guard_repo_not_missing`, not by ``scan_repo`` itself —
    an *existing* repo tree legitimately going down to zero files (the user
    deleted the last document) must still reconcile normally. The dangerous
    case is different: the configured path doesn't exist *at all* while the
    index already holds documents from a previous connection — most likely
    an unmounted network drive, a renamed/moved KB directory, or a typo'd
    persisted path. ``ensure_repo``'s ``mkdir(parents=True)`` would otherwise
    silently manifest a brand-new, empty repo there, and the scan that
    follows would then read that as "every file disappeared" and wipe the
    whole index plus every ``session_document``/``skill_run`` link.
    """


def guard_repo_not_missing(repo_root: str | Path, db: Database, *, force: bool = False) -> None:
    """Call before ``ensure_repo``/``scan_repo`` on a *reopened* repo path.

    No-op when ``force`` is set, when the path already exists (the common
    case — nothing dangerous about scanning a real, reachable directory), or
    when the index is empty already (nothing to lose).
    """
    if force:
        return
    existing_count = len(list_documents(db))
    if existing_count and not Path(repo_root).is_dir():
        raise DangerousEmptyScanError(
            f"refusing to initialize a new, empty repo at {repo_root}: the "
            f"index already has {existing_count} document(s) from a previous "
            "connection, and this path does not exist on disk — likely an "
            "unmounted drive, a renamed/moved KB folder, or a typo. Pass "
            "force=True if this is an intentional switch to a new, empty repo."
        )


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
                try:
                    stat = abs_path.stat()
                except OSError:
                    # Broken symlink, permission denied, vanished mid-walk —
                    # skip it rather than let one bad file 500 the whole scan
                    # partway through (some rows already added/updated).
                    summary.skipped += 1
                    continue
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
