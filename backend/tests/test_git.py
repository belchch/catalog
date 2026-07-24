"""Tests for the dulwich-backed KB-repo git layer (ADR-0012/0022, CATALOG-20)."""

from __future__ import annotations

from pathlib import Path

import pytest
from dulwich.repo import Repo

from app.storage.git import (
    PathEscapesRepoError,
    commit,
    ensure_repo,
    stage_all,
    stage_paths,
    stage_removal,
    status,
)


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


def test_stage_and_commit_creates_commit(tmp_path: Path) -> None:
    ensure_repo(tmp_path).close()
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "a.md").write_text("hi", encoding="utf-8")

    stage_paths(tmp_path, ["documents/a.md"])
    sha = commit(tmp_path, "add a.md")

    assert sha is not None
    assert status(tmp_path).is_clean


def test_commit_with_nothing_staged_is_noop(tmp_path: Path) -> None:
    ensure_repo(tmp_path).close()

    assert commit(tmp_path, "nothing to see") is None


def test_status_reports_untracked_before_staging(tmp_path: Path) -> None:
    ensure_repo(tmp_path).close()
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "a.md").write_text("hi", encoding="utf-8")

    st = status(tmp_path)

    assert "documents/" in st.untracked
    assert not st.is_clean


def test_stage_all_picks_up_deletion(tmp_path: Path) -> None:
    ensure_repo(tmp_path).close()
    (tmp_path / "documents").mkdir()
    doc = tmp_path / "documents" / "a.md"
    doc.write_text("hi", encoding="utf-8")
    stage_paths(tmp_path, ["documents/a.md"])
    commit(tmp_path, "add a.md")

    doc.unlink()
    stage_all(tmp_path)

    st = status(tmp_path)
    assert "documents/a.md" in st.staged_delete
    sha = commit(tmp_path, "remove a.md")
    assert sha is not None


def test_stage_removal_of_deleted_file(tmp_path: Path) -> None:
    ensure_repo(tmp_path).close()
    (tmp_path / "documents").mkdir()
    doc = tmp_path / "documents" / "a.md"
    doc.write_text("hi", encoding="utf-8")
    stage_paths(tmp_path, ["documents/a.md"])
    commit(tmp_path, "add a.md")

    doc.unlink()
    stage_removal(tmp_path, ["documents/a.md"])

    assert "documents/a.md" in status(tmp_path).staged_delete


def test_stage_paths_rejects_traversal(tmp_path: Path) -> None:
    ensure_repo(tmp_path).close()

    with pytest.raises(PathEscapesRepoError):
        stage_paths(tmp_path, ["../outside.md"])
