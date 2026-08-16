import sys
import types

from fastapi.testclient import TestClient

from catalog.build_stamp import write_build_sha
from catalog.main import app


def test_health_ok() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "git_sha" in body


def test_health_git_sha(monkeypatch) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "git_sha": "abc1234"}


def _fake_build_sha(monkeypatch, sha: str) -> None:
    module = types.ModuleType("catalog._build_sha")
    module.GIT_SHA = sha
    monkeypatch.setitem(sys.modules, "catalog._build_sha", module)


def _without_repo_git(monkeypatch) -> None:
    monkeypatch.setattr("catalog.main._REPO_GIT_SHA", None)
    monkeypatch.setattr("catalog.main.git_sha_from_repo", lambda *a, **kw: "")


def test_health_git_sha_from_baked_stamp(monkeypatch) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    _without_repo_git(monkeypatch)
    _fake_build_sha(monkeypatch, "deadbee")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "git_sha": "deadbee"}


def test_health_repo_git_wins_over_baked_stamp(monkeypatch) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.setattr("catalog.main._REPO_GIT_SHA", None)
    monkeypatch.setattr("catalog.main.git_sha_from_repo", lambda *a, **kw: "fromrepo")
    _fake_build_sha(monkeypatch, "deadbee")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.json() == {"status": "ok", "git_sha": "fromrepo"}


def test_health_env_wins_over_baked_stamp(monkeypatch) -> None:
    monkeypatch.setenv("GIT_SHA", "fromenv")
    _fake_build_sha(monkeypatch, "deadbee")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.json() == {"status": "ok", "git_sha": "fromenv"}


def test_write_build_sha_stamps_module(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GIT_SHA", "cafe123")
    target = tmp_path / "_build_sha.py"
    assert write_build_sha(target) == "cafe123"
    assert target.read_text(encoding="utf-8") == 'GIT_SHA = "cafe123"\n'


def test_write_build_sha_skips_unusable_value(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GIT_SHA", "not a sha")
    target = tmp_path / "_build_sha.py"
    assert write_build_sha(target) == ""
    assert not target.exists()
