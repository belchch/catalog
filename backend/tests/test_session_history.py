from __future__ import annotations

import time

from app.storage.repo_message import add_message, list_messages
from app.storage.repo_session import create_session, get_session, list_sessions


def test_list_get_delete_sessions(client, db) -> None:
    a = client.post("/sessions").json()["id"]
    b = client.post("/sessions").json()["id"]
    add_message(db, session_id=a, role="user", content="Первый диалог про отчёт")
    add_message(db, session_id=a, role="assistant", content="План по отчёту")
    time.sleep(0.01)
    add_message(db, session_id=b, role="user", content="Второй диалог")
    add_message(db, session_id=b, role="assistant", content="Ответ")

    listing = client.get("/sessions")
    assert listing.status_code == 200
    items = listing.json()
    ids = [s["id"] for s in items]
    assert b in ids and a in ids
    assert ids.index(b) < ids.index(a)

    by_id = {s["id"]: s for s in items}
    assert by_id[a]["title"] == "Первый диалог про отчёт"
    assert by_id[b]["title"] == "Второй диалог"
    assert by_id[a]["status"] == "planning"
    assert by_id[a]["updated_at"]
    assert by_id[a]["created_at"]

    msgs = client.get(f"/sessions/{a}/messages")
    assert msgs.status_code == 200
    body = msgs.json()
    assert [m["role"] for m in body] == ["user", "assistant"]
    assert body[0]["content"] == "Первый диалог про отчёт"
    assert all(m["session_id"] == a for m in body)

    other = client.get(f"/sessions/{b}/messages").json()
    assert all(m["session_id"] == b for m in other)
    assert not any(m["session_id"] == a for m in other)

    deleted = client.delete(f"/sessions/{a}")
    assert deleted.status_code == 204

    after = client.get("/sessions").json()
    assert a not in [s["id"] for s in after]
    assert b in [s["id"] for s in after]

    assert client.get(f"/sessions/{a}/messages").status_code == 404
    assert client.delete(f"/sessions/{a}").status_code == 404
    assert list_messages(db, a) == []
    assert get_session(db, a) is None


def test_list_sessions_status_filter(client, db) -> None:
    a = create_session(db, status="planning")
    b = create_session(db, status="done")
    add_message(db, session_id=a, role="user", content="planning one")
    add_message(db, session_id=b, role="user", content="done one")

    only_done = client.get("/sessions", params={"status": "done"})
    assert only_done.status_code == 200
    ids = [s["id"] for s in only_done.json()]
    assert b in ids
    assert a not in ids


def test_title_set_only_from_first_user_message(db) -> None:
    sid = create_session(db)
    add_message(db, session_id=sid, role="assistant", content="привет")
    row = get_session(db, sid)
    assert row is not None
    assert row.title is None

    add_message(db, session_id=sid, role="user", content="Заголовок сессии")
    add_message(db, session_id=sid, role="user", content="Второе сообщение")
    row = get_session(db, sid)
    assert row is not None
    assert row.title == "Заголовок сессии"


def test_list_sessions_repo_order(db) -> None:
    first = create_session(db)
    second = create_session(db)
    add_message(db, session_id=first, role="user", content="old")
    time.sleep(0.01)
    add_message(db, session_id=second, role="user", content="new")
    rows = list_sessions(db)
    assert [r.id for r in rows[:2]] == [second, first]
