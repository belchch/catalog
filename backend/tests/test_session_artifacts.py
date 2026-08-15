from __future__ import annotations

import asyncio
import json

import pytest

from catalog.llm.base import CompletionResult, ToolCall
from catalog.skills.artifact_tools import build_artifact_tools
from catalog.skills.config import SkillConfig, VerifyCheck
from catalog.skills.repo_skill import create_skill, get_skill
from catalog.storage.db import Database
from catalog.storage.repo_message import list_messages
from catalog.storage.repo_session import create_session
from catalog.storage.repo_session_artifact import (
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


def test_set_skill_meta_rejects_min_length_without_min(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, set_meta = tools.get("set_skill_meta")
    check_prop = tools.get("set_skill_meta")[0].parameters["properties"][
        "verify_checks"
    ]["items"]["properties"]["check"]
    assert "enum" in check_prop
    assert "non_empty" in check_prop["enum"]

    async def _run():
        return await set_meta(
            name="BadMin",
            description="x",
            kind="agent",
            allowed_tools=["read_document"],
            verify_checks=[{"check": "min_length"}],
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert "min_length" in (result.get("error") or "")


def test_set_skill_meta_rejects_empty_name(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, set_meta = tools.get("set_skill_meta")

    async def _run():
        return await set_meta(
            name="   ",
            description="x",
            kind="agent",
            allowed_tools=["read_document"],
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert "name" in (result.get("error") or "").lower()
    row = get_artifact(mem_db, session_id, "meta")
    assert row is not None
    assert row.is_valid is False


def test_set_skill_meta_rejects_bad_input_arity(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, set_meta = tools.get("set_skill_meta")

    async def _run():
        return await set_meta(
            name="BadArity",
            description="x",
            kind="agent",
            input_arity=3,
            allowed_tools=["read_document"],
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert "input_arity" in (result.get("error") or "")
    row = get_artifact(mem_db, session_id, "meta")
    assert row is not None
    assert row.is_valid is False


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


def test_patch_artifacts_meta_rejects_missing_description(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    resp = client.patch(
        f"/sessions/{session_id}/artifacts/meta",
        json={
            "content": json.dumps(
                {
                    "name": "NoDesc",
                    "kind": "agent",
                    "allowed_tools": ["read_document"],
                },
                ensure_ascii=False,
            )
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is False
    assert "description" in (resp.json()["error"] or "").lower()
    build = client.post(f"/sessions/{session_id}/skills")
    assert build.status_code == 422


def test_patch_skill_meta_rejects_bad_input_arity(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    resp = client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "BadArity",
            "description": "x",
            "kind": "agent",
            "input_arity": 3,
            "allowed_tools": ["read_document"],
        },
    )
    assert resp.status_code == 422


def test_patch_artifacts_meta_normalizes_string_input_arity(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    resp = client.patch(
        f"/sessions/{session_id}/artifacts/meta",
        json={
            "content": json.dumps(
                {
                    "name": "Arity",
                    "description": "x",
                    "kind": "agent",
                    "input_arity": "1",
                    "allowed_tools": ["read_document"],
                },
                ensure_ascii=False,
            )
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True
    meta = json.loads(resp.json()["content"])
    assert meta["input_arity"] == 1
    assert isinstance(meta["input_arity"], int)


def test_patch_artifacts_meta_rejects_bad_input_arity(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    resp = client.patch(
        f"/sessions/{session_id}/artifacts/meta",
        json={
            "content": json.dumps(
                {
                    "name": "Arity",
                    "description": "x",
                    "kind": "agent",
                    "input_arity": 3,
                    "allowed_tools": ["read_document"],
                },
                ensure_ascii=False,
            )
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is False
    assert "input_arity" in (resp.json()["error"] or "")


def test_patch_artifacts_meta_rejects_non_list_allowed_tools(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    resp = client.patch(
        f"/sessions/{session_id}/artifacts/meta",
        json={
            "content": json.dumps(
                {
                    "name": "BadTools",
                    "description": "x",
                    "kind": "agent",
                    "allowed_tools": 1,
                },
                ensure_ascii=False,
            )
        },
    )
    assert resp.status_code == 422
    assert "allowed_tools" in resp.json()["detail"]


def test_patch_artifacts_meta_rejects_non_list_verify_checks(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    resp = client.patch(
        f"/sessions/{session_id}/artifacts/meta",
        json={
            "content": json.dumps(
                {
                    "name": "BadChecks",
                    "description": "x",
                    "kind": "agent",
                    "allowed_tools": ["read_document"],
                    "verify_checks": {"check": "non_empty"},
                },
                ensure_ascii=False,
            )
        },
    )
    assert resp.status_code == 422
    assert "verify_checks" in resp.json()["detail"]


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
    from catalog.llm.base import CompletionResult, ToolCall

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


def test_set_skill_meta_accepts_pipeline(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, set_meta = tools.get("set_skill_meta")

    async def _run():
        return await set_meta(
            name="Pipe",
            description="linear",
            kind="pipeline",
            allowed_tools=["read_document"],
        )

    result = asyncio.run(_run())
    assert result["ok"] is True
    row = get_artifact(mem_db, session_id, "meta")
    assert row is not None
    payload = json.loads(row.content)
    assert payload["kind"] == "pipeline"
    assert payload["allowed_tools"] == []


def test_save_skill_steps_writes_valid_artifact(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_steps = tools.get("save_skill_steps")
    steps = [
        {
            "id": "upper",
            "type": "script",
            "input": "documents",
            "code": "result = document.upper()\n",
        },
        {
            "id": "note",
            "type": "llm",
            "input": "previous",
            "system_prompt": "rewrite",
            "allowed_tools": ["read_document"],
        },
    ]

    async def _run():
        return await save_steps(steps=steps)

    result = asyncio.run(_run())
    assert result["ok"] is True
    row = get_artifact(mem_db, session_id, "steps")
    assert row is not None
    assert row.is_valid is True
    payload = json.loads(row.content)
    assert [s["id"] for s in payload["steps"]] == ["upper", "note"]


def test_save_skill_steps_allows_empty_content(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_steps = tools.get("save_skill_steps")

    async def _run():
        return await save_steps(
            steps=[
                {"id": "upper", "type": "script", "input": "documents"},
                {
                    "id": "note",
                    "type": "llm",
                    "input": "previous",
                    "allowed_tools": ["read_document"],
                },
            ]
        )

    result = asyncio.run(_run())
    assert result["ok"] is True
    row = get_artifact(mem_db, session_id, "steps")
    assert row is not None
    assert row.is_valid is True


def test_save_skill_steps_rejects_unknown_input(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_steps = tools.get("save_skill_steps")

    async def _run():
        return await save_steps(
            steps=[
                {
                    "id": "upper",
                    "type": "script",
                    "input": "prevous",
                    "code": "result = document.upper()\n",
                }
            ]
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert "unknown input" in (result["error"] or "")
    row = get_artifact(mem_db, session_id, "steps")
    assert row is not None
    assert row.is_valid is False
    payload = json.loads(row.content)
    assert payload["steps"][0]["input"] == "prevous"


def test_save_skill_steps_rejects_bad_script(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_steps = tools.get("save_skill_steps")

    async def _run():
        return await save_steps(
            steps=[
                {
                    "id": "bad",
                    "type": "script",
                    "code": "import os\nresult = 'x'",
                }
            ]
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    row = get_artifact(mem_db, session_id, "steps")
    assert row is not None
    assert row.is_valid is False


def test_build_pipeline_from_artifacts(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "Pipe",
            "description": "from artifacts",
            "kind": "pipeline",
        },
    )
    steps = {
        "steps": [
            {
                "id": "upper",
                "type": "script",
                "input": "documents",
                "code": "result = document.upper()\n",
            },
            {
                "id": "note",
                "type": "llm",
                "input": "previous",
                "system_prompt": "rewrite the text",
                "allowed_tools": ["read_document"],
            },
        ]
    }
    patch = client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["is_valid"] is True
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text
    skill = get_skill(db, resp.json()["skill_id"])
    assert skill is not None
    assert skill.config.kind == "pipeline"
    assert [s.id for s in skill.config.steps] == ["upper", "note"]
    assert skill.config.allowed_tools == []
    assert provider.requests == []


def test_build_pipeline_from_artifacts_despite_track_intent(
    client, provider, db
) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "Pipe",
            "description": "from artifacts after track",
            "kind": "pipeline",
        },
    )
    steps = {
        "steps": [
            {
                "id": "upper",
                "type": "script",
                "input": "documents",
                "code": "result = document.upper()\n",
            },
            {
                "id": "note",
                "type": "llm",
                "input": "previous",
                "system_prompt": "rewrite the text",
                "allowed_tools": ["read_document"],
            },
        ]
    }
    patch = client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    assert patch.status_code == 200, patch.text
    select = client.post(
        f"/sessions/{session_id}/skill-tracks/select",
        json={
            "track": {
                "name": "Pipe",
                "description": "linear",
                "operation": "прогнать шаги pipeline",
                "input_arity": 1,
                "rationale": "черновик уже pipeline",
            }
        },
    )
    assert select.status_code == 200, select.text
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text
    assert provider.requests == []
    skill = get_skill(db, resp.json()["skill_id"])
    assert skill is not None
    assert skill.config.kind == "pipeline"
    assert [s.id for s in skill.config.steps] == ["upper", "note"]


def test_build_invalid_pipeline_meta_with_track_intent_returns_422(
    client, provider, db
) -> None:
    session_id = client.post("/sessions").json()["id"]
    meta = client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "Pipe",
            "description": "invalid pipeline meta",
            "kind": "pipeline",
            "verify_checks": [{"check": "not_a_real_check"}],
        },
    )
    assert meta.status_code == 200, meta.text
    assert meta.json()["is_valid"] is False
    steps = {
        "steps": [
            {
                "id": "upper",
                "type": "script",
                "input": "documents",
                "code": "result = document.upper()\n",
            }
        ]
    }
    patch = client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["is_valid"] is True
    select = client.post(
        f"/sessions/{session_id}/skill-tracks/select",
        json={
            "track": {
                "name": "Pipe",
                "description": "linear",
                "operation": "прогнать шаги pipeline",
                "input_arity": 1,
                "rationale": "черновик уже pipeline",
            }
        },
    )
    assert select.status_code == 200, select.text
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422, resp.text
    assert "meta" in resp.json()["detail"].lower()
    assert provider.requests == []


def test_patch_steps_allows_empty_content(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    steps = {
        "steps": [
            {"id": "upper", "type": "script", "input": "documents"},
            {"id": "note", "type": "llm", "input": "previous"},
        ]
    }
    patch = client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["is_valid"] is True


def test_build_pipeline_from_split_artifacts(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "Pipe",
            "description": "filled from script/prompt artifacts",
            "kind": "pipeline",
        },
    )
    steps = {
        "steps": [
            {"id": "upper", "type": "script", "input": "documents"},
            {
                "id": "note",
                "type": "llm",
                "input": "previous",
                "allowed_tools": ["read_document"],
            },
        ]
    }
    patch = client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["is_valid"] is True
    script = client.patch(
        f"/sessions/{session_id}/artifacts/script",
        json={"content": "result = document.upper()\n"},
    )
    assert script.json()["is_valid"] is True
    prompt = client.patch(
        f"/sessions/{session_id}/artifacts/prompt",
        json={"content": "rewrite the text"},
    )
    assert prompt.json()["is_valid"] is True
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text
    skill = get_skill(db, resp.json()["skill_id"])
    assert skill is not None
    assert skill.config.kind == "pipeline"
    assert [s.id for s in skill.config.steps] == ["upper", "note"]
    assert skill.config.steps[0].code == "result = document.upper()\n"
    assert skill.config.steps[1].system_prompt == "rewrite the text"
    assert provider.requests == []


def test_build_pipeline_rejects_unfilled_empty_steps(client, provider) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "Pipe",
            "description": "empty steps stay empty",
            "kind": "pipeline",
        },
    )
    steps = {
        "steps": [
            {"id": "upper", "type": "script", "input": "documents"},
            {"id": "note", "type": "llm", "input": "previous"},
        ]
    }
    client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422
    detail = resp.json()["detail"].lower()
    assert "invalid" in detail or "empty" in detail
