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
    """Refused: the scan that would follow is about to empty a live index.

    Raised by the guards below, never by ``scan_repo`` itself — an *existing*
    repo tree legitimately going down to zero files (the user deleted the
    last document) must still reconcile normally. Two shapes are dangerous,
    and both end the same way: ``scan_repo`` reads "every file disappeared"
    and drops the whole document index plus every ``session_document`` /
    ``skill_run`` link, irreversibly, while the files themselves sit safe in
    a directory nobody is looking at any more.

    * :func:`guard_repo_not_missing` — the configured path does not exist at
      all (unmounted network drive, renamed/moved KB folder, typo'd persisted
      path). ``ensure_repo``'s ``mkdir(parents=True)`` would otherwise
      silently manifest a brand-new, empty repo right there.
    * :func:`guard_not_switching_to_empty_repo` — the path *does* exist but
      holds nothing indexable, and it is not the repo we are already on. A
      typo that happens to land on a real directory, or a folder just created
      in Finder, looks like an ordinary connect and is the likelier accident
      of the two.
    """


def _indexable_file_count(repo_root: str | Path) -> int:
    """How many files :func:`scan_repo` would index under this root."""
    root = Path(repo_root)
    count = 0
    for subdir in _SCANNED_SUBDIRS:
        base = root / subdir
        if not base.is_dir():
            continue
        for _dirpath, _dirnames, filenames in os.walk(base):
            count += sum(1 for name in filenames if _kind_for(subdir, name) is not None)
    return count


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


def guard_not_switching_to_empty_repo(
    repo_root: str | Path,
    db: Database,
    *,
    current_root: str | Path | None = None,
    force: bool = False,
) -> None:
    """Call on ``POST /kb/connect`` before scanning a *different* repo path.

    Complements :func:`guard_repo_not_missing`, which only catches a path
    that is missing outright. Connecting is a *switch*, so "the target holds
    no documents" carries a meaning it does not carry on startup or rescan:
    every row in the index is about to be reconciled away against a tree that
    was never the source of those rows.

    Deliberately narrow, so it cannot fire on legitimate work:

    * reconnecting to the same path is never guarded — that is exactly the
      "user deleted the last document" case, and it belongs to
      :func:`scan_repo` as usual;
    * a target that holds even one indexable file is a real KB, and switching
      to it is taken at face value;
    * an empty index has nothing to lose.
    """
    if force:
        return
    root = Path(repo_root)
    if current_root is not None and Path(current_root).resolve() == root.resolve():
        return
    existing_count = len(list_documents(db))
    if not existing_count or _indexable_file_count(root):
        return
    raise DangerousEmptyScanError(
        f"refusing to switch the knowledge base to {root}: it contains no "
        f"documents, while the index still holds {existing_count} document(s) "
        "from the repo you are connected to now. Scanning would drop all of "
        "them along with their session/run links (the files themselves stay "
        "on disk in the old repo). Check the path for a typo, or pass "
        "force=True if you really mean to start from an empty knowledge base."
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
