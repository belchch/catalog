"""Tests for the KB-repo connect/status/rescan/commit API (ADR-0022)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("client")


def test_connect_inits_repo_and_subdirs(client, tmp_path: Path) -> None:
    target = tmp_path / "my-kb"

    resp = client.post("/kb/connect", json={"path": str(target)})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["repo_root"] == str(target)
    assert (target / ".git").exists()
    for sub in ("documents", "results", "skills"):
        assert (target / sub).is_dir()
    assert body["scan"] == {"added": 0, "updated": 0, "removed": 0, "skipped": 0}
    assert client.app.state.repo_root == str(target)
    assert client.app.state.workspace == str(target)


def test_connect_indexes_existing_files(client, tmp_path: Path) -> None:
    target = tmp_path / "existing-kb"
    (target / "documents").mkdir(parents=True)
    (target / "documents" / "note.md").write_text("hi", encoding="utf-8")

    resp = client.post("/kb/connect", json={"path": str(target)})

    assert resp.status_code == 200
    assert resp.json()["scan"]["added"] == 1

    listing = client.get("/documents")
    assert len(listing.json()) == 1


def test_status_reports_pending_changes(client, tmp_path: Path) -> None:
    target = tmp_path / "status-kb"
    client.post("/kb/connect", json={"path": str(target)})
    (target / "documents" / "note.md").write_text("hi", encoding="utf-8")

    resp = client.get("/kb/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_clean"] is False
    assert "documents/" in body["untracked"]
    assert body["document_count"] == 0  # not yet scanned/committed


def test_commit_stages_and_commits_pending_changes(client, tmp_path: Path) -> None:
    target = tmp_path / "commit-kb"
    client.post("/kb/connect", json={"path": str(target)})
    (target / "documents" / "note.md").write_text("hi", encoding="utf-8")

    resp = client.post("/kb/commit", json={"message": "add note"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["sha"] is not None
    assert body["pushed"] is False

    status_after = client.get("/kb/status").json()
    assert status_after["is_clean"] is True


def test_commit_with_no_changes_is_noop(client, tmp_path: Path) -> None:
    target = tmp_path / "empty-commit-kb"
    client.post("/kb/connect", json={"path": str(target)})

    resp = client.post("/kb/commit", json={"message": "nothing pending"})

    assert resp.status_code == 200
    assert resp.json() == {"sha": None, "pushed": False, "push_warning": None}


def test_commit_rejects_empty_message(client, tmp_path: Path) -> None:
    target = tmp_path / "msg-kb"
    client.post("/kb/connect", json={"path": str(target)})

    resp = client.post("/kb/commit", json={"message": "   "})

    assert resp.status_code == 422


def test_rescan_picks_up_external_file_changes(client, tmp_path: Path) -> None:
    target = tmp_path / "rescan-kb"
    client.post("/kb/connect", json={"path": str(target)})
    (target / "documents" / "note.md").write_text("hi", encoding="utf-8")

    resp = client.post("/kb/rescan")

    assert resp.status_code == 200
    assert resp.json()["scan"]["added"] == 1
    assert len(client.get("/documents").json()) == 1


def test_rescan_removes_orphans(client, tmp_path: Path) -> None:
    target = tmp_path / "orphan-kb"
    client.post("/kb/connect", json={"path": str(target)})
    note = target / "documents" / "note.md"
    note.write_text("hi", encoding="utf-8")
    client.post("/kb/rescan")
    assert len(client.get("/documents").json()) == 1

    note.unlink()
    resp = client.post("/kb/rescan")

    assert resp.json()["scan"]["removed"] == 1
    assert client.get("/documents").json() == []


def test_connect_persists_across_lifespan_restart(client, settings, tmp_path: Path) -> None:
    """A prior connect wins over the Settings default at the next startup."""
    from fastapi.testclient import TestClient

    from app.main import app

    target = tmp_path / "persisted-kb"
    client.post("/kb/connect", json={"path": str(target)})

    with TestClient(app) as c2:
        assert c2.app.state.repo_root == str(target)
