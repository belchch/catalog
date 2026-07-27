"""Tests for the dulwich-backed KB-repo git layer (ADR-0012/0022, CATALOG-20)."""

from __future__ import annotations

from pathlib import Path

import pytest
from dulwich.repo import Repo

from app.storage.git import (
    PathEscapesRepoError,
    commit,
    ensure_gitignore,
    ensure_repo,
    pending_paths,
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


def test_ensure_gitignore_writes_and_commits_immediately(tmp_path: Path) -> None:
    ensure_repo(tmp_path).close()

    ensure_gitignore(tmp_path)

    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "prompt_logs/" in text
    assert ".DS_Store" in text
    assert ".obsidian/" in text
    # Committed immediately (it's bootstrap plumbing, not user content) so it
    # never dangles as an "other pending change" for e.g. the skill-commit
    # isolation check.
    assert status(tmp_path).is_clean


def test_ensure_gitignore_is_idempotent(tmp_path: Path) -> None:
    ensure_repo(tmp_path).close()
    ensure_gitignore(tmp_path)
    text_before = (tmp_path / ".gitignore").read_text(encoding="utf-8")

    ensure_gitignore(tmp_path)  # second call: nothing to add, no new commit

    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == text_before
    assert status(tmp_path).is_clean


def test_stage_all_respects_gitignore(tmp_path: Path) -> None:
    ensure_repo(tmp_path).close()
    ensure_gitignore(tmp_path)
    (tmp_path / "prompt_logs").mkdir()
    (tmp_path / "prompt_logs" / "run.json").write_text("{}", encoding="utf-8")
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "note.md").write_text("hi", encoding="utf-8")

    stage_all(tmp_path)

    st = status(tmp_path)
    assert "documents/note.md" in st.staged_add
    assert not any("prompt_logs" in p for p in st.staged_add)


def test_pending_paths_expands_untracked_directory(tmp_path: Path) -> None:
    ensure_repo(tmp_path).close()
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "alpha-abcd1234.json").write_text("{}", encoding="utf-8")

    # status() collapses a wholly-untracked dir to one entry ("skills/") —
    # pending_paths must expand it to the actual file.
    assert "skills/" in status(tmp_path).untracked
    assert pending_paths(tmp_path) == {"skills/alpha-abcd1234.json"}


def test_ensure_gitignore_does_not_sweep_unrelated_staged_files(tmp_path: Path) -> None:
    """``commit`` writes the whole index, so the bootstrap commit must stand
    down when someone else's work is already staged (an interrupted
    ``POST /kb/commit``, a manual ``git add``) — review follow-up."""
    ensure_repo(tmp_path).close()
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "wip.md").write_text("unrelated pending work", encoding="utf-8")
    stage_paths(tmp_path, ["documents/wip.md"])

    ensure_gitignore(tmp_path)

    # The file is written (stage_all still needs it as defense in depth)...
    assert "prompt_logs/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    # ...but no commit happened: the staged file is still merely staged.
    with pytest.raises(KeyError):
        Repo(str(tmp_path)).head()
    st = status(tmp_path)
    assert "documents/wip.md" in st.staged_add
    assert ".gitignore" in st.untracked


def test_ensure_gitignore_is_picked_up_by_the_next_explicit_commit(tmp_path: Path) -> None:
    """Standing down is not dropping the file: the user's own commit takes it."""
    ensure_repo(tmp_path).close()
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "wip.md").write_text("pending", encoding="utf-8")
    stage_paths(tmp_path, ["documents/wip.md"])
    ensure_gitignore(tmp_path)

    stage_all(tmp_path)
    assert commit(tmp_path, "user's own commit") is not None

    assert status(tmp_path).is_clean
