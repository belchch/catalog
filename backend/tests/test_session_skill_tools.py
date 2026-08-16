from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import replace
from pathlib import Path

from catalog.agent.registry import ToolRegistry
from catalog.agent.runner import run_agent_collect
from catalog.api.sessions import _ws_session_tools
from catalog.documents.ingest import ingest_file
from catalog.documents.tools import build_document_tools
from catalog.llm.base import CompletionResult, Message, ToolCall
from catalog.skills.apply import apply_skill_collect
from catalog.skills.budget import (
    SkillBudget,
    estimate_skill_budget,
    make_turn_budget,
    nested_skill_hold,
    turn_deadline_seconds,
)
from catalog.skills.config import PipelineStep, SkillConfig, VerifyCheck
from catalog.skills.repo_run import get_run
from catalog.skills.repo_skill import create_skill, get_skill
from catalog.skills.skill_tools import (
    SESSION_TOOL_PARENT_RUN_ID,
    SkillCallContext,
    build_session_skill_tools,
    config_hash,
    skill_tool_name,
)
from catalog.storage.db import Database
from catalog.storage.repo_custom_check import create_custom_check
from catalog.storage.repo_document import list_documents
from catalog.storage.repo_session import create_session
from catalog.storage.repo_session_skill import (
    attach_skills,
    detach_skills,
    list_session_skills,
)


_TOOL_NAME_RE = re.compile(r"^[a-z0-9_]+$")


class _JudgeProvider:
    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.requests: list[dict] = []

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools=None,
        temperature: float = 0.0,
        **kwargs,
    ) -> CompletionResult:
        self.requests.append({"model": model, "messages": messages, "tools": tools})
        if not self.answers:
            raise AssertionError("judge script exhausted")
        return CompletionResult(
            content=self.answers.pop(0),
            tool_calls=[],
            finish_reason="stop",
        )


def _script_skill(
    db: Database,
    *,
    name: str = "Upper Text",
    code: str = "def main(document):\n    return document.upper()\n",
    verify_checks: list[VerifyCheck] | None = None,
    input_arity: int | None = 1,
    model: str = "x",
    provider: str = "",
) -> str:
    config = SkillConfig(
        name=name,
        description="Uppercase input",
        system_prompt="",
        allowed_tools=[],
        model=model,
        provider=provider,
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


def _agent_skill(
    db: Database,
    *,
    name: str = "Agent Skill",
    max_iterations: int = 8,
    max_retries: int = 2,
) -> str:
    config = SkillConfig(
        name=name,
        description="Agent",
        system_prompt="do things",
        allowed_tools=["read_document"],
        model="x",
        kind="agent",
        max_iterations=max_iterations,
        max_retries=max_retries,
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
    assert out["depth"] == 1
    assert out["verify_failures"] == []
    assert list(out) == [
        "ok",
        "status",
        "run_id",
        "skill_id",
        "skill_name",
        "config_hash",
        "depth",
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
    assert pins[0]["data"]["depth"] == 1
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


def test_session_skill_tool_custom_verify_uses_provider(db: Database) -> None:
    row = create_custom_check(db, name="Has Hello", prompt="contains hello")
    sid = create_session(db)
    skill_id = _script_skill(
        db,
        model="",
        verify_checks=[VerifyCheck(check=f"custom:{row.id}")],
    )
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    provider = _JudgeProvider(["PASS"])
    tools = build_session_skill_tools(
        db,
        sid,
        workspace_dir="/tmp",
        base_tools=ToolRegistry(),
        provider=provider,
        fallback_model="workspace/model",
    )
    _, fn = tools.get(name)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is True
    assert out["verify_failures"] == []
    assert len(provider.requests) == 1
    assert provider.requests[0]["model"] == "workspace/model"


def test_session_skill_tool_custom_verify_uses_pinned_provider(
    db: Database,
) -> None:
    row = create_custom_check(db, name="Has Hello", prompt="contains hello")
    sid = create_session(db)
    skill_id = _script_skill(
        db,
        model="",
        provider="zai",
        verify_checks=[VerifyCheck(check=f"custom:{row.id}")],
    )
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    workspace = _JudgeProvider(["SHOULD NOT RUN"])
    pinned = _JudgeProvider(["PASS"])
    tools = build_session_skill_tools(
        db,
        sid,
        workspace_dir="/tmp",
        base_tools=ToolRegistry(),
        provider=workspace,
        fallback_model="workspace/model",
        providers={"openrouter": workspace, "zai": pinned},
    )
    _, fn = tools.get(name)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is True
    assert pinned.requests
    assert workspace.requests == []


def test_session_skill_tool_custom_verify_without_provider_fails(
    db: Database,
) -> None:
    row = create_custom_check(db, name="Has Hello", prompt="contains hello")
    sid = create_session(db)
    skill_id = _script_skill(
        db,
        model="",
        verify_checks=[VerifyCheck(check=f"custom:{row.id}")],
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
    assert any(
        "missing model" in f or "provider" in f or "judge error" in f
        for f in out["verify_failures"]
    )


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


def test_ws_session_tools_custom_verify_uses_provider(db: Database) -> None:
    row = create_custom_check(db, name="Has Hello", prompt="contains hello")
    sid = create_session(db)
    skill_id = _script_skill(
        db,
        model="",
        verify_checks=[VerifyCheck(check=f"custom:{row.id}")],
    )
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    expected = skill_tool_name(record, used=set())

    class _WS:
        async def send_json(self, payload: dict) -> None:
            return None

    provider = _JudgeProvider(["PASS"])
    tools = _ws_session_tools(
        db,
        "/tmp",
        sid,
        ToolRegistry(),
        _WS(),
        provider=provider,
        fallback_model="ws/model",
    )
    _, fn = tools.get(expected)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is True
    assert provider.requests[0]["model"] == "ws/model"


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


def test_depth_2_registers_no_skill_tools(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    attach_skills(db, sid, [skill_id])
    tools = build_session_skill_tools(
        db,
        sid,
        workspace_dir="/tmp",
        base_tools=ToolRegistry(),
        call_context=SkillCallContext(depth=2),
    )
    assert tools.names() == []


def test_chain_skips_self_registers_neighbor(db: Database) -> None:
    sid = create_session(db)
    skill_a = _script_skill(db, name="Alpha")
    skill_b = _script_skill(db, name="Beta")
    attach_skills(db, sid, [skill_a, skill_b])
    rec_a = get_skill(db, skill_a)
    rec_b = get_skill(db, skill_b)
    assert rec_a is not None and rec_b is not None
    name_a = skill_tool_name(rec_a, used=set())
    name_b = skill_tool_name(rec_b, used=set())
    tools = build_session_skill_tools(
        db,
        sid,
        workspace_dir="/tmp",
        base_tools=ToolRegistry(),
        call_context=SkillCallContext(depth=1, chain=(skill_a,)),
    )
    names = tools.names()
    assert name_a not in names
    assert name_b in names


def test_self_call_a_to_a_is_impossible(db: Database) -> None:
    sid = create_session(db)
    skill_a = _script_skill(db, name="Alpha")
    attach_skills(db, sid, [skill_a])
    rec_a = get_skill(db, skill_a)
    assert rec_a is not None
    name_a = skill_tool_name(rec_a, used=set())
    root = build_session_skill_tools(
        db, sid, workspace_dir="/tmp", base_tools=ToolRegistry()
    )
    assert name_a in root.names()
    _, fn = root.get(name_a)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is True
    assert out["depth"] == 1
    nested = build_session_skill_tools(
        db,
        sid,
        workspace_dir="/tmp",
        base_tools=ToolRegistry(),
        call_context=SkillCallContext(depth=1, chain=(skill_a,)),
    )
    assert name_a not in nested.names()
    assert nested.names() == []


def test_estimate_skill_budget_by_kind() -> None:
    script = SkillConfig(
        name="s",
        description="",
        system_prompt="",
        allowed_tools=[],
        model="x",
        kind="script",
        max_iterations=8,
        max_retries=2,
    )
    agent = SkillConfig(
        name="a",
        description="",
        system_prompt="p",
        allowed_tools=[],
        model="x",
        kind="agent",
        max_iterations=8,
        max_retries=2,
    )
    pipeline = SkillConfig(
        name="p",
        description="",
        system_prompt="",
        allowed_tools=[],
        model="x",
        kind="pipeline",
        max_iterations=5,
        steps=[
            PipelineStep(id="one", type="llm"),
            PipelineStep(id="two", type="script"),
            PipelineStep(id="three", type="llm"),
        ],
    )
    assert estimate_skill_budget(script) == (0, 1)
    assert estimate_skill_budget(agent) == (24, 1)
    assert estimate_skill_budget(pipeline) == (15, 1)


def test_budget_reserve_release_two_of_twenty_four() -> None:
    budget = SkillBudget(llm_calls_left=60, nested_runs_left=20)
    hold = budget.reserve(24, 1)
    assert hold is not None
    assert budget.snapshot() == {"llm_calls_left": 36, "nested_runs_left": 19}
    hold.charge_llm()
    hold.charge_llm()
    budget.release(hold)
    assert hold.llm_used == 2
    assert budget.llm_calls_left == 58
    assert budget.nested_runs_left == 19


def test_agent_skill_does_not_start_when_budget_short(db: Database) -> None:
    sid = create_session(db)
    skill_id = _agent_skill(db)
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    provider = _JudgeProvider(["SHOULD NOT RUN"])
    budget = SkillBudget(llm_calls_left=5, nested_runs_left=20)
    tools = build_session_skill_tools(
        db,
        sid,
        workspace_dir="/tmp",
        base_tools=ToolRegistry(),
        provider=provider,
        budget=budget,
        kinds=frozenset({"agent"}),
    )
    _, fn = tools.get(name)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is False
    assert out["error"] == "budget exhausted"
    assert out["budget"]["needed_llm_calls"] == 24
    assert out["budget"]["needed_nested_runs"] == 1
    assert out["budget"]["llm_calls_left"] == 5
    assert out["budget"]["nested_runs_left"] == 20
    assert provider.requests == []
    run = get_run(db, out["run_id"])
    assert run is not None
    entries = json.loads(run["trace_json"] or "[]")
    nodes = [e for e in entries if e["kind"] == "budget"]
    assert nodes
    assert nodes[0]["data"]["error"] == "budget exhausted"


def test_budget_returns_unused_after_two_nested_llm_calls(
    db: Database, client
) -> None:
    workspace = Path(client.app.state.workspace_manager.root)
    doc_id = ingest_file(db, workspace, filename="in.md", content=b"hello").id
    skill_id = _agent_skill(db)
    record = get_skill(db, skill_id)
    assert record is not None
    provider = _JudgeProvider([])
    provider.answers = []

    class _TwoCallProvider(_JudgeProvider):
        def __init__(self) -> None:
            super().__init__([])
            self.step = 0

        async def complete(self, model, messages, tools=None, temperature=0.0, **kwargs):
            self.requests.append({"model": model})
            self.step += 1
            if self.step == 1:
                return CompletionResult(
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="c1",
                            name="read_document",
                            arguments={"doc_id": doc_id},
                        )
                    ],
                    finish_reason="tool_calls",
                )
            return CompletionResult(
                content="done",
                tool_calls=[],
                finish_reason="stop",
            )

    two = _TwoCallProvider()
    budget = SkillBudget(llm_calls_left=60, nested_runs_left=20)
    hold = budget.reserve(*estimate_skill_budget(record.config))
    assert hold is not None
    assert hold.llm_reserved == 24

    def _run() -> None:
        with nested_skill_hold(hold):
            asyncio.run(
                apply_skill_collect(
                    provider=two,
                    db=db,
                    workspace_dir=str(workspace),
                    skill=record.config,
                    skill_id=skill_id,
                    input_doc_ids=[doc_id],
                    base_tools=build_document_tools(db, workspace),
                    persist=False,
                )
            )

    try:
        _run()
    finally:
        budget.release(hold)
    assert two.step == 2
    assert hold.llm_used == 2
    assert budget.llm_calls_left == 58
    assert budget.nested_runs_left == 19


def test_budget_release_on_exception(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(
        db,
        code="def main(document):\n    return 1 / 0\n",
    )
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    budget = SkillBudget(llm_calls_left=60, nested_runs_left=20)
    tools = build_session_skill_tools(
        db, sid, workspace_dir="/tmp", base_tools=ToolRegistry(), budget=budget
    )
    _, fn = tools.get(name)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is False
    assert out["error"]
    assert budget.llm_calls_left == 60
    assert budget.nested_runs_left == 19


def test_script_tool_refuses_when_run_budget_exhausted(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    budget = SkillBudget(llm_calls_left=60, nested_runs_left=0)
    tools = build_session_skill_tools(
        db, sid, workspace_dir="/tmp", base_tools=ToolRegistry(), budget=budget
    )
    _, fn = tools.get(name)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is False
    assert out["error"] == "budget exhausted"
    assert out["budget"]["nested_runs_left"] == 0
    assert budget.nested_runs_left == 0


def test_next_budget_is_fresh(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    first = SkillBudget(llm_calls_left=60, nested_runs_left=1)
    tools_first = build_session_skill_tools(
        db, sid, workspace_dir="/tmp", base_tools=ToolRegistry(), budget=first
    )
    _, fn_first = tools_first.get(name)
    assert fn_first is not None
    assert asyncio.run(fn_first(text="hello"))["ok"] is True
    assert first.nested_runs_left == 0
    assert asyncio.run(fn_first(text="hello"))["error"] == "budget exhausted"
    second = SkillBudget(llm_calls_left=60, nested_runs_left=1)
    tools_second = build_session_skill_tools(
        db, sid, workspace_dir="/tmp", base_tools=ToolRegistry(), budget=second
    )
    _, fn_second = tools_second.get(name)
    assert fn_second is not None
    assert asyncio.run(fn_second(text="hello"))["ok"] is True
    assert second.nested_runs_left == 0
    assert first.nested_runs_left == 0


def test_planner_iterations_do_not_charge_budget() -> None:
    budget = SkillBudget(llm_calls_left=60, nested_runs_left=20)

    class _PlannerProvider(_JudgeProvider):
        async def complete(self, model, messages, tools=None, temperature=0.0, **kwargs):
            self.requests.append({"model": model})
            return CompletionResult(
                content="plan",
                tool_calls=[],
                finish_reason="stop",
            )

    provider = _PlannerProvider(["plan"])
    text, _trace, capped = asyncio.run(
        run_agent_collect(
            provider=provider,
            model="x",
            system_prompt="planner",
            messages=[Message(role="user", content="hi")],
            tools=ToolRegistry(),
            use_stream=False,
        )
    )
    assert text == "plan"
    assert capped is False
    assert len(provider.requests) == 1
    assert budget.snapshot() == {"llm_calls_left": 60, "nested_runs_left": 20}


def test_ws_budget_exhausted_does_not_fail_turn(client, provider, db) -> None:
    client.app.state.settings = replace(
        client.app.state.settings, skill_budget_nested_runs=0
    )
    sid = client.post("/sessions").json()["id"]
    skill_id = _script_skill(db)
    client.post(f"/sessions/{sid}/tools", json={"skill_ids": [skill_id]})
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    provider.script = [
        CompletionResult(
            content=None,
            tool_calls=[ToolCall(id="t1", name=name, arguments={"text": "one"})],
            finish_reason="tool_calls",
        ),
        CompletionResult(content="продолжаю", tool_calls=[], finish_reason="stop"),
    ]
    with client.websocket_connect(f"/sessions/{sid}") as ws:
        first = ws.receive_json()
        assert first.get("type") == "suggestions"
        ws.send_text("вызови скилл")
        frames: list[dict] = []
        while True:
            frame = ws.receive_json()
            frames.append(frame)
            if frame.get("type") == "finish":
                break
    results = [f for f in frames if f.get("type") == "tool_result"]
    assert len(results) == 1
    payload = json.loads(results[0]["result"])
    assert payload["ok"] is False
    assert payload["error"] == "budget exhausted"
    assert frames[-1]["status"] == "ok"


def test_turn_deadline_seconds_uses_session_timeout_and_floor() -> None:
    assert turn_deadline_seconds(30) == 600
    assert turn_deadline_seconds(60) == 900
    assert turn_deadline_seconds(120) == 1800
    at_floor = make_turn_budget(
        llm_calls_left=60,
        nested_runs_left=20,
        llm_timeout_seconds=30,
        now=1000.0,
    )
    from_session = make_turn_budget(
        llm_calls_left=60,
        nested_runs_left=20,
        llm_timeout_seconds=120,
        now=1000.0,
    )
    default_timeout = make_turn_budget(
        llm_calls_left=60,
        nested_runs_left=20,
        llm_timeout_seconds=60,
        now=1000.0,
    )
    assert at_floor.deadline_monotonic == 1600.0
    assert from_session.deadline_monotonic == 2800.0
    assert default_timeout.deadline_monotonic == 1900.0
    assert from_session.deadline_monotonic != default_timeout.deadline_monotonic
    assert turn_deadline_seconds(60) >= 60 * 10


def test_expired_deadline_does_not_start_nested_run(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    provider = _JudgeProvider(["SHOULD NOT RUN"])
    budget = SkillBudget(
        llm_calls_left=60,
        nested_runs_left=20,
        deadline_monotonic=time.monotonic() - 1,
    )
    tools = build_session_skill_tools(
        db,
        sid,
        workspace_dir="/tmp",
        base_tools=ToolRegistry(),
        provider=provider,
        budget=budget,
    )
    _, fn = tools.get(name)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is False
    assert out["error"] == "deadline exceeded"
    assert provider.requests == []
    assert budget.nested_runs_left == 20
    assert budget.llm_calls_left == 60
    assert budget.deadline_hit is True
    run = get_run(db, out["run_id"])
    assert run is not None
    entries = json.loads(run["trace_json"] or "[]")
    nodes = [e for e in entries if e["kind"] == "deadline"]
    assert nodes
    assert nodes[0]["data"]["error"] == "deadline exceeded"


def test_budget_exhausted_when_deadline_still_open(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    budget = SkillBudget(
        llm_calls_left=60,
        nested_runs_left=0,
        deadline_monotonic=time.monotonic() + 900,
    )
    tools = build_session_skill_tools(
        db, sid, workspace_dir="/tmp", base_tools=ToolRegistry(), budget=budget
    )
    _, fn = tools.get(name)
    assert fn is not None
    out = asyncio.run(fn(text="hello"))
    assert out["ok"] is False
    assert out["error"] == "budget exhausted"
    assert budget.deadline_hit is False


def test_nested_runner_stops_between_iterations_on_deadline(
    db: Database, client
) -> None:
    workspace = Path(client.app.state.workspace_manager.root)
    doc_id = ingest_file(db, workspace, filename="in.md", content=b"hello").id
    skill_id = _agent_skill(db)
    record = get_skill(db, skill_id)
    assert record is not None
    budget = SkillBudget(
        llm_calls_left=60,
        nested_runs_left=20,
        deadline_monotonic=time.monotonic() + 1000,
    )
    hold = budget.reserve(*estimate_skill_budget(record.config))
    assert hold is not None

    class _ExpireAfterFirst(_JudgeProvider):
        def __init__(self) -> None:
            super().__init__([])
            self.step = 0

        async def complete(self, model, messages, tools=None, temperature=0.0, **kwargs):
            self.requests.append({"model": model})
            self.step += 1
            budget.deadline_monotonic = time.monotonic() - 1
            return CompletionResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="read_document",
                        arguments={"doc_id": doc_id},
                    )
                ],
                finish_reason="tool_calls",
            )

    provider = _ExpireAfterFirst()

    def _run() -> None:
        with nested_skill_hold(hold, budget):
            asyncio.run(
                apply_skill_collect(
                    provider=provider,
                    db=db,
                    workspace_dir=str(workspace),
                    skill=record.config,
                    skill_id=skill_id,
                    input_doc_ids=[doc_id],
                    base_tools=build_document_tools(db, workspace),
                    persist=False,
                )
            )

    try:
        _run()
    finally:
        budget.release(hold)
    assert provider.step == 1
    assert hold.llm_used == 1
    assert budget.deadline_hit is True


def test_ws_deadline_uses_session_llm_timeout(
    client, provider, db, monkeypatch
) -> None:
    captured: list[int] = []
    real = make_turn_budget

    def _spy(
        *,
        llm_calls_left: int,
        nested_runs_left: int,
        llm_timeout_seconds: int,
        now: float | None = None,
    ) -> SkillBudget:
        captured.append(llm_timeout_seconds)
        return real(
            llm_calls_left=llm_calls_left,
            nested_runs_left=nested_runs_left,
            llm_timeout_seconds=llm_timeout_seconds,
            now=now,
        )

    monkeypatch.setattr("catalog.api.sessions.make_turn_budget", _spy)
    sid = client.post("/sessions").json()["id"]
    patched = client.patch(f"/sessions/{sid}", json={"llm_timeout_seconds": 90})
    assert patched.status_code == 200
    assert patched.json()["llm_timeout_seconds"] == 90
    provider.script = [
        CompletionResult(content="ok", tool_calls=[], finish_reason="stop"),
    ]
    with client.websocket_connect(f"/sessions/{sid}") as ws:
        first = ws.receive_json()
        assert first.get("type") == "suggestions"
        ws.send_text("hi")
        while True:
            frame = ws.receive_json()
            if frame.get("type") == "finish":
                break
    assert captured == [90]


def test_ws_deadline_exceeded_does_not_fail_turn(
    client, provider, db, monkeypatch
) -> None:
    def _expired(
        *,
        llm_calls_left: int,
        nested_runs_left: int,
        llm_timeout_seconds: int,
        now: float | None = None,
    ) -> SkillBudget:
        return SkillBudget(
            llm_calls_left=llm_calls_left,
            nested_runs_left=nested_runs_left,
            deadline_monotonic=time.monotonic() - 1,
        )

    monkeypatch.setattr("catalog.api.sessions.make_turn_budget", _expired)
    sid = client.post("/sessions").json()["id"]
    skill_id = _script_skill(db)
    client.post(f"/sessions/{sid}/tools", json={"skill_ids": [skill_id]})
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())
    provider.script = [
        CompletionResult(
            content=None,
            tool_calls=[ToolCall(id="t1", name=name, arguments={"text": "one"})],
            finish_reason="tool_calls",
        ),
        CompletionResult(content="продолжаю", tool_calls=[], finish_reason="stop"),
    ]
    with client.websocket_connect(f"/sessions/{sid}") as ws:
        first = ws.receive_json()
        assert first.get("type") == "suggestions"
        ws.send_text("вызови скилл")
        frames: list[dict] = []
        while True:
            frame = ws.receive_json()
            frames.append(frame)
            if frame.get("type") == "finish":
                break
    results = [f for f in frames if f.get("type") == "tool_result"]
    assert len(results) == 1
    payload = json.loads(results[0]["result"])
    assert payload["ok"] is False
    assert payload["error"] == "deadline exceeded"
    assert frames[-1]["status"] == "ok"
