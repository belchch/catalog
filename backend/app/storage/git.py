"""KB-repo git transactions via dulwich (ADR-0022).

Pure Python, zero host dependencies — no ``git`` binary, no ``user.name`` /
``user.email`` configuration required (critical for on-prem installs). Beyond
``ensure_repo`` (init/open, used for the connected knowledge-base repo) this
module adds the stage/status/commit/push primitives the KB endpoints need to
turn "files changed in the working tree" into real git history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

_APP_AUTHOR = b"Catalog <catalog@localhost>"


class PathEscapesRepoError(ValueError):
    """Raised when a path resolves outside the repo root (traversal guard)."""


def ensure_repo(path: str | Path) -> Repo:
    """Ensure ``path`` exists and is a git repository; return it.

    Idempotent: creates the directory (and any missing parents) if needed,
    runs ``git init`` only when ``.git`` is not already present, and simply
    opens the existing repo otherwise.
    """
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    if (target / ".git").exists():
        return Repo(str(target))
    return Repo.init(str(target))


# ``ensure_repo`` covers both init and open; these aliases make call sites
# read as intent ("connect to a fresh repo" vs "reopen a configured one").
init_repo = ensure_repo
open_repo = ensure_repo


def _guarded_abs_paths(repo_root: str | Path, paths: list[str]) -> list[str]:
    """Resolve ``paths`` (relative to ``repo_root``) and reject traversal.

    Every path must resolve to somewhere inside ``repo_root`` — guards against
    ``../`` segments or symlinks pointing outside the connected repo.
    """
    root = Path(repo_root).resolve()
    out: list[str] = []
    for rel in paths:
        candidate = (root / rel).resolve()
        if candidate != root and root not in candidate.parents:
            raise PathEscapesRepoError(f"path escapes repo root: {rel}")
        out.append(str(candidate))
    return out


def stage_paths(repo_root: str | Path, paths: list[str]) -> None:
    """Add/stage files (new or modified) under ``repo_root``."""
    if not paths:
        return
    abs_paths = _guarded_abs_paths(repo_root, paths)
    porcelain.add(str(repo_root), paths=abs_paths)


def stage_all(repo_root: str | Path) -> None:
    """Stage every pending change in the working tree (``git add -A``).

    Used by the general "Commit" button (ADR-0022 decision #5): the working
    tree accumulates document/result/skill changes as plain file writes and
    deletes; this is what turns all of them into one commit at once.
    """
    porcelain.add(str(repo_root))


def stage_removal(repo_root: str | Path, paths: list[str]) -> None:
    """Stage a deletion for files already removed from the working tree.

    ``cached=True`` only updates the index — the caller (``delete_document``)
    already unlinked the file, so there is nothing left on disk to touch.
    """
    if not paths:
        return
    abs_paths = _guarded_abs_paths(repo_root, paths)
    porcelain.remove(str(repo_root), paths=abs_paths, cached=True)


@dataclass
class RepoStatus:
    staged_add: list[str] = field(default_factory=list)
    staged_delete: list[str] = field(default_factory=list)
    staged_modify: list[str] = field(default_factory=list)
    unstaged: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (
            self.staged_add
            or self.staged_delete
            or self.staged_modify
            or self.unstaged
            or self.untracked
        )


def _decode(items: list[bytes | str]) -> list[str]:
    return [i.decode() if isinstance(i, bytes) else i for i in items]


def status(repo_root: str | Path) -> RepoStatus:
    """Report staged/unstaged/untracked changes (panel of pending work)."""
    st = porcelain.status(str(repo_root))
    return RepoStatus(
        staged_add=_decode(st.staged.get("add", [])),
        staged_delete=_decode(st.staged.get("delete", [])),
        staged_modify=_decode(st.staged.get("modify", [])),
        unstaged=_decode(st.unstaged),
        untracked=_decode(st.untracked),
    )


def commit(repo_root: str | Path, message: str) -> str | None:
    """Commit currently staged changes; return the short sha, or ``None``.

    ``None`` when there is nothing staged (no-op, not an error) — dulwich
    would otherwise happily create an empty commit identical to its parent.
    A fixed app identity is used for both author and committer so on-prem
    installs never need host ``git`` config.
    """
    st = status(repo_root)
    if not (st.staged_add or st.staged_delete or st.staged_modify):
        return None
    sha = porcelain.commit(
        str(repo_root),
        message=message.encode("utf-8"),
        author=_APP_AUTHOR,
        committer=_APP_AUTHOR,
    )
    return sha.decode()[:12]


@dataclass
class PushResult:
    ok: bool
    warning: str | None = None


def push(repo_root: str | Path, remote: str) -> PushResult:
    """Push HEAD to ``remote``.

    Failures are warnings — the commit already landed locally, so a broken or
    unreachable remote must not roll it back or surface as a hard error.
    """
    try:
        porcelain.push(str(repo_root), remote_location=remote)
    except Exception as exc:  # noqa: BLE001 - any transport/auth failure is a soft warning
        return PushResult(ok=False, warning=str(exc))
    return PushResult(ok=True)
