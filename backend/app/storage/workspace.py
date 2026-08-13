from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.documents.scan import ScanReport, preview_workspace, scan_workspace
from app.documents.tools import build_document_tools
from app.skills.repo_run import has_running_runs
from app.storage.db import Database
from app.storage.schema import (
    ADDITIVE_MIGRATIONS,
    WORKSPACE_SCHEMA,
    WORKSPACE_USER_VERSION,
)

CATALOG_DIR = ".catalog"
INDEX_DB_NAME = "index.db"
BACKUPS_DIR = "backups"
BACKUP_LIMIT = 5


class WorkspaceError(Exception):
    pass


class WorkspaceValidationError(WorkspaceError):
    pass


class WorkspaceBusyError(WorkspaceError):
    pass


class WorkspaceNotFoundError(WorkspaceError):
    pass


class WorkspaceAccessError(WorkspaceError):
    pass


@dataclass
class OpenResult:
    status: Literal["ok", "needs_init", "needs_confirm"]
    path: str
    display_name: str
    scan: ScanReport | None = None


def _has_user_content(root: Path) -> bool:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d != CATALOG_DIR and not d.startswith(".")
        ]
        for name in filenames:
            if not name.startswith("."):
                return True
    return False


class WorkspaceManager:
    def __init__(self) -> None:
        self.current: Database | None = None
        self.root: Path | None = None
        self.last_scan: ScanReport | None = None
        self._app_db: Database | None = None
        self._app_state: Any | None = None

    def bind(self, *, app_db: Database, app_state: Any) -> None:
        self._app_db = app_db
        self._app_state = app_state
        self._sync_app_state()

    def validate(self, path: Path) -> None:
        root = path.resolve()
        index = root / CATALOG_DIR / INDEX_DB_NAME
        if not index.is_file():
            raise WorkspaceValidationError(
                f"missing workspace marker database: {index}"
            )
        db = Database(str(index))
        version = db.user_version()
        if version != WORKSPACE_USER_VERSION:
            raise WorkspaceValidationError(
                f"incompatible workspace schema version: got {version}, "
                f"expected {WORKSPACE_USER_VERSION}"
            )
        check = db.quick_check()
        if check != "ok":
            raise WorkspaceValidationError(f"workspace database failed quick_check: {check}")

    def _hook_rescan(self, root: Path, db: Database) -> ScanReport:
        report = scan_workspace(db, root)
        self.last_scan = report
        return report

    def open(self, path: str | Path, *, confirm_init: bool = False) -> Database:
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise WorkspaceValidationError(f"path is not a directory: {root}")

        if self.root is not None and self.root == root and self.current is not None:
            self._hook_rescan(root, self.current)
            return self.current

        if self.current is not None:
            self._assert_no_running()
            self._clear_current()

        catalog = root / CATALOG_DIR
        index = catalog / INDEX_DB_NAME
        if index.is_file():
            self.validate(root)
            self._backup_index(index)
        else:
            if not confirm_init:
                raise WorkspaceValidationError(
                    "folder has no .catalog/index.db; pass confirm_init=true to initialize"
                )
            catalog.mkdir(parents=True, exist_ok=True)

        db = Database(str(index))
        db.init_schema(WORKSPACE_SCHEMA, WORKSPACE_USER_VERSION, ADDITIVE_MIGRATIONS)
        self.current = db
        self.root = root
        self._hook_rescan(root, db)
        self._touch_registry(root)
        self._sync_app_state()
        return db

    def open_for_api(self, path: str | Path, *, confirm: bool = False) -> OpenResult:
        try:
            root = Path(path).expanduser().resolve()
        except OSError as exc:
            raise WorkspaceAccessError(str(exc)) from exc

        if not root.exists():
            raise WorkspaceNotFoundError(f"path not found: {root}")
        if not root.is_dir():
            raise WorkspaceValidationError(f"path is not a directory: {root}")
        try:
            next(root.iterdir(), None)
        except PermissionError as exc:
            raise WorkspaceAccessError(f"path not accessible: {root}") from exc

        index = root / CATALOG_DIR / INDEX_DB_NAME
        display = root.name
        path_str = str(root)

        if index.is_file():
            self.open(root, confirm_init=False)
            return OpenResult(
                status="ok",
                path=path_str,
                display_name=display,
                scan=self.last_scan,
            )

        if not confirm:
            if not _has_user_content(root):
                return OpenResult(
                    status="needs_init",
                    path=path_str,
                    display_name=display,
                )
            return OpenResult(
                status="needs_confirm",
                path=path_str,
                display_name=display,
                scan=preview_workspace(root),
            )

        self.open(root, confirm_init=True)
        return OpenResult(
            status="ok",
            path=path_str,
            display_name=display,
            scan=self.last_scan,
        )

    def close(self) -> None:
        if self.current is not None:
            self._assert_no_running()
        self._clear_current()
        self._sync_app_state()

    def _clear_current(self) -> None:
        self.current = None
        self.root = None
        self.last_scan = None

    def has_running(self) -> bool:
        if self.current is None:
            return False
        return has_running_runs(self.current)

    def _assert_no_running(self) -> None:
        if self.has_running():
            raise WorkspaceBusyError("cannot switch workspace while a skill_run is running")

    def list_registry(self) -> list[dict[str, str | None]]:
        if self._app_db is None:
            return []
        with self._app_db.connect() as conn:
            rows = conn.execute(
                "SELECT path, display_name, opened_at FROM workspace_registry "
                "ORDER BY opened_at DESC"
            ).fetchall()
        return [
            {
                "path": row["path"],
                "display_name": row["display_name"],
                "last_opened": row["opened_at"],
            }
            for row in rows
        ]

    def rescan(self) -> ScanReport:
        if self.current is None or self.root is None:
            raise WorkspaceValidationError("workspace not open")
        return self._hook_rescan(self.root, self.current)

    def _backup_index(self, index: Path) -> Path:
        backups = index.parent / BACKUPS_DIR
        backups.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest = backups / f"{stamp}.db"
        shutil.copy2(index, dest)
        existing = sorted(backups.glob("*.db"), key=lambda p: p.name, reverse=True)
        for stale in existing[BACKUP_LIMIT:]:
            stale.unlink(missing_ok=True)
        return dest

    def _touch_registry(self, root: Path) -> None:
        if self._app_db is None:
            return
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        path_str = str(root)
        display = root.name
        with self._app_db.connect() as conn:
            row = conn.execute(
                "SELECT id FROM workspace_registry WHERE path = ?",
                (path_str,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO workspace_registry(id, path, display_name, opened_at) "
                    "VALUES (?, ?, ?, ?)",
                    (uuid.uuid4().hex, path_str, display, now),
                )
            else:
                conn.execute(
                    "UPDATE workspace_registry SET opened_at = ?, display_name = ? WHERE id = ?",
                    (now, display, row["id"]),
                )

    def _sync_app_state(self) -> None:
        state = self._app_state
        if state is None:
            return
        state.db = self.current
        if self.root is None or self.current is None:
            state.workspace = None
            state.tools = None
        else:
            state.workspace = str(self.root)
            state.tools = build_document_tools(self.current, self.root)
