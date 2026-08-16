from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from catalog.documents.ingest import kind_for_filename
from catalog.storage.db import Database
from catalog.storage.repo_document import (
    create_document,
    delete_document,
    list_documents,
    update_document,
)

_CATALOG_DIR = ".catalog"
_EXPORT_DIR = "export"
_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass
class ScanReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "added": list(self.added),
            "updated": list(self.updated),
            "renamed": list(self.renamed),
            "removed": list(self.removed),
            "skipped": list(self.skipped),
        }


@dataclass
class _FsEntry:
    rel_path: str
    kind: str
    mtime: float
    size: int
    title: str
    abs_path: Path
    content_hash: str | None = None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_hash(entry: _FsEntry) -> str:
    if entry.content_hash is None:
        entry.content_hash = _hash_file(entry.abs_path)
    return entry.content_hash


def _is_hidden_part(name: str) -> bool:
    return name.startswith(".")


def _walk_workspace(root: Path) -> tuple[list[_FsEntry], list[str]]:
    entries: list[_FsEntry] = []
    skipped: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d != _CATALOG_DIR and d != _EXPORT_DIR and not _is_hidden_part(d)
        ]
        base = Path(dirpath)
        for name in filenames:
            full = base / name
            try:
                rel = full.relative_to(root).as_posix()
            except ValueError:
                continue
            if _is_hidden_part(name) or any(
                _is_hidden_part(p) for p in Path(rel).parts
            ):
                skipped.append(rel)
                continue
            if _CATALOG_DIR in Path(rel).parts or _EXPORT_DIR in Path(rel).parts:
                skipped.append(rel)
                continue
            kind = kind_for_filename(name, skip=True)
            if kind is None:
                skipped.append(rel)
                continue
            try:
                st = full.stat()
            except OSError:
                skipped.append(rel)
                continue
            entries.append(
                _FsEntry(
                    rel_path=rel,
                    kind=kind,
                    mtime=st.st_mtime,
                    size=st.st_size,
                    title=Path(name).stem,
                    abs_path=full,
                )
            )
    return entries, skipped


def preview_workspace(workspace_dir: str | Path) -> ScanReport:
    root = Path(workspace_dir)
    report = ScanReport()
    if not root.is_dir():
        return report
    entries, skipped = _walk_workspace(root)
    report.skipped.extend(skipped)
    report.added.extend(e.rel_path for e in entries)
    return report


def scan_workspace(db: Database, workspace_dir: str | Path) -> ScanReport:
    root = Path(workspace_dir)
    report = ScanReport()
    if not root.is_dir():
        return report

    entries, skipped = _walk_workspace(root)
    report.skipped.extend(skipped)

    docs = list_documents(db)
    by_path = {d.path: d for d in docs}
    fs_paths = {e.rel_path for e in entries}

    claimed_ids: set[str] = set()

    for entry in entries:
        existing = by_path.get(entry.rel_path)
        if existing is not None:
            claimed_ids.add(existing.id)
            same_meta = (
                existing.mtime == entry.mtime and existing.size == entry.size
            )
            if same_meta:
                if not existing.content_hash:
                    update_document(
                        db,
                        existing.id,
                        content_hash=_ensure_hash(entry),
                    )
                continue
            file_hash = _ensure_hash(entry)
            hash_changed = existing.content_hash != file_hash
            update_document(
                db,
                existing.id,
                mtime=entry.mtime,
                size=entry.size,
                content_hash=file_hash,
            )
            if hash_changed:
                report.updated.append(entry.rel_path)
            continue

        file_hash = _ensure_hash(entry)
        rename_candidate = None
        for doc in docs:
            if doc.id in claimed_ids:
                continue
            if doc.path in fs_paths:
                continue
            if doc.content_hash and doc.content_hash == file_hash:
                rename_candidate = doc
                break
        if rename_candidate is None:
            meta_matches = [
                doc
                for doc in docs
                if doc.id not in claimed_ids
                and doc.path not in fs_paths
                and not doc.content_hash
                and doc.size is not None
                and doc.mtime is not None
                and doc.size == entry.size
                and doc.mtime == entry.mtime
            ]
            if len(meta_matches) == 1:
                rename_candidate = meta_matches[0]

        if rename_candidate is not None:
            old_path = rename_candidate.path
            update_document(
                db,
                rename_candidate.id,
                path=entry.rel_path,
                mtime=entry.mtime,
                size=entry.size,
                content_hash=file_hash,
            )
            claimed_ids.add(rename_candidate.id)
            report.renamed.append(f"{old_path} → {entry.rel_path}")
            continue

        row = create_document(
            db,
            title=entry.title,
            path=entry.rel_path,
            kind=entry.kind,
            mtime=entry.mtime,
            size=entry.size,
            content_hash=file_hash,
        )
        claimed_ids.add(row.id)
        report.added.append(entry.rel_path)

    for doc in docs:
        if doc.id in claimed_ids:
            continue
        if doc.path in fs_paths:
            continue
        if (root / doc.path).is_file():
            continue
        deleted = delete_document(db, root, doc.id)
        if deleted is not None:
            report.removed.append(deleted.path)

    return report
