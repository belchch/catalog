from __future__ import annotations

from catalog.llm.base import CompletionResult
from catalog.storage.repo_custom_check import (
    create_custom_check,
    get_custom_check,
    hide_custom_check,
    list_custom_checks,
)


def test_repo_create_list_hide(db) -> None:
    row = create_custom_check(db, name="  Python  ", prompt="  есть Python  ")
    assert row.name == "Python"
    assert row.prompt == "есть Python"
    assert row.hidden is False
    assert list_custom_checks(db)[0].id == row.id
    assert hide_custom_check(db, row.id) is True
    hidden = get_custom_check(db, row.id)
    assert hidden is not None
    assert hidden.hidden is True
    assert list_custom_checks(db) == []
    assert list_custom_checks(db, include_hidden=True)[0].id == row.id
    assert hide_custom_check(db, "missing") is False


def test_list_verify_checks_catalog(client) -> None:
    resp = client.get("/verify-checks")
    assert resp.status_code == 200
    body = resp.json()
    assert "non_empty" in body["builtin"]
    assert "custom" not in body["builtin"]
    assert body["labels"]["non_empty"] == "Не пустой"
    assert set(body["labels"]) == set(body["builtin"])


def test_custom_checks_rest_create_list_hide(client) -> None:
    created = client.post(
        "/custom-checks",
        json={"name": "Python", "prompt": "есть опыт Python"},
    )
    assert created.status_code == 200
    payload = created.json()
    check_id = payload["id"]
    assert payload["name"] == "Python"
    assert payload["hidden"] is False

    listed = client.get("/custom-checks")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [check_id]

    hidden = client.post(f"/custom-checks/{check_id}/hide")
    assert hidden.status_code == 204
    assert client.get("/custom-checks").json() == []
    assert client.post(f"/custom-checks/{check_id}/hide").status_code == 204
    assert client.post("/custom-checks/missing/hide").status_code == 404


def test_custom_checks_create_rejects_empty(client) -> None:
    resp = client.post("/custom-checks", json={"name": "  ", "prompt": "x"})
    assert resp.status_code == 422


def test_custom_checks_no_delete_route(client, db) -> None:
    created = client.post(
        "/custom-checks",
        json={"name": "Python", "prompt": "есть опыт Python"},
    )
    check_id = created.json()["id"]
    resp = client.delete(f"/custom-checks/{check_id}")
    assert resp.status_code in {404, 405}
    row = get_custom_check(db, check_id)
    assert row is not None
    assert row.hidden is False


def test_custom_checks_preview(client, provider) -> None:
    provider.script.append(
        CompletionResult(content="PASS", tool_calls=[], finish_reason="stop")
    )
    resp = client.post(
        "/custom-checks/preview",
        json={"prompt": "есть опыт Python", "sample": "Python 5 лет"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"passed": True, "failures": []}
    assert provider.requests
    message = provider.requests[0]["messages"][0]
    assert message.role == "user"
    assert "есть опыт Python" in (message.content or "")
    assert "Python 5 лет" in (message.content or "")


def test_custom_checks_preview_uses_active_model(client, provider) -> None:
    client.app.state.active_model = "ui/selected-model"
    provider.script.append(
        CompletionResult(content="PASS", tool_calls=[], finish_reason="stop")
    )
    resp = client.post(
        "/custom-checks/preview",
        json={"prompt": "есть опыт Python", "sample": "Python 5 лет"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"passed": True, "failures": []}
    assert provider.requests[0]["model"] == "ui/selected-model"


def test_custom_checks_preview_fail(client, provider) -> None:
    provider.script.append(
        CompletionResult(
            content="FAIL: нет стека", tool_calls=[], finish_reason="stop"
        )
    )
    resp = client.post(
        "/custom-checks/preview",
        json={"prompt": "есть опыт Python", "sample": "только Java"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["passed"] is False
    assert body["failures"] == ["custom:preview: нет стека"]


def test_custom_checks_require_workspace(client_no_workspace) -> None:
    resp = client_no_workspace.get("/custom-checks")
    assert resp.status_code == 409


def test_custom_checks_preview_does_not_persist(client, provider, db) -> None:
    provider.script.append(
        CompletionResult(content="PASS", tool_calls=[], finish_reason="stop")
    )
    resp = client.post(
        "/custom-checks/preview",
        json={"prompt": "есть опыт Python", "sample": "Python 5 лет"},
    )
    assert resp.status_code == 200
    assert list_custom_checks(db, include_hidden=True) == []
