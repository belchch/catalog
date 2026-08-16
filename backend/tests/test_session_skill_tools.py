from __future__ import annotations

import asyncio
import json
import re

from catalog.agent.registry import ToolRegistry
from catalog.api.sessions import _ws_session_tools
from catalog.skills.config import SkillConfig, VerifyCheck
from catalog.skills.repo_run import get_run
from catalog.skills.repo_skill import create_skill, get_skill
from catalog.skills.skill_tools import (
    SESSION_TOOL_PARENT_RUN_ID,
    build_session_skill_tools,
    config_hash,
    skill_tool_name,
)
from catalog.storage.db import Database
from catalog.storage.repo_document import list_documents
from catalog.storage.repo_session import create_session
from catalog.storage.repo_session_skill import (
    attach_skills,
    detach_skills,
    list_session_skills,
)


_TOOL_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def _script_skill(
    db: Database,
    *,
    name: str = "Upper Text",
    code: str = "def main(document):\n    return document.upper()\n",
    verify_checks: list[VerifyCheck] | None = None,
    input_arity: int | None = 1,
) -> str:
    config = SkillConfig(
        name=name,
        description="Uppercase input",
        system_prompt="",
        allowed_tools=[],
        model="x",
        kind="script",
        code=code,
        verify_checks=verify_checks
        if verify_checks is not None
        else [VerifyCheck(check="non_empty")],
        input_arity=input_arity,
    )
    return create_skill(
        db,
        name=config.name,
        description=config.description,
        config=config,
        status="committed",
    )


def _agent_skill(db: Database, *, name: str = "Agent Skill") -> str:
    config = SkillConfig(
        name=name,
        description="Agent",
        system_prompt="do things",
        allowed_tools=["read_document"],
        model="x",
        kind="agent",
    )
    return create_skill(
        db,
        name=config.name,
        description=config.description,
        config=config,
        status="committed",
    )


def test_attach_detach_list_session_skills(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    missing = "missing-skill"
    assert attach_skills(db, sid, [skill_id, missing]) == [missing]
    rows = list_session_skills(db, sid)
    assert len(rows) == 1
    assert rows[0].id == skill_id
    assert detach_skills(db, sid, [skill_id]) == 1
    assert list_session_skills(db, sid) == []
    assert detach_skills(db, sid, [skill_id]) == 0


def test_session_skill_tool_runs_script_and_pins(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    assert _TOOL_NAME_RE.match(name)

    tools = build_session_skill_tools(
        db,
        sid,
        workspace_dir="/tmp",
        base_tools=ToolRegistry(),
    )
    assert name in tools.names()
    _, fn = tools.get(name)
    assert fn is not None

    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is True
    assert out["text"] == "HELLO"
    assert out["skill_id"] == skill_id
    assert out["config_hash"] == config_hash(record.config.to_json())
    assert out["run_id"]
    assert out["verify_failures"] == []
    assert list(out) == [
        "ok",
        "status",
        "run_id",
        "skill_id",
        "skill_name",
        "config_hash",
        "verify_failures",
        "text",
    ]

    run = get_run(db, out["run_id"])
    assert run is not None
    assert run["parent_run_id"] == SESSION_TOOL_PARENT_RUN_ID
    assert run["persist"] is False
    assert run["output_doc_id"] is None
    assert run["result_text"] == "HELLO"
    entries = json.loads(run["trace_json"] or "[]")
    pins = [e for e in entries if e["kind"] == "skill_pin"]
    assert pins
    assert pins[0]["data"]["skill_id"] == skill_id
    assert pins[0]["data"]["config_hash"] == out["config_hash"]
    verify = [e for e in entries if e["kind"] == "verify"]
    assert verify
    assert verify[0]["data"]["passed"] is True
    assert list_documents(db) == []


def test_get_run_returns_parent_run_id(client, db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    tools = build_session_skill_tools(
        db, sid, workspace_dir="/tmp", base_tools=ToolRegistry()
    )
    _, fn = tools.get(name)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    run = client.get(f"/runs/{out['run_id']}").json()
    assert run["parent_run_id"] == SESSION_TOOL_PARENT_RUN_ID
    assert run["id"] == out["run_id"]
    assert run["result_text"] == "HELLO"


def test_session_skill_tool_verify_failure(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(
        db,
        verify_checks=[VerifyCheck(check="min_length", params={"min": 100})],
    )
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    tools = build_session_skill_tools(
        db, sid, workspace_dir="/tmp", base_tools=ToolRegistry()
    )
    _, fn = tools.get(name)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is False
    assert out["verify_failures"]


def test_session_skill_tool_requires_text(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    tools = build_session_skill_tools(
        db, sid, workspace_dir="/tmp", base_tools=ToolRegistry()
    )
    _, fn = tools.get(name)
    assert fn is not None
    out = asyncio.run(fn())
    assert out["ok"] is False
    assert out["error"] == "provide text or texts"


def test_skill_tool_name_collisions() -> None:
    class _Rec:
        def __init__(self, name: str, skill_id: str) -> None:
            self.name = name
            self.id = skill_id

    used: set[str] = set()
    first = skill_tool_name(_Rec("Upper Text", "aaaaaaaaaaaaaaaa"), used=used)
    second = skill_tool_name(_Rec("Upper Text", "bbbbbbbbbbbbbbbb"), used=used)
    reserved = skill_tool_name(_Rec("list_documents", "cccccccc"), used=used)
    assert first == "skill_upper_text"
    assert second == "skill_upper_text_bbbbbbbb"
    assert reserved == "skill_list_documents"
    assert first != second
    assert _TOOL_NAME_RE.match(first)
    assert _TOOL_NAME_RE.match(second)
    assert _TOOL_NAME_RE.match(reserved)


def test_agent_skill_is_not_registered_as_tool(db: Database) -> None:
    sid = create_session(db)
    script_id = _script_skill(db)
    agent_id = _agent_skill(db)
    attach_skills(db, sid, [script_id, agent_id])
    assert {s.id for s in list_session_skills(db, sid)} == {script_id, agent_id}
    tools = build_session_skill_tools(
        db, sid, workspace_dir="/tmp", base_tools=ToolRegistry()
    )
    names = tools.names()
    assert any(n.startswith("skill_upper") for n in names)
    assert not any("agent" in n for n in names)
    assert len(names) == 1


def test_ws_session_tools_includes_attached_script(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    expected = skill_tool_name(record, used=set())

    class _WS:
        async def send_json(self, payload: dict) -> None:
            return None

    tools = _ws_session_tools(db, "/tmp", sid, ToolRegistry(), _WS())
    assert expected in tools.names()
    assert "list_documents" in tools.names()
    assert "save_skill_prompt" in tools.names()


def test_rest_attach_detach_list_session_tools(client, db: Database) -> None:
    session_id = client.post("/sessions").json()["id"]
    skill_id = _script_skill(db)
    missing = "no-such-skill"

    listed = client.get(f"/sessions/{session_id}/tools")
    assert listed.status_code == 200
    assert listed.json() == []

    attached = client.post(
        f"/sessions/{session_id}/tools",
        json={"skill_ids": [skill_id, missing]},
    )
    assert attached.status_code == 200
    body = attached.json()
    assert body["skipped_skill_ids"] == [missing]
    assert [s["id"] for s in body["skills"]] == [skill_id]
    assert body["skills"][0]["kind"] == "script"

    listed2 = client.get(f"/sessions/{session_id}/tools")
    assert [s["id"] for s in listed2.json()] == [skill_id]

    gone = client.delete(f"/sessions/{session_id}/tools/{skill_id}")
    assert gone.status_code == 204
    assert client.get(f"/sessions/{session_id}/tools").json() == []
    assert client.delete(f"/sessions/{session_id}/tools/{skill_id}").status_code == 404
    assert client.get("/sessions/missing/tools").status_code == 404
    assert (
        client.post(
            "/sessions/missing/tools", json={"skill_ids": [skill_id]}
        ).status_code
        == 404
    )
    empty = client.post(f"/sessions/{session_id}/tools", json={"skill_ids": []})
    assert empty.status_code == 422
