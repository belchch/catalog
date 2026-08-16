from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
_STAMP_FILE = _PACKAGE_DIR / "_build_sha.py"


def git_sha_from_repo(cwd: Path, timeout: float = 10.0) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def baked_git_sha() -> str:
    try:
        from catalog._build_sha import GIT_SHA
    except ImportError:
        return ""
    return (GIT_SHA or "").strip()


def write_build_sha(target: Path | None = None) -> str:
    sha = os.getenv("GIT_SHA", "").strip()
    if not sha or sha == "unknown":
        sha = git_sha_from_repo(_PACKAGE_DIR.parent)
    if not sha or not sha.isalnum():
        return ""
    path = _STAMP_FILE if target is None else target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'GIT_SHA = "{sha}"\n', encoding="utf-8")
    return sha
