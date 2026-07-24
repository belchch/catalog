"""``POST /kb/connect``, ``GET /kb/status``, ``POST /kb/rescan``, ``POST
/kb/commit`` — the connected knowledge-base repo (ADR-0022).

Replaces single-file upload with "connect a git repo, scan it into the
index, commit changes from the UI". ``app.state.repo_root``/``workspace`` and
``app.state.tools`` are updated in place on connect so the rest of the app
(``read_document`` et al., which closed over ``workspace`` at lifespan
startup) immediately targets the newly connected repo without a restart.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_db, get_repo_root
from app.api.schemas import (
    KBCommitOut,
    KBCommitRequest,
    KBConnectOut,
    KBConnectRequest,
    KBRescanOut,
    KBScanSummary,
    KBStatusOut,
)
from app.documents.scan import scan_repo
from app.documents.tools import build_document_tools
from app.skills.repo_skill import list_skills, scan_skills
from app.storage.db import Database
from app.storage.git import PathEscapesRepoError, ensure_repo
from app.storage.git import commit as git_commit
from app.storage.git import push as git_push
from app.storage.git import stage_all, status as git_status
from app.storage.repo_document import list_documents
from app.storage.repo_setting import get_setting, set_setting

router = APIRouter(prefix="/kb", tags=["kb"])

_KB_REPO_SUBDIRS = ("documents", "results", "skills")

_REMOTE_KEY = "kb_remote"
_PUSH_ENABLED_KEY = "kb_push_enabled"
_REPO_PATH_KEY = "kb_repo_path"


def _read_remote_config(db: Database) -> tuple[str | None, bool]:
    remote = get_setting(db, _REMOTE_KEY)
    push_enabled = get_setting(db, _PUSH_ENABLED_KEY) == "1"
    return remote, push_enabled


@router.post("/connect", response_model=KBConnectOut)
async def connect_kb_endpoint(
    req: KBConnectRequest,
    request: Request,
    db: Database = Depends(get_db),
) -> KBConnectOut:
    repo_root = Path(req.path).expanduser().resolve()
    ensure_repo(repo_root)
    for subdir in _KB_REPO_SUBDIRS:
        (repo_root / subdir).mkdir(parents=True, exist_ok=True)

    set_setting(db, _REPO_PATH_KEY, str(repo_root))
    if req.remote is not None:
        set_setting(db, _REMOTE_KEY, req.remote)
    set_setting(db, _PUSH_ENABLED_KEY, "1" if req.push_enabled else "0")

    request.app.state.repo_root = str(repo_root)
    request.app.state.workspace = str(repo_root)
    request.app.state.tools = build_document_tools(db, str(repo_root))

    scan_summary = scan_repo(db, repo_root)
    skills_summary = scan_skills(db, repo_root)
    remote, push_enabled = _read_remote_config(db)
    return KBConnectOut(
        repo_root=str(repo_root),
        remote=remote,
        push_enabled=push_enabled,
        scan=KBScanSummary(
            added=scan_summary.added,
            updated=scan_summary.updated,
            removed=scan_summary.removed,
            skipped=scan_summary.skipped,
        ),
        skills_loaded=skills_summary["loaded"],
    )


@router.get("/status", response_model=KBStatusOut)
async def kb_status_endpoint(
    db: Database = Depends(get_db),
    repo_root: str = Depends(get_repo_root),
) -> KBStatusOut:
    remote, push_enabled = _read_remote_config(db)
    st = git_status(repo_root)
    return KBStatusOut(
        repo_root=repo_root,
        remote=remote,
        push_enabled=push_enabled,
        staged_add=st.staged_add,
        staged_delete=st.staged_delete,
        staged_modify=st.staged_modify,
        unstaged=st.unstaged,
        untracked=st.untracked,
        is_clean=st.is_clean,
        document_count=len(list_documents(db)),
        skill_count=len(list_skills(db)),
    )


@router.post("/rescan", response_model=KBRescanOut)
async def kb_rescan_endpoint(
    db: Database = Depends(get_db),
    repo_root: str = Depends(get_repo_root),
) -> KBRescanOut:
    scan_summary = scan_repo(db, repo_root)
    skills_summary = scan_skills(db, repo_root)
    return KBRescanOut(
        scan=KBScanSummary(
            added=scan_summary.added,
            updated=scan_summary.updated,
            removed=scan_summary.removed,
            skipped=scan_summary.skipped,
        ),
        skills_loaded=skills_summary["loaded"],
    )


@router.post("/commit", response_model=KBCommitOut)
async def kb_commit_endpoint(
    req: KBCommitRequest,
    db: Database = Depends(get_db),
    repo_root: str = Depends(get_repo_root),
) -> KBCommitOut:
    try:
        stage_all(repo_root)
    except PathEscapesRepoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sha = git_commit(repo_root, req.message)
    if sha is None:
        return KBCommitOut(sha=None, pushed=False)

    remote, push_enabled = _read_remote_config(db)
    if not push_enabled or not remote:
        return KBCommitOut(sha=sha, pushed=False)
    result = git_push(repo_root, remote)
    return KBCommitOut(sha=sha, pushed=result.ok, push_warning=result.warning)
