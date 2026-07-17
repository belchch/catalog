"""Tests for the dulwich-backed app-owned repos (ADR-0012, CATALOG-20)."""

from __future__ import annotations

from pathlib import Path

from dulwich.repo import Repo

from app.storage.git import ensure_repo


def test_ensure_repo_creates_git_dir(tmp_path: Path) -> None:
    target = tmp_path / "documents"

    repo = ensure_repo(target)

    assert (target / ".git").exists()
    assert isinstance(repo, Repo)
    repo.close()


def test_ensure_repo_creates_missing_parents(tmp_path: Path) -> None:
    target = tmp_path / "data-root" / "workspace" / "skills"

    ensure_repo(target).close()

    assert target.is_dir()
    assert (target / ".git").exists()


def test_ensure_repo_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "documents"

    ensure_repo(target).close()
    head_before = (target / ".git" / "HEAD").read_bytes()

    repo_again = ensure_repo(target)

    assert (target / ".git").exists()
    assert (target / ".git" / "HEAD").read_bytes() == head_before
    repo_again.close()


def test_ensure_repo_on_existing_non_repo_dir_initializes_it(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    (target / "already-here.md").write_text("hello", encoding="utf-8")

    ensure_repo(target).close()

    assert (target / ".git").exists()
    assert (target / "already-here.md").exists()
