from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from catalog.api.deps import get_settings, get_workspace_manager
from catalog.api.schemas import (
    FsEntry,
    ScanReport,
    WorkspaceOpenRequest,
    WorkspaceOpenResult,
    WorkspaceOut,
)
from catalog.config import Settings
from catalog.storage.workspace import (
    WorkspaceAccessError,
    WorkspaceBusyError,
    WorkspaceManager,
    WorkspaceNotFoundError,
    WorkspaceValidationError,
)

router = APIRouter()


def _scan_out(report) -> ScanReport | None:
    if report is None:
        return None
    data = report.as_dict() if hasattr(report, "as_dict") else report
    return ScanReport(**data)


@router.get("/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(
    manager: WorkspaceManager = Depends(get_workspace_manager),
) -> list[WorkspaceOut]:
    return [WorkspaceOut(**row) for row in manager.list_registry()]


@router.get("/workspaces/current", response_model=WorkspaceOut | None)
async def current_workspace(
    response: Response,
    manager: WorkspaceManager = Depends(get_workspace_manager),
) -> WorkspaceOut | None:
    if manager.root is None:
        response.status_code = 204
        return None
    path_str = str(manager.root)
    last_opened = None
    for row in manager.list_registry():
        if row["path"] == path_str:
            last_opened = row["last_opened"]
            break
    return WorkspaceOut(
        path=path_str,
        display_name=manager.root.name,
        last_opened=last_opened,
    )


@router.post("/workspaces/open", response_model=WorkspaceOpenResult)
async def open_workspace(
    body: WorkspaceOpenRequest,
    manager: WorkspaceManager = Depends(get_workspace_manager),
    settings: Settings = Depends(get_settings),
) -> WorkspaceOpenResult:
    open_path = body.path.strip() if body.path else ""
    if open_path in ("", "."):
        open_path = str(Path(settings.fs_root).expanduser().resolve())
    try:
        result = manager.open_for_api(open_path, confirm=body.confirm)
    except WorkspaceBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkspaceAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except WorkspaceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WorkspaceOpenResult(
        status=result.status,
        path=result.path,
        display_name=result.display_name,
        scan=_scan_out(result.scan),
    )


@router.post("/workspaces/rescan", response_model=ScanReport)
async def rescan_workspace(
    manager: WorkspaceManager = Depends(get_workspace_manager),
) -> ScanReport:
    if manager.current is None or manager.root is None:
        raise HTTPException(status_code=409, detail="workspace not open")
    report = manager.rescan()
    return ScanReport(**report.as_dict())


@router.get("/fs/browse", response_model=list[FsEntry])
async def browse_fs(
    path: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> list[FsEntry]:
    root = Path(settings.fs_root).expanduser().resolve()
    if path is None or path == "":
        target = root
    else:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            target = candidate.resolve()
        except OSError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="path escapes APP_FS_ROOT"
        ) from exc
    if not target.exists():
        raise HTTPException(status_code=404, detail="path not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")
    try:
        children = sorted(target.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    entries: list[FsEntry] = []
    for child in children:
        if child.name.startswith("."):
            continue
        try:
            resolved = child.resolve()
        except OSError:
            continue
        if not resolved.is_dir():
            continue
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        has_catalog = (resolved / ".catalog" / "index.db").is_file()
        entries.append(
            FsEntry(name=child.name, path=str(resolved), has_catalog=has_catalog)
        )
    return entries
