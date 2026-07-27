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


def test_connect_rejects_empty_path(client) -> None:
    resp = client.post("/kb/connect", json={"path": ""})

    assert resp.status_code == 422


def test_connect_rejects_relative_path(client) -> None:
    """A relative path would resolve against the server's CWD (its source
    tree), not wherever the caller intended (ADR-0022 review)."""
    resp = client.post("/kb/connect", json={"path": "some/relative/path"})

    assert resp.status_code == 422


def test_connect_refuses_when_switching_away_from_a_nonempty_index_to_a_missing_path(
    client, tmp_path: Path
) -> None:
    first = tmp_path / "first-kb"
    (first / "documents").mkdir(parents=True)
    (first / "documents" / "note.md").write_text("hi", encoding="utf-8")
    client.post("/kb/connect", json={"path": str(first)})
    assert len(client.get("/documents").json()) == 1

    second = tmp_path / "second-kb-does-not-exist"
    resp = client.post("/kb/connect", json={"path": str(second)})

    assert resp.status_code == 409
    # Refused before anything was touched — old index/connection intact.
    assert client.app.state.repo_root == str(first)
    assert len(client.get("/documents").json()) == 1


def test_connect_force_bypasses_the_guard(client, tmp_path: Path) -> None:
    first = tmp_path / "first-kb"
    (first / "documents").mkdir(parents=True)
    (first / "documents" / "note.md").write_text("hi", encoding="utf-8")
    client.post("/kb/connect", json={"path": str(first)})

    second = tmp_path / "second-kb-does-not-exist"
    resp = client.post("/kb/connect", json={"path": str(second), "force": True})

    assert resp.status_code == 200
    assert client.app.state.repo_root == str(second)
    assert client.get("/documents").json() == []


def test_rescan_refuses_when_repo_path_vanished(client, tmp_path: Path) -> None:
    import shutil

    target = tmp_path / "vanish-kb"
    (target / "documents").mkdir(parents=True)
    (target / "documents" / "note.md").write_text("hi", encoding="utf-8")
    client.post("/kb/connect", json={"path": str(target)})
    assert len(client.get("/documents").json()) == 1

    shutil.rmtree(target)
    resp = client.post("/kb/rescan")

    assert resp.status_code == 409
    assert len(client.get("/documents").json()) == 1  # untouched


def test_connect_persists_across_lifespan_restart(client, settings, tmp_path: Path) -> None:
    """A prior connect wins over the Settings default at the next startup."""
    from fastapi.testclient import TestClient

    from app.main import app

    target = tmp_path / "persisted-kb"
    client.post("/kb/connect", json={"path": str(target)})

    with TestClient(app) as c2:
        assert c2.app.state.repo_root == str(target)


# --- switching to an existing but empty repo (review follow-up) ------------


def _connect_seeded_kb(client, tmp_path: Path) -> Path:
    first = tmp_path / "first-kb"
    (first / "documents").mkdir(parents=True)
    (first / "documents" / "note.md").write_text("hi", encoding="utf-8")
    assert client.post("/kb/connect", json={"path": str(first)}).status_code == 200
    assert len(client.get("/documents").json()) == 1
    return first


def test_connect_refuses_switch_to_an_existing_empty_directory(
    client, db, tmp_path: Path
) -> None:
    """The dangerous case guard_repo_not_missing cannot see: a typo that lands
    on a real directory. The whole index — and every session link — would go."""
    first = _connect_seeded_kb(client, tmp_path)
    doc_id = client.get("/documents").json()[0]["id"]
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO session(id, status, created_at, updated_at) "
            "VALUES ('s-kb', 'done', 'now', 'now')"
        )
        conn.execute(
            "INSERT INTO session_document(session_id, document_id, attached_at) "
            "VALUES ('s-kb', ?, 'now')",
            (doc_id,),
        )

    empty = tmp_path / "typo-kb"
    empty.mkdir()
    resp = client.post("/kb/connect", json={"path": str(empty)})

    assert resp.status_code == 409
    assert "no documents" in resp.json()["detail"]
    # Nothing moved: still on the original repo, index and links intact.
    assert client.app.state.repo_root == str(first)
    assert len(client.get("/documents").json()) == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM session_document").fetchone()["c"] == 1


def test_connect_force_allows_switch_to_an_existing_empty_directory(
    client, tmp_path: Path
) -> None:
    _connect_seeded_kb(client, tmp_path)
    empty = tmp_path / "deliberately-empty-kb"
    empty.mkdir()

    resp = client.post("/kb/connect", json={"path": str(empty), "force": True})

    assert resp.status_code == 200
    assert client.app.state.repo_root == str(empty)
    assert client.get("/documents").json() == []


def test_connect_allows_switch_to_a_populated_repo(client, tmp_path: Path) -> None:
    _connect_seeded_kb(client, tmp_path)
    other = tmp_path / "other-kb"
    (other / "documents").mkdir(parents=True)
    (other / "documents" / "elsewhere.md").write_text("real", encoding="utf-8")

    resp = client.post("/kb/connect", json={"path": str(other)})

    assert resp.status_code == 200
    titles = [d["title"] for d in client.get("/documents").json()]
    assert titles == ["elsewhere"]


def test_reconnecting_to_the_same_emptied_repo_is_allowed(client, tmp_path: Path) -> None:
    """Deleting the last document then reconnecting is routine, not a switch."""
    first = _connect_seeded_kb(client, tmp_path)
    (first / "documents" / "note.md").unlink()

    resp = client.post("/kb/connect", json={"path": str(first)})

    assert resp.status_code == 200
    assert resp.json()["scan"]["removed"] == 1
    assert client.get("/documents").json() == []


def test_status_reports_a_vanished_repo_instead_of_crashing(
    client, tmp_path: Path
) -> None:
    import shutil

    first = _connect_seeded_kb(client, tmp_path)
    shutil.rmtree(first)

    resp = client.get("/kb/status")

    assert resp.status_code == 409
    assert "not on disk" in resp.json()["detail"]


def test_startup_does_not_recreate_a_vanished_repo(client, tmp_path: Path) -> None:
    """The guard's whole point is that the directory must not be manifested —
    on an unmounted volume that would leave a stray tree on the mount point."""
    import shutil

    from fastapi.testclient import TestClient

    from app.main import app

    target = tmp_path / "vanishing-kb"
    (target / "documents").mkdir(parents=True)
    (target / "documents" / "note.md").write_text("hi", encoding="utf-8")
    client.post("/kb/connect", json={"path": str(target)})
    assert len(client.get("/documents").json()) == 1

    shutil.rmtree(target)
    with TestClient(app) as c2:
        assert not target.exists()  # not re-created behind the user's back
        assert c2.app.state.repo_root == str(target)
        assert len(c2.get("/documents").json()) == 1  # index survived
        assert c2.get("/kb/status").status_code == 409
