from fastapi.testclient import TestClient

from app.main import app


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
