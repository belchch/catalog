"""App-owned git repositories (ADR-0012) via dulwich.

Pure Python, zero host dependencies — no ``git`` binary, no ``user.name`` /
``user.email`` configuration required. Used to lazily initialize the two
internal repos (``documents/``, ``skills/``) under the workspace.
"""

from __future__ import annotations

from pathlib import Path

from dulwich.repo import Repo


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
