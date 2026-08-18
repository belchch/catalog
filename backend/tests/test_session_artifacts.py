from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from catalog.documents.ingest import ingest_file
from catalog.documents.tools import build_document_tools
from catalog.llm.base import CompletionResult, ToolCall
from catalog.api.sessions import _planner_system_prompt
from catalog.skills.artifact_tools import build_artifact_tools
from catalog.skills.budget import (
    SCRIPT_TRIES_PER_TURN,
    TURN_DEADLINE_FLOOR_SECONDS,
    SkillBudget,
    _session_script_tries,
    consume_script_try,
)
from catalog.skills.skill_tools import _RESERVED, config_hash
from catalog.skills.verify import registered_checks, verify_checks_params_hint
from catalog.skills.config import PipelineStep, SkillConfig, VerifyCheck
from catalog.skills.repo_skill import create_skill, get_skill, update_skill
from catalog.storage.db import Database
from catalog.storage.repo_document import list_documents
from catalog.storage.repo_message import list_messages
from catalog.storage.repo_session import create_session
from catalog.storage.repo_session_artifact import (
    code_sha256,
    delete_artifact,
    dry_run_slot,
    get_artifact,
    list_artifacts,
    upsert_artifact,
    upsert_script_dry_run,
)
from catalog.storage.repo_session_document import attach_documents
from catalog.storage.repo_session_skill import attach_skills


@pytest.fixture()
def mem_db() -> Database:
    d = Database(":memory:")
    d.init_schema()
    return d


def _seed_green_dry_run(
    db: Database,
    session_id: str,
    code: str,
    *,
    step_index: int | None = None,
) -> None:
    upsert_script_dry_run(
        db,
        session_id=session_id,
        slot=dry_run_slot(step_index),
        sha256=code_sha256(code),
        ok=True,
        stage="run",
    )


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
    _seed_green_dry_run(db, session_id, code)
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


def test_set_skill_meta_rejects_min_length_without_min(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    spec, set_meta = tools.get("set_skill_meta")
    check_schema = spec.parameters["properties"]["verify_checks"]["items"][
        "properties"
    ]["check"]
    assert check_schema.get("enum") == registered_checks()
    assert verify_checks_params_hint() in spec.description

    async def _run():
        return await set_meta(
            name="Len",
            description="x",
            kind="agent",
            allowed_tools=["read_document"],
            verify_checks=[{"check": "min_length"}],
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert "min" in (result.get("error") or "")
    row = get_artifact(mem_db, session_id, "meta")
    assert row is not None
    assert row.is_valid is False


def test_set_skill_meta_accepts_min_length_with_min(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, set_meta = tools.get("set_skill_meta")

    async def _run():
        return await set_meta(
            name="Len",
            description="x",
            kind="agent",
            allowed_tools=["read_document"],
            verify_checks=[{"check": "min_length", "params": {"min": 20}}],
        )

    result = asyncio.run(_run())
    assert result["ok"] is True
    row = get_artifact(mem_db, session_id, "meta")
    assert row is not None
    assert row.is_valid is True


def test_set_skill_meta_rejects_unknown_verify_check(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, set_meta = tools.get("set_skill_meta")

    async def _run():
        return await set_meta(
            name="Len",
            description="x",
            kind="agent",
            allowed_tools=["read_document"],
            verify_checks=[{"check": "not_a_real_check"}],
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert "unknown verify check" in (result.get("error") or "")


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
    _seed_green_dry_run(
        db, session_id, "result = document.upper()\n", step_index=0
    )
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
    _seed_green_dry_run(
        db, session_id, "result = document.upper()\n", step_index=0
    )
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
    _seed_green_dry_run(
        db, session_id, "result = document.upper()\n", step_index=0
    )
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


def _committed_script(db: Database, *, name: str = "Upper", code: str | None = None) -> str:
    source = code if code is not None else "result = document.upper()\n"
    config = SkillConfig(
        name=name,
        description="upper",
        system_prompt="",
        allowed_tools=[],
        model="m",
        kind="script",
        code=source,
    )
    return create_skill(
        db,
        name=config.name,
        description=config.description,
        config=config,
        status="committed",
    )


def test_save_skill_steps_accepts_skill_id(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    skill_id = _committed_script(mem_db)
    attach_skills(mem_db, session_id, [skill_id])
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_steps = tools.get("save_skill_steps")

    async def _run():
        return await save_steps(
            steps=[
                {
                    "id": "call",
                    "type": "skill",
                    "input": "documents",
                    "skill_id": skill_id,
                }
            ]
        )

    result = asyncio.run(_run())
    assert result["ok"] is True
    row = get_artifact(mem_db, session_id, "steps")
    assert row is not None
    payload = json.loads(row.content)
    assert payload["steps"][0]["type"] == "skill"
    assert payload["steps"][0]["skill_id"] == skill_id
    assert "config" not in payload["steps"][0]


def test_save_skill_steps_rejects_empty_skill_id(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_steps = tools.get("save_skill_steps")

    async def _run():
        return await save_steps(
            steps=[{"id": "call", "type": "skill", "input": "documents"}]
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert "skill_id is empty" in (result["error"] or "")


def test_save_skill_steps_rejects_unattached_skill_id(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    skill_id = _committed_script(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_steps = tools.get("save_skill_steps")

    async def _run():
        return await save_steps(
            steps=[
                {
                    "id": "call",
                    "type": "skill",
                    "input": "documents",
                    "skill_id": skill_id,
                }
            ]
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert "not attached" in (result["error"] or "")


def test_list_session_skills_tool(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    skill_id = _committed_script(mem_db, name="Ready")
    attach_skills(mem_db, session_id, [skill_id])
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    spec, list_fn = tools.get("list_session_skills")
    assert spec is not None
    assert spec.name == "list_session_skills"

    async def _run():
        return await list_fn()

    result = asyncio.run(_run())
    assert result["skills"][0]["id"] == skill_id
    assert result["skills"][0]["name"] == "Ready"
    assert result["skills"][0]["kind"] == "script"


def test_planner_prompt_lists_attached_skill_ids(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    skill_id = _committed_script(mem_db, name="Ready")
    attach_skills(mem_db, session_id, [skill_id])
    prompt = _planner_system_prompt(mem_db, session_id)
    assert skill_id in prompt
    assert "Ready" in prompt
    assert "type=skill" in prompt


def test_build_pipeline_skill_step_snapshots_and_isolates(
    client, provider, db
) -> None:
    session_id = client.post("/sessions").json()["id"]
    child_id = _committed_script(db, name="Child", code="result = document.upper()\n")
    child = get_skill(db, child_id)
    assert child is not None
    pinned = config_hash(child.config.to_json())
    attach = client.post(
        f"/sessions/{session_id}/tools", json={"skill_ids": [child_id]}
    )
    assert attach.status_code == 200, attach.text
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "Parent",
            "description": "calls child",
            "kind": "pipeline",
        },
    )
    steps = {
        "steps": [
            {
                "id": "call",
                "type": "skill",
                "input": "documents",
                "skill_id": child_id,
            }
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
    parent = get_skill(db, resp.json()["skill_id"])
    assert parent is not None
    step = parent.config.steps[0]
    assert step.type == "skill"
    assert step.skill_id == child_id
    assert step.skill_name == "Child"
    assert step.config_hash == pinned
    assert step.config is not None
    assert step.config.code == "result = document.upper()\n"
    parent_json = parent.config.to_json()

    updated = SkillConfig(
        name="Child",
        description="upper",
        system_prompt="",
        allowed_tools=[],
        model="m",
        kind="script",
        code="result = document.lower()\n",
    )
    update_skill(
        db,
        child_id,
        name=updated.name,
        description=updated.description,
        config=updated,
    )
    after = get_skill(db, parent.id)
    assert after is not None
    assert after.config.to_json() == parent_json
    assert after.config.steps[0].config is not None
    assert after.config.steps[0].config.code == "result = document.upper()\n"
    assert after.config.steps[0].config_hash != config_hash(updated.to_json())


def test_build_pipeline_skill_step_rejects_missing_id(client, provider) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={"name": "Parent", "description": "x", "kind": "pipeline"},
    )
    steps = {
        "steps": [
            {
                "id": "call",
                "type": "skill",
                "input": "documents",
                "skill_id": "missing-skill",
            }
        ]
    }
    client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422
    assert "not found" in resp.json()["detail"]


def test_build_pipeline_skill_step_rejects_unattached(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    child_id = _committed_script(db)
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={"name": "Parent", "description": "x", "kind": "pipeline"},
    )
    steps = {
        "steps": [
            {
                "id": "call",
                "type": "skill",
                "input": "documents",
                "skill_id": child_id,
            }
        ]
    }
    client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422
    assert "not attached" in resp.json()["detail"]


def test_build_pipeline_skill_step_rejects_draft(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    draft_config = SkillConfig(
        name="Draft",
        description="d",
        system_prompt="",
        allowed_tools=[],
        model="m",
        kind="script",
        code="result = document\n",
    )
    draft_id = create_skill(
        db,
        name=draft_config.name,
        description=draft_config.description,
        config=draft_config,
        status="draft",
    )
    attach_skills(db, session_id, [draft_id])
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={"name": "Parent", "description": "x", "kind": "pipeline"},
    )
    steps = {
        "steps": [
            {
                "id": "call",
                "type": "skill",
                "input": "documents",
                "skill_id": draft_id,
            }
        ]
    }
    client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422
    assert "not committed" in resp.json()["detail"]


def _pipeline_calling_child(db: Database, child_id: str) -> str:
    child = get_skill(db, child_id)
    assert child is not None
    parent = SkillConfig(
        name="Parent",
        description="calls child",
        system_prompt="",
        allowed_tools=[],
        model="m",
        kind="pipeline",
        steps=[
            PipelineStep(
                id="call",
                type="skill",
                input="documents",
                skill_id=child.id,
                skill_name=child.name,
                config_hash=config_hash(child.config.to_json()),
                config=child.config,
            )
        ],
    )
    return create_skill(
        db,
        name=parent.name,
        description=parent.description,
        config=parent,
        status="committed",
    )


def test_edit_pipeline_attaches_skill_ids_and_rebuilds(client, provider, db) -> None:
    child_id = _committed_script(db, name="Child")
    parent_id = _pipeline_calling_child(db, child_id)
    edit = client.post(f"/skills/{parent_id}/edit")
    assert edit.status_code == 200, edit.text
    session_id = edit.json()["session_id"]
    attached = client.get(f"/sessions/{session_id}/tools")
    assert attached.status_code == 200
    assert [s["id"] for s in attached.json()] == [child_id]
    provider.script = []
    first = client.post(f"/sessions/{session_id}/skills")
    assert first.status_code == 200, first.text
    assert first.json()["skill_id"] == parent_id

    tools = build_artifact_tools(db, session_id, available_tools=["read_document"])
    _, save_steps = tools.get("save_skill_steps")

    async def _run():
        return await save_steps(
            steps=[
                {
                    "id": "call",
                    "type": "skill",
                    "input": "documents",
                    "skill_id": child_id,
                }
            ]
        )

    saved = asyncio.run(_run())
    assert saved["ok"] is True
    provider.script = []
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 200, resp.text
    assert resp.json()["skill_id"] == parent_id
    parent = get_skill(db, parent_id)
    assert parent is not None
    step = parent.config.steps[0]
    assert step.type == "skill"
    assert step.skill_id == child_id
    assert step.config is not None
    assert step.config.code == "result = document.upper()\n"


def test_save_skill_steps_accepts_snapshotted_skill_without_attach(
    mem_db: Database,
) -> None:
    session_id = create_session(mem_db)
    nested = SkillConfig(
        name="Inner",
        description="d",
        system_prompt="",
        allowed_tools=[],
        model="m",
        kind="script",
        code="result = document.upper()\n",
    )
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_steps = tools.get("save_skill_steps")

    async def _run():
        return await save_steps(
            steps=[
                {
                    "id": "call",
                    "type": "skill",
                    "input": "documents",
                    "skill_id": "gone-child",
                    "config": json.loads(nested.to_json()),
                }
            ]
        )

    result = asyncio.run(_run())
    assert result["ok"] is True
    row = get_artifact(mem_db, session_id, "steps")
    assert row is not None
    payload = json.loads(row.content)
    assert payload["steps"][0]["skill_id"] == "gone-child"
    assert payload["steps"][0]["config"]["name"] == "Inner"


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


def _count_rows(db: Database, table: str) -> int:
    with db.connect() as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
        return int(row[0])


def _artifact_try_tools(
    db: Database,
    session_id: str,
    *,
    workspace: str = "",
    budget: SkillBudget | None = None,
):
    return build_artifact_tools(
        db,
        session_id,
        available_tools=["read_document"],
        workspace_dir=workspace,
        budget=budget,
    )


def test_try_skill_script_is_planner_only(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = _artifact_try_tools(mem_db, session_id)
    assert "try_skill_script" in tools.names()
    assert "try_skill_script" in _RESERVED
    spec, _fn = tools.get("try_skill_script")
    assert spec is not None
    assert spec.name == "try_skill_script"
    apply_tools = build_document_tools(mem_db, "/tmp", session_id)
    assert "try_skill_script" not in apply_tools.names()


def test_try_skill_script_ok_on_attached_document(
    mem_db: Database, tmp_path: Path
) -> None:
    session_id = create_session(mem_db)
    doc = ingest_file(mem_db, tmp_path, filename="note.md", content=b"hello world")
    attach_documents(mem_db, session_id, [doc.id])
    tools = _artifact_try_tools(mem_db, session_id, workspace=str(tmp_path))
    _, try_fn = tools.get("try_skill_script")

    async def _run():
        return await try_fn(code="result = document.upper()\n")

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert result["stage"] in ("run", "verify")
    assert result["output_preview"]
    assert "HELLO WORLD" in result["output_preview"]
    assert result["output_kind"] == "str"
    assert result["input_len"] > 0
    assert result["output_len"] > 0


def test_try_skill_script_run_error_includes_line(
    mem_db: Database, tmp_path: Path
) -> None:
    session_id = create_session(mem_db)
    doc = ingest_file(mem_db, tmp_path, filename="note.md", content=b"hello")
    attach_documents(mem_db, session_id, [doc.id])
    tools = _artifact_try_tools(mem_db, session_id, workspace=str(tmp_path))
    _, try_fn = tools.get("try_skill_script")
    code = "def main():\n    items = []\n    return items[0]\n"

    async def _run():
        return await try_fn(code=code)

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["stage"] == "run"
    assert result["line_no"] == 3
    assert result["source_line"] is not None
    assert "items[0]" in result["source_line"]
    assert "3" in (result["error"] or "")


def test_try_skill_script_forbidden_import_is_validate(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = _artifact_try_tools(mem_db, session_id)
    _, try_fn = tools.get("try_skill_script")

    async def _run():
        return await try_fn(code="import os\nresult = 'x'\n")

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["stage"] == "validate"
    assert "import" in (result["error"] or "").lower()
    assert result["output_preview"] == ""
    assert result["duration_ms"] == 0


def test_try_skill_script_timeout(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    tools = _artifact_try_tools(mem_db, session_id)
    _, try_fn = tools.get("try_skill_script")

    async def _run():
        return await try_fn(code="while True:\n    pass\n")

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["stage"] == "run"
    assert "time limit" in (result["error"] or "")


def test_try_skill_script_rejects_foreign_doc_id(
    mem_db: Database, tmp_path: Path
) -> None:
    session_id = create_session(mem_db)
    other_session = create_session(mem_db)
    attached = ingest_file(mem_db, tmp_path, filename="in.md", content=b"in")
    foreign = ingest_file(mem_db, tmp_path, filename="out.md", content=b"out")
    attach_documents(mem_db, session_id, [attached.id])
    attach_documents(mem_db, other_session, [foreign.id])
    tools = _artifact_try_tools(mem_db, session_id, workspace=str(tmp_path))
    _, try_fn = tools.get("try_skill_script")

    async def _run():
        return await try_fn(
            code="result = document.upper()\n",
            doc_ids=[foreign.id],
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["error"] == "document_not_available_in_session"


def test_try_skill_script_does_not_persist(
    mem_db: Database, tmp_path: Path
) -> None:
    session_id = create_session(mem_db)
    doc = ingest_file(mem_db, tmp_path, filename="note.md", content=b"hello")
    attach_documents(mem_db, session_id, [doc.id])
    docs_before = _count_rows(mem_db, "document")
    runs_before = _count_rows(mem_db, "skill_run")
    tools = _artifact_try_tools(mem_db, session_id, workspace=str(tmp_path))
    _, try_fn = tools.get("try_skill_script")

    async def _run():
        return await try_fn(code="result = document.upper()\n")

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert _count_rows(mem_db, "document") == docs_before
    assert _count_rows(mem_db, "skill_run") == runs_before
    assert len(list_documents(mem_db)) == docs_before


def test_try_skill_script_turn_limit_is_ok_false(mem_db: Database) -> None:
    session_id = create_session(mem_db)
    budget = SkillBudget(llm_calls_left=60, nested_runs_left=20, script_tries_left=0)
    tools = _artifact_try_tools(mem_db, session_id, budget=budget)
    _, try_fn = tools.get("try_skill_script")

    async def _run():
        return await try_fn(code="result = 'x'\n")

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert "limit" in (result["error"] or "").lower()
    assert result["stage"] is None


def test_try_skill_script_http_ok_and_same_payload(
    client, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_run(code, doc_texts, params=None, **kwargs):
        return (doc_texts[0] if doc_texts else "").upper()

    monkeypatch.setattr(
        "catalog.skills.artifact_tools.run_skill_script_async",
        _fake_run,
    )
    session_id = client.post("/sessions").json()["id"]
    uploaded = client.post(
        "/documents",
        files={"file": ("note.md", b"hello world", "text/markdown")},
    )
    assert uploaded.status_code == 200
    doc_id = uploaded.json()["id"]
    attach_documents(db, session_id, [doc_id])
    resp = client.post(
        f"/sessions/{session_id}/artifacts/script/try",
        json={"code": "result = document.upper()\n"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "HELLO WORLD" in body["output_preview"]
    assert set(body) >= {
        "ok",
        "stage",
        "error",
        "input_preview",
        "input_len",
        "output_preview",
        "output_len",
        "output_kind",
        "duration_ms",
        "verify",
    }
    assert _count_rows(db, "skill_run") == 0
    docs_after = _count_rows(db, "document")
    resp2 = client.post(
        f"/sessions/{session_id}/artifacts/script/try",
        json={"code": "result = document.upper()\n"},
    )
    assert resp2.status_code == 200
    assert _count_rows(db, "skill_run") == 0
    assert _count_rows(db, "document") == docs_after


def test_try_skill_script_http_validate_and_foreign_doc(client, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    other = client.post("/sessions").json()["id"]
    uploaded = client.post(
        "/documents",
        files={"file": ("note.md", b"hello", "text/markdown")},
    )
    doc_id = uploaded.json()["id"]
    attach_documents(db, other, [doc_id])
    forbidden = client.post(
        f"/sessions/{session_id}/artifacts/script/try",
        json={"code": "import os\nresult = 'x'\n"},
    )
    assert forbidden.status_code == 200
    assert forbidden.json()["ok"] is False
    assert forbidden.json()["stage"] == "validate"
    foreign = client.post(
        f"/sessions/{session_id}/artifacts/script/try",
        json={"code": "result = document.upper()\n", "doc_ids": [doc_id]},
    )
    assert foreign.status_code == 200
    assert foreign.json()["ok"] is False
    assert foreign.json()["error"] == "document_not_available_in_session"


def test_try_skill_script_http_limit_is_not_500(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    _session_script_tries[session_id] = (0, time.monotonic())
    resp = client.post(
        f"/sessions/{session_id}/artifacts/script/try",
        json={"code": "result = 'ok'\n"},
    )
    assert resp.status_code == 200
    assert resp.status_code != 500
    assert resp.json()["ok"] is False
    assert "limit" in (resp.json()["error"] or "").lower()


def test_session_script_tries_reset_after_turn_window() -> None:
    session_id = "window-reset"
    _session_script_tries.pop(session_id, None)
    start = 1_000.0
    for _ in range(SCRIPT_TRIES_PER_TURN):
        assert consume_script_try(session_id=session_id, now=start) is True
    assert consume_script_try(session_id=session_id, now=start + 1) is False
    assert (
        consume_script_try(
            session_id=session_id,
            now=start + TURN_DEADLINE_FLOOR_SECONDS,
        )
        is True
    )
    _session_script_tries.pop(session_id, None)


def test_build_script_without_dry_run_returns_422(client) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={"name": "Upper", "description": "upper", "kind": "script"},
    )
    client.patch(
        f"/sessions/{session_id}/artifacts/script",
        json={"content": "result = document.upper()\n"},
    )
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422
    detail = resp.json()["detail"].lower()
    assert "dry-run" in detail
    assert "try_skill_script" in detail


def test_build_script_after_code_change_requires_new_dry_run(client, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    first = "result = document.upper()\n"
    second = "result = document.lower()\n"
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={"name": "Case", "description": "case", "kind": "script"},
    )
    client.patch(
        f"/sessions/{session_id}/artifacts/script",
        json={"content": first},
    )
    _seed_green_dry_run(db, session_id, first)
    ok = client.post(f"/sessions/{session_id}/skills")
    assert ok.status_code == 200, ok.text
    client.patch(
        f"/sessions/{session_id}/artifacts/script",
        json={"content": second},
    )
    stale = client.post(f"/sessions/{session_id}/skills")
    assert stale.status_code == 422
    assert "dry-run" in stale.json()["detail"].lower()
    _seed_green_dry_run(db, session_id, second)
    again = client.post(f"/sessions/{session_id}/skills")
    assert again.status_code == 200, again.text
    skill = get_skill(db, again.json()["skill_id"])
    assert skill is not None
    assert skill.config.code == second


def test_build_script_ignores_green_dry_run_from_other_slot(client, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    code = "result = document.upper()\n"
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={"name": "Upper", "description": "upper", "kind": "script"},
    )
    client.patch(
        f"/sessions/{session_id}/artifacts/script",
        json={"content": code},
    )
    _seed_green_dry_run(db, session_id, code, step_index=0)
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422
    assert "dry-run" in resp.json()["detail"].lower()
    _seed_green_dry_run(db, session_id, code)
    ok = client.post(f"/sessions/{session_id}/skills")
    assert ok.status_code == 200, ok.text


def test_build_pipeline_two_script_steps_requires_each_dry_run(client, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={"name": "Two", "description": "two scripts", "kind": "pipeline"},
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
                "id": "lower",
                "type": "script",
                "input": "previous",
                "code": "result = document.lower()\n",
            },
        ]
    }
    client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    _seed_green_dry_run(
        db, session_id, "result = document.upper()\n", step_index=0
    )
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "lower" in detail
    assert "step_index=1" in detail
    _seed_green_dry_run(
        db, session_id, "result = document.lower()\n", step_index=1
    )
    ok = client.post(f"/sessions/{session_id}/skills")
    assert ok.status_code == 200, ok.text


def test_build_pipeline_same_code_steps_require_own_slot(client, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    code = "result = document.upper()\n"
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={"name": "Dup", "description": "same scripts", "kind": "pipeline"},
    )
    steps = {
        "steps": [
            {
                "id": "first",
                "type": "script",
                "input": "documents",
                "code": code,
            },
            {
                "id": "second",
                "type": "script",
                "input": "previous",
                "code": code,
            },
        ]
    }
    client.patch(
        f"/sessions/{session_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    _seed_green_dry_run(db, session_id, code, step_index=0)
    resp = client.post(f"/sessions/{session_id}/skills")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "second" in detail
    assert "step_index=1" in detail
    _seed_green_dry_run(db, session_id, code, step_index=1)
    ok = client.post(f"/sessions/{session_id}/skills")
    assert ok.status_code == 200, ok.text


def test_build_agent_and_skill_pipeline_skip_dry_run_gate(client, provider, db) -> None:
    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/skill-meta",
        json={
            "name": "Agent",
            "description": "no script",
            "kind": "agent",
            "allowed_tools": ["read_document"],
        },
    )
    client.patch(
        f"/sessions/{session_id}/artifacts/prompt",
        json={"content": "Summarize."},
    )
    provider.script = []
    agent = client.post(f"/sessions/{session_id}/skills")
    assert agent.status_code == 200, agent.text
    assert get_skill(db, agent.json()["skill_id"]) is not None

    pipe_id = client.post("/sessions").json()["id"]
    child_id = _committed_script(db)
    attach = client.post(
        f"/sessions/{pipe_id}/tools", json={"skill_ids": [child_id]}
    )
    assert attach.status_code == 200, attach.text
    client.patch(
        f"/sessions/{pipe_id}/skill-meta",
        json={"name": "Parent", "description": "skill only", "kind": "pipeline"},
    )
    steps = {
        "steps": [
            {
                "id": "call",
                "type": "skill",
                "input": "documents",
                "skill_id": child_id,
            }
        ]
    }
    client.patch(
        f"/sessions/{pipe_id}/artifacts/steps",
        json={"content": json.dumps(steps, ensure_ascii=False)},
    )
    provider.script = []
    pipe = client.post(f"/sessions/{pipe_id}/skills")
    assert pipe.status_code == 200, pipe.text


def test_dry_run_status_in_artifact_payload_and_draft(
    client, db, mem_db: Database
) -> None:
    session_id = create_session(mem_db)
    tools = build_artifact_tools(
        mem_db, session_id, available_tools=["read_document"]
    )
    _, save_script = tools.get("save_skill_script")
    _, read_draft = tools.get("read_skill_draft")
    _, try_fn = tools.get("try_skill_script")
    code = "result = document.upper()\n"

    async def _before():
        await save_script(code=code)
        return await read_draft()

    before = asyncio.run(_before())
    script = next(a for a in before["artifacts"] if a["type"] == "script")
    assert script["dry_run"]["ok"] is False
    assert script["dry_run"]["slot"] == "script"
    assert script["dry_run"]["time"] is None

    async def _after():
        result = await try_fn()
        draft = await read_draft()
        return result, draft

    result, draft = asyncio.run(_after())
    assert result["ok"] is True
    script = next(a for a in draft["artifacts"] if a["type"] == "script")
    assert script["dry_run"]["ok"] is True
    assert script["dry_run"]["sha256"]
    assert script["dry_run"]["time"]
    assert script["dry_run"]["stage"] in ("run", "verify")

    session_id = client.post("/sessions").json()["id"]
    client.patch(
        f"/sessions/{session_id}/artifacts/script",
        json={"content": code},
    )
    listed = client.get(f"/sessions/{session_id}/artifacts").json()
    script_http = next(a for a in listed if a["type"] == "script")
    assert "dry_run" in script_http
    assert script_http["dry_run"]["ok"] is False
    _seed_green_dry_run(db, session_id, code)
    listed = client.get(f"/sessions/{session_id}/artifacts").json()
    script_http = next(a for a in listed if a["type"] == "script")
    assert script_http["dry_run"]["ok"] is True
    assert script_http["dry_run"]["sha256"]
