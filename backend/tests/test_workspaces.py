from __future__ import annotations

from pathlib import Path

from catalog.storage.db import Database
from catalog.storage.repo_session_document import attach_documents, list_session_documents
from catalog.storage.schema import WORKSPACE_USER_VERSION
from catalog.storage.workspace import WorkspaceManager


def test_list_and_current_without_open(client_no_workspace) -> None:
    client = client_no_workspace
    assert client.get("/workspaces").json() == []
    assert client.get("/workspaces/current").status_code == 204


def test_open_needs_confirm_then_indexes(client_no_workspace, tmp_path: Path) -> None:
    client = client_no_workspace
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "note.md").write_text("# hi", encoding="utf-8")

    preview = client.post(
        "/workspaces/open", json={"path": str(folder), "confirm": False}
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["status"] == "needs_confirm"
    assert "note.md" in body["scan"]["added"]
    assert not (folder / ".catalog" / "index.db").exists()
    assert client.get("/documents").status_code == 409

    opened = client.post(
        "/workspaces/open", json={"path": str(folder), "confirm": True}
    )
    assert opened.status_code == 200
    assert opened.json()["status"] == "ok"
    assert (folder / ".catalog" / "index.db").is_file()
    docs = client.get("/documents").json()
    assert len(docs) == 1
    assert docs[0]["title"] == "note"


def test_open_dot_resolves_to_fs_root(client_no_workspace, tmp_path: Path) -> None:
    client = client_no_workspace
    resp = client.post("/workspaces/open", json={"path": ".", "confirm": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "needs_init", "needs_confirm")
    assert body["path"] == str(tmp_path.resolve())


def test_open_empty_needs_init(client_no_workspace, tmp_path: Path) -> None:
    client = client_no_workspace
    folder = tmp_path / "empty"
    folder.mkdir()

    resp = client.post(
        "/workspaces/open", json={"path": str(folder), "confirm": False}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "needs_init"
    assert not (folder / ".catalog").exists()

    ok = client.post(
        "/workspaces/open", json={"path": str(folder), "confirm": True}
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"
    assert client.get("/documents").json() == []


def test_switch_preserves_document_ids_and_session(
    client_no_workspace, tmp_path: Path
) -> None:
    client = client_no_workspace
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "a.md").write_text("a", encoding="utf-8")
    (b / "b.md").write_text("b", encoding="utf-8")

    assert (
        client.post("/workspaces/open", json={"path": str(a), "confirm": True}).status_code
        == 200
    )
    docs_a = client.get("/documents").json()
    assert len(docs_a) == 1
    doc_a_id = docs_a[0]["id"]
    session_id = client.post("/sessions").json()["id"]
    manager: WorkspaceManager = client.app.state.workspace_manager
    assert manager.current is not None
    attach_documents(manager.current, session_id, [doc_a_id])

    assert (
        client.post("/workspaces/open", json={"path": str(b), "confirm": True}).status_code
        == 200
    )
    docs_b = client.get("/documents").json()
    assert [d["title"] for d in docs_b] == ["b"]

    assert (
        client.post("/workspaces/open", json={"path": str(a), "confirm": False}).status_code
        == 200
    )
    docs_a_again = client.get("/documents").json()
    assert docs_a_again[0]["id"] == doc_a_id
    assert manager.current is not None
    attached = list_session_documents(manager.current, session_id)
    assert [d.id for d in attached] == [doc_a_id]


def test_open_blocked_while_run_active(client_no_workspace, tmp_path: Path) -> None:
    client = client_no_workspace
    a = tmp_path / "wa"
    b = tmp_path / "wb"
    a.mkdir()
    b.mkdir()
    assert (
        client.post("/workspaces/open", json={"path": str(a), "confirm": True}).status_code
        == 200
    )
    manager: WorkspaceManager = client.app.state.workspace_manager
    assert manager.current is not None
    with manager.current.connect() as conn:
        conn.execute(
            "INSERT INTO skill_run(id, skill_id, status, started_at) "
            "VALUES ('r1', 's1', 'running', '2026-01-01T00:00:00Z')"
        )

    blocked = client.post(
        "/workspaces/open", json={"path": str(b), "confirm": True}
    )
    assert blocked.status_code == 409

    with manager.current.connect() as conn:
        conn.execute("UPDATE skill_run SET status = 'ok' WHERE id = 'r1'")

    ok = client.post("/workspaces/open", json={"path": str(b), "confirm": True})
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"


def test_rescan_report(client_no_workspace, tmp_path: Path) -> None:
    client = client_no_workspace
    folder = tmp_path / "scanme"
    folder.mkdir()
    assert (
        client.post(
            "/workspaces/open", json={"path": str(folder), "confirm": True}
        ).status_code
        == 200
    )
    (folder / "new.md").write_text("x", encoding="utf-8")
    resp = client.post("/workspaces/rescan")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"added", "updated", "renamed", "removed", "skipped"}
    assert len(body["added"]) == 1


def test_rescan_requires_open(client_no_workspace) -> None:
    assert client_no_workspace.post("/workspaces/rescan").status_code == 409


def test_browse_lists_dirs_and_blocks_escape(
    client_no_workspace, tmp_path: Path
) -> None:
    client = client_no_workspace
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "child").mkdir()
    (inside / "child" / ".catalog").mkdir()
    (inside / "child" / ".catalog" / "index.db").write_bytes(b"")
    (inside / "file.md").write_text("x", encoding="utf-8")

    listed = client.get("/fs/browse", params={"path": str(inside)})
    assert listed.status_code == 200
    names = {e["name"] for e in listed.json()}
    assert names == {"child"}
    child = listed.json()[0]
    assert child["has_catalog"] is True

    escape = client.get("/fs/browse", params={"path": str(inside / ".." / "..")})
    assert escape.status_code == 400

    outside = Path("/tmp")
    if not str(outside.resolve()).startswith(str(tmp_path.resolve())):
        abs_out = client.get("/fs/browse", params={"path": str(outside)})
        assert abs_out.status_code == 400


def test_browse_blocks_symlink_escape(
    client_no_workspace, tmp_path: Path, tmp_path_factory
) -> None:
    client = client_no_workspace
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path_factory.mktemp("outside_fs_root")
    link = root / "escape"
    try:
        link.symlink_to(outside)
    except OSError:
        return
    assert not str(outside.resolve()).startswith(str(tmp_path.resolve()))
    listed = client.get("/fs/browse", params={"path": str(root)})
    assert listed.status_code == 200
    assert listed.json() == []


def test_open_incompatible_schema(client_no_workspace, tmp_path: Path) -> None:
    client = client_no_workspace
    folder = tmp_path / "bad"
    catalog = folder / ".catalog"
    catalog.mkdir(parents=True)
    bad = Database(str(catalog / "index.db"))
    bad.init_schema(user_version=999)
    resp = client.post(
        "/workspaces/open", json={"path": str(folder), "confirm": False}
    )
    assert resp.status_code == 400
    assert client.get("/workspaces/current").status_code == 204


def test_registry_after_open(client_no_workspace, tmp_path: Path) -> None:
    client = client_no_workspace
    folder = tmp_path / "reg"
    folder.mkdir()
    client.post("/workspaces/open", json={"path": str(folder), "confirm": True})
    reg = client.get("/workspaces").json()
    assert len(reg) == 1
    assert reg[0]["path"] == str(folder.resolve())
    assert reg[0]["display_name"] == "reg"
    assert reg[0]["last_opened"]
    cur = client.get("/workspaces/current")
    assert cur.status_code == 200
    assert cur.json()["path"] == str(folder.resolve())


def test_open_existing_catalog_without_confirm(
    client_no_workspace, tmp_path: Path
) -> None:
    client = client_no_workspace
    folder = tmp_path / "ready"
    folder.mkdir()
    manager: WorkspaceManager = client.app.state.workspace_manager
    manager.open(folder, confirm_init=True)
    manager.close()
    (folder / "doc.md").write_text("hi", encoding="utf-8")

    resp = client.post(
        "/workspaces/open", json={"path": str(folder), "confirm": False}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert client.get("/documents").json()[0]["title"] == "doc"
    assert manager.current is not None
    assert manager.current.user_version() == WORKSPACE_USER_VERSION

