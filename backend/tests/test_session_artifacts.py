from __future__ import annotations

import asyncio
import json

import pytest

from app.llm.base import CompletionResult, ToolCall
from app.skills.artifact_tools import build_artifact_tools
from app.skills.config import SkillConfig, VerifyCheck
from app.skills.repo_skill import create_skill, get_skill
from app.storage.db import Database
from app.storage.repo_message import list_messages
from app.storage.repo_session import create_session
from app.storage.repo_session_artifact import (
    delete_artifact,
    get_artifact,
    list_artifacts,
    upsert_artifact,
)


@pytest.fixture()
def mem_db() -> Database:
    d = Database(":memory:")
    d.init_schema()
    return d


def test_upsert_get_list_delete_artifact(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    row = upsert_artifact(
        mem_db,
        session_id=session_id,
        type="prompt",
        content="first",
        source="llm",
    )
    assert row.content == "first"
    assert row.is_valid is True
    assert get_artifact(mem_db, session_id, "prompt") is not None

    upsert_artifact(
        mem_db,
        session_id=session_id,
        type="prompt",
        content="second",
        source="user",
    )
    got = get_artifact(mem_db, session_id, "prompt")
    assert got is not None
    assert got.content == "second"
    assert got.source == "user"
    assert len(list_artifacts(mem_db, session_id)) == 1

    assert delete_artifact(mem_db, session_id, "prompt") is True
    assert get_artifact(mem_db, session_id, "prompt") is None
    assert delete_artifact(mem_db, session_id, "prompt") is False


def test_save_skill_script_marks_invalid(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_script = tools.get("save_skill_script")

    async def _run():
        return await save_script(code="import os\nresult = 'x'")

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["error"]
    row = get_artifact(mem_db, session_id, "script")
    assert row is not None
    assert row.is_valid is False
    assert row.error


def test_save_skill_script_valid(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_script = tools.get("save_skill_script")
    code = "def main(document):\n    return document.upper()\n"

    async def _run():
        return await save_script(code=code)

    result = asyncio.run(_run())
    assert result["ok"] is True
    row = get_artifact(mem_db, session_id, "script")
    assert row is not None
    assert row.is_valid is True
    assert row.content == code


def test_patch_artifacts_meta_rejects_empty_name(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    resp = client.patch(
        f"/sessions/{session_id}/artifacts/meta",
        json={
            "content": json.dumps(
                {
                    "name": "   ",
                    "description": "x",
                    "kind": "agent",
                    "allowed_tools": ["read_document"],
                },
                ensure_ascii=False,
            )
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is False
    assert "name" in (resp.json()["error"] or "").lower()


def test_patch_artifacts_meta_rejects_missing_name(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    resp = client.patch(
        f"/sessions/{session_id}/artifacts/meta",
        json={
            "content": json.dumps(
                {
                    "description": "x",
                    "kind": "agent",
                    "allowed_tools": ["read_document"],
                },
                ensure_ascii=False,
            )
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is False
    assert "name" in (resp.json()["error"] or "").lower()
    build = client.post(f"/sessions/{session_id}/skills")
    assert build.status_code == 422


def test_build_from_artifacts_without_llm(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "FromArtifacts",
            "description": "packed without LLM",
            "kind": "agent",
            "allowed_tools": ["read_document"],
            "verify_checks": [{"check": "non_empty"}],
        },
    )
    client.patch(
        f"/sessions/{session_id}/artifacts/prompt",
        json={"content": "Summarize the document."},
    )
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["name"] == "FromArtifacts"
    assert provider.requests == []
    skill = get_skill(db, resp.json()["skill_id"])
    assert skill is not None
    assert skill.config.system_prompt == "Summarize the document."


def test_build_script_from_artifacts(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    code = "def main(document):\n    return document.upper()\n"
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "Upper",
            "description": "upper",
            "kind": "script",
        },
    )
    patch = client.patch(
        f"/sessions/{session_id}/artifacts/script",
        json={"content": code},
    )
    assert patch.status_code == 200
    assert patch.json()["is_valid"] is True
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text
    skill = get_skill(db, resp.json()["skill_id"])
    assert skill is not None
    assert skill.config.kind == "script"
    assert skill.config.code == code
    assert provider.requests == []


def test_build_invalid_script_returns_422(client, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={"name": "Bad", "description": "bad", "kind": "script"},
    )
    patch = client.patch(
        f"/sessions/{session_id}/artifacts/script",
        json={"content": "import os\nresult = 'x'"},
    )
    assert patch.json()["is_valid"] is False
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422
    assert "script" in resp.json()["detail"].lower()


def test_build_missing_prompt_returns_422(client, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "NoPrompt",
            "description": "x",
            "kind": "agent",
            "allowed_tools": ["read_document"],
        },
    )
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422
    assert "prompt" in resp.json()["detail"].lower()


def test_build_fallback_llm_when_no_artifacts(client, provider, db) -> None:
    from app.llm.base import CompletionResult, ToolCall

    session_id = client.post("/sessions").json()["id"]
    assert list_artifacts(db, session_id) == []
    provider.script = [
        CompletionResult(
            content=None,
            tool_calls=[
                ToolCall(
                    id="build-1",
                    name="build_skill",
                    arguments={
                        "name": "Legacy",
                        "description": "from chat",
                        "system_prompt": "Do it.",
                        "allowed_tools": ["read_document"],
                        "verify_checks": [{"check": "non_empty"}],
                    },
                )
            ],
            finish_reason="stop",
        )
    ]
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["name"] == "Legacy"
    assert provider.requests


def test_edit_seeds_artifacts(client, db) -> None:
    config = SkillConfig(
        name="Original",
        description="test skill",
        system_prompt="You summarize.",
        allowed_tools=["read_document"],
        model="test/model",
        verify_checks=[VerifyCheck(check="non_empty")],
    )
    skill_id = create_skill(
        db,
        name=config.name,
        description=config.description,
        config=config,
        status="committed",
    )
    resp = client.post(f"/skills/{skill_id}/edit")
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]
    arts = {a["type"]: a for a in client.get(f"/sessions/{session_id}/artifacts").json()}
    assert "meta" in arts
    assert "prompt" in arts
    meta = json.loads(arts["meta"]["content"])
    assert meta["name"] == "Original"
    assert arts["prompt"]["content"] == "You summarize."

    seed = list_messages(db, session_id)[0]["content"]
    assert "You summarize." not in seed
    assert "build_skill" not in seed
    assert "set_skill_meta" in seed
    assert "save_skill_prompt" in seed


def test_ws_save_skill_prompt_emits_session_artifacts(client, provider) -> None:
    session_id = client.post("/sessions").json()["id"]
    prompt_text = "Draft prompt from planner tool."
    provider.script = [
        CompletionResult(
            content=None,
            tool_calls=[
                ToolCall(
                    id="save-1",
                    name="save_skill_prompt",
                    arguments={"content": prompt_text},
                )
            ],
            finish_reason="stop",
        ),
        CompletionResult(
            content="Обновил черновик prompt.",
            tool_calls=[],
            finish_reason="stop",
        ),
    ]
    with client.websocket_connect(f"/sessions/{session_id}") as ws:
        assert ws.receive_json()["type"] == "suggestions"
        ws.send_text("сохрани prompt")
        frames: list[dict] = []
        while True:
            frame = ws.receive_json()
            frames.append(frame)
            if frame.get("type") == "finish":
                break

    art_frames = [f for f in frames if f.get("type") == "session_artifacts"]
    assert art_frames, f"expected session_artifacts in { [f.get('type') for f in frames] }"
    prompts = [
        a
        for a in art_frames[-1]["artifacts"]
        if a.get("type") == "prompt"
    ]
    assert prompts
    assert prompts[0]["content"] == prompt_text
    assert prompts[0]["source"] == "llm"


def test_build_from_edit_session_via_artifacts(client, provider, db) -> None:
    config = SkillConfig(
        name="Original",
        description="test skill",
        system_prompt="You summarize.",
        allowed_tools=["read_document"],
        model="test/model",
    )
    skill_id = create_skill(
        db,
        name=config.name,
        description=config.description,
        config=config,
        status="committed",
    )
    session_id = client.post(f"/skills/{skill_id}/edit").json()["session_id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "Renamed",
            "description": "updated",
            "kind": "agent",
            "allowed_tools": ["read_document"],
        },
    )
    client.patch(
        f"/sessions/{session_id}/artifacts/prompt",
        json={"content": "Updated prompt."},
    )
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text
    assert resp.json()["skill_id"] == skill_id
    skill = get_skill(db, skill_id)
    assert skill is not None
    assert skill.name == "Renamed"
    assert skill.status == "draft"
    assert skill.config.system_prompt == "Updated prompt."
    assert provider.requests == []
