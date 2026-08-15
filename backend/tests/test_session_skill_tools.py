from __future__ import annotations

import asyncio

from catalog.agent.registry import ToolRegistry
from catalog.skills.config import SkillConfig, VerifyCheck
from catalog.skills.repo_skill import create_skill, get_skill
from catalog.skills.skill_tools import build_session_skill_tools, skill_tool_name
from catalog.storage.db import Database
from catalog.storage.repo_session import create_session
from catalog.storage.repo_session_skill import attach_skills, list_session_skills


def _script_skill(db: Database) -> str:
    config = SkillConfig(
        name="Upper Text",
        description="Uppercase input",
        system_prompt="",
        allowed_tools=[],
        model="x",
        kind="script",
        code=("def main(document):\n" "    return document.upper()\n"),
        verify_checks=[VerifyCheck(check="non_empty")],
        input_arity=1,
    )
    return create_skill(
        db,
        name=config.name,
        description=config.description,
        config=config,
        status="committed",
    )


def test_attach_list_session_skills(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    assert attach_skills(db, sid, [skill_id]) == []
    rows = list_session_skills(db, sid)
    assert len(rows) == 1
    assert rows[0].id == skill_id


def test_session_skill_tool_runs_script(db: Database) -> None:
    sid = create_session(db)
    skill_id = _script_skill(db)
    attach_skills(db, sid, [skill_id])
    record = get_skill(db, skill_id)
    assert record is not None
    name = skill_tool_name(record, used=set())

    class _Prov:
        async def complete(self, *a, **k):
            raise AssertionError("LLM must not be called for script tool")

    tools = build_session_skill_tools(
        db,
        sid,
        workspace_dir="/tmp",
        provider=_Prov(),  # type: ignore[arg-type]
        base_tools=ToolRegistry(),
    )
    assert name in tools.names()
    _, fn = tools.get(name)

    async def _run():
        return await fn(text="hello")

    out = asyncio.run(_run())
    assert out["ok"] is True
    assert out["text"] == "HELLO"
    assert out["skill_id"] == skill_id
    assert out["config_hash"]
