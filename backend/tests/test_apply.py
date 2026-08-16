from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from catalog.agent.events import (
    FinishEvent,
    ReasoningEvent,
    RunMetaEvent,
    ScriptEvent,
    StepEvent,
    VerifyEvent,
)
from catalog.agent.registry import ToolRegistry
from catalog.documents.ingest import ingest_file
from catalog.documents.tools import build_document_tools
from catalog.storage.repo_document import get_document
from catalog.llm.base import (
    CompletionResult,
    LLMProvider,
    Message,
    ModelInfo,
    StreamDelta,
    ToolCall,
    ToolSpec,
)
from catalog.skills.apply import PipelineStepError, apply_skill, apply_skill_collect
from catalog.skills.budget import SkillBudget, SkillCallContext
from catalog.skills.artifact_tools import (
    resolve_pipeline_skill_steps,
    validate_pipeline_steps,
)
from catalog.skills.config import (
    PipelineStep,
    SkillConfig,
    VerifyCheck,
    pipeline_step_from_dict,
    pipeline_step_to_dict,
)
from catalog.skills.repo_run import get_run
from catalog.skills.repo_skill import create_skill, get_skill
from catalog.storage.db import Database
from catalog.storage.repo_custom_check import create_custom_check
from catalog.storage.repo_session import create_session
from catalog.storage.repo_session_document import list_session_documents


# --------------------------------------------------------------------------- #
# Test providers
# --------------------------------------------------------------------------- #


class ScriptProvider:
    """Provider that pops pre-scripted completions and records seen tools."""

    def __init__(self, script: list[CompletionResult]) -> None:
        self.script: list[CompletionResult] = list(script)
        self.seen_tools: list[list[ToolSpec] | None] = []
        self.seen_messages: list[list[Message]] = []

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
        reasoning: str = "",
    ) -> CompletionResult:
        self.seen_tools.append(list(tools) if tools else None)
        self.seen_messages.append(list(messages))
        return self.script.pop(0)

    async def stream_complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        reasoning: str = "",
    ) -> Any:
        yield StreamDelta(content="")


# Static check: ScriptProvider satisfies the protocol.
_PROVIDER: LLMProvider = ScriptProvider([])  # type: ignore[assignment]


def _result(content: str) -> CompletionResult:
    return CompletionResult(content=content, tool_calls=[], finish_reason="stop")


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def db() -> Database:
    d = Database(":memory:")
    d.init_schema()
    return d


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path


def _make_skill(
    *,
    allowed_tools: list[str] | None = None,
    verify_checks: list[VerifyCheck] | None = None,
    max_retries: int = 2,
) -> SkillConfig:
    return SkillConfig(
        name="summarizer",
        description="test skill",
        system_prompt="You are a summarizer.",
        allowed_tools=allowed_tools if allowed_tools is not None else ["read_document"],
        model="test/model",
        temperature=0.0,
        max_iterations=4,
        max_retries=max_retries,
        verify_checks=verify_checks if verify_checks is not None else [],
    )


def _ingest_input(db: Database, workspace: Path) -> str:
    row = ingest_file(db, workspace, filename="input.md", content=b"source text")
    return row.id


def _saved_trace(db: Database, skill_id: str) -> list[dict]:
    import json as _json

    with db.connect() as conn:
        row = conn.execute(
            "SELECT trace_json FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    return _json.loads(row["trace_json"] or "[]")


def _verify_entries(trace: list[dict] | Any) -> list:
    if isinstance(trace, list):
        return [e for e in trace if e.get("kind") == "verify"]
    return [e for e in trace.entries if e.kind == "verify"]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_apply_success_first_try(db: Database, workspace: Path) -> None:
    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("# Summary\n\nGreat document.")])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None
    input_row = get_document(db, input_doc_id)
    assert input_row is not None
    input_stem = Path(input_row.path).stem
    assert "# Summary\n\nGreat document." in (result.result_text or "")
    assert f"[[{input_stem}]]" in (result.result_text or "")

    out_doc = get_document(db, result.output_doc_id)
    assert out_doc is not None
    assert out_doc.path == f"results/{skill.name} — input.md"
    assert out_doc.path.startswith("results/")
    out_path = workspace / out_doc.path
    assert out_path.exists()
    file_text = out_path.read_text(encoding="utf-8")
    assert "# Summary\n\nGreat document." in file_text
    assert "## Ссылки" in file_text
    assert f"- [[{input_stem}]]" in file_text

    # skill_run row reflects success.
    # Find the run via the DB (only one run exists).
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, output_doc_id FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "ok"
    assert row["output_doc_id"] == result.output_doc_id

    verify_entries = _verify_entries(result.trace)
    assert len(verify_entries) == 1
    assert verify_entries[0].data["passed"] is True
    assert verify_entries[0].data["failures"] == []
    assert verify_entries[0].data["checks"] == [
        {
            "check": "non_empty",
            "params": {},
            "passed": True,
            "reason": None,
            "source": "builtin",
            "skipped": False,
        }
    ]


def test_apply_persist_attaches_output_to_session(
    db: Database, workspace: Path
) -> None:
    session_id = create_session(db)
    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("# Summary\n\nAttached.")])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            session_id=session_id,
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None
    assert [d.id for d in list_session_documents(db, session_id)] == [
        result.output_doc_id
    ]


def test_apply_retry_then_success(db: Database, workspace: Path) -> None:
    skill = _make_skill(
        verify_checks=[VerifyCheck("has_section", params={"heading": "Summary"})],
        max_retries=2,
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)

    # First attempt: no heading → fail. Second attempt: has heading → pass.
    provider = ScriptProvider(
        [
            _result("Just plain text without a heading."),
            _result("# Summary\n\nFixed version."),
        ]
    )

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None
    assert "Summary" in (result.result_text or "")

    # Trace should contain entries from both attempts (at least 2 llm entries).
    llm_entries = [e for e in result.trace.entries if e.kind == "llm"]
    assert len(llm_entries) >= 2

    verify_entries = _verify_entries(result.trace)
    assert len(verify_entries) == 2
    assert verify_entries[0].iteration == 1
    assert verify_entries[0].data["passed"] is False
    assert verify_entries[0].data["failures"]
    assert verify_entries[0].data["checks"][0]["check"] == "has_section"
    assert verify_entries[0].data["checks"][0]["passed"] is False
    assert verify_entries[0].data["checks"][0]["skipped"] is False
    assert verify_entries[1].iteration == 2
    assert verify_entries[1].data["passed"] is True
    assert verify_entries[1].data["failures"] == []
    assert verify_entries[1].data["checks"][0]["passed"] is True


def test_apply_verify_never_passes(db: Database, workspace: Path) -> None:
    skill = _make_skill(
        verify_checks=[VerifyCheck("has_section", params={"heading": "Missing"})],
        max_retries=2,
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)

    # Always bad text: 3 attempts (1 + 2 retries).
    provider = ScriptProvider(
        [
            _result("bad attempt 1"),
            _result("bad attempt 2"),
            _result("bad attempt 3"),
        ]
    )

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "failed"
    assert result.output_doc_id is None
    # Last text preserved.
    assert result.result_text == "bad attempt 3"

    # No result file written.
    results_dir = workspace / "results"
    if results_dir.exists():
        assert not any(results_dir.iterdir())

    # skill_run row reflects failure.
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, output_doc_id, trace_json FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "failed"
    assert row["output_doc_id"] is None
    assert row["trace_json"] is not None

    saved = _saved_trace(db, skill_id)
    verify_entries = _verify_entries(saved)
    assert len(verify_entries) == 3
    for i, entry in enumerate(verify_entries, start=1):
        assert entry["kind"] == "verify"
        assert entry["iteration"] == i
        assert entry["data"]["passed"] is False
        assert entry["data"]["failures"]
        assert any("has_section" in f for f in entry["data"]["failures"])


def test_apply_filters_tools(db: Database, workspace: Path) -> None:
    # Skill allows only read_document, not list_documents.
    skill = _make_skill(allowed_tools=["read_document"])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("ok")])

    asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    # The provider should have seen only read_document, not list_documents.
    assert len(provider.seen_tools) == 1
    tools_seen = provider.seen_tools[0]
    assert tools_seen is not None
    names = [t.name for t in tools_seen]
    assert names == ["read_document"]
    assert "list_documents" not in names


def test_apply_agent_empty_allowed_tools_still_gets_read_document(
    db: Database, workspace: Path
) -> None:
    skill = _make_skill(allowed_tools=[])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("# Summary\n\nOk.")])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert len(provider.seen_tools) == 1
    tools_seen = provider.seen_tools[0]
    assert tools_seen is not None
    names = [t.name for t in tools_seen]
    assert "read_document" in names
    assert "list_documents" not in names


def test_apply_agent_inlines_input_document_text(
    db: Database, workspace: Path
) -> None:
    skill = _make_skill(allowed_tools=[])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("# Summary\n\nBased on source.")])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert provider.seen_messages
    user_msgs = [m for m in provider.seen_messages[0] if m.role == "user"]
    assert user_msgs
    content = user_msgs[0].content or ""
    assert "source text" in content
    assert f"--- документ {input_doc_id}:" in content
    assert "полный текст" in content
    assert "не вложение файла" in content


def test_apply_unknown_allowed_tool(db: Database, workspace: Path) -> None:
    skill = _make_skill(allowed_tools=["read_document", "nonexistent_tool"])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)

    # Provider has no script — if the agent runs, pop(0) will fail.
    provider = ScriptProvider([])

    with pytest.raises(ValueError, match="unknown tool"):
        asyncio.run(
            apply_skill_collect(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
            )
        )

    # No skill_run should have been created (fail-closed before run).
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row["n"] == 0


def test_apply_missing_input_doc_raises(db: Database, workspace: Path) -> None:
    skill = _make_skill()
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    provider = ScriptProvider([_result("ok")])

    with pytest.raises(ValueError, match="input document not found"):
        asyncio.run(
            apply_skill_collect(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=["nonexistent"],
                base_tools=build_document_tools(db, workspace),
            )
        )


def test_apply_no_verify_checks_passes(db: Database, workspace: Path) -> None:
    """A skill with no verify_checks passes on the first attempt."""
    skill = _make_skill(verify_checks=[])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("anything")])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None


def test_apply_script_skill(db: Database, workspace: Path) -> None:
    """A kind=script skill runs its code deterministically — no agent loop.

    The provider has an empty script: if the agent loop were invoked,
    ``pop(0)`` would raise ``AssertionError``. The script uppercases the
    document text; the result is persisted as a result_md document and the
    skill_run is marked ok.
    """
    skill = SkillConfig(
        name="uppercaser",
        description="uppercase the document",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        verify_checks=[VerifyCheck("non_empty")],
        kind="script",
        code="result = document.upper()\n",
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    # Empty script — agent loop must NOT be invoked.
    provider = ScriptProvider([])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None
    input_row = get_document(db, input_doc_id)
    assert input_row is not None
    input_stem = Path(input_row.path).stem
    assert "SOURCE TEXT" in (result.result_text or "")
    assert f"[[{input_stem}]]" in (result.result_text or "")

    out_doc = get_document(db, result.output_doc_id)
    assert out_doc is not None
    assert out_doc.path == f"results/{skill.name} — input.md"
    out_path = workspace / out_doc.path
    assert out_path.exists()
    file_text = out_path.read_text(encoding="utf-8")
    assert "SOURCE TEXT" in file_text
    assert "## Ссылки" in file_text
    assert f"- [[{input_stem}]]" in file_text

    # skill_run row reflects success.
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, output_doc_id FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "ok"
    assert row["output_doc_id"] == result.output_doc_id

    # The provider was never called (no agent loop).
    assert provider.seen_tools == []

    # Trace contains a script entry.
    script_entries = [e for e in result.trace.entries if e.kind == "script"]
    assert len(script_entries) == 1
    assert script_entries[0].data["ok"] is True

    verify_entries = _verify_entries(result.trace)
    assert len(verify_entries) == 1
    assert verify_entries[0].data["passed"] is True
    assert verify_entries[0].data["failures"] == []
    assert verify_entries[0].data["checks"][0]["check"] == "non_empty"
    assert verify_entries[0].data["checks"][0]["passed"] is True


def test_apply_script_verify_failure_saved_in_trace(
    db: Database, workspace: Path
) -> None:
    skill = SkillConfig(
        name="empty-script",
        description="returns empty",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        verify_checks=[VerifyCheck("non_empty")],
        kind="script",
        code="result = ''\n",
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "failed"
    saved = _saved_trace(db, skill_id)
    verify_entries = _verify_entries(saved)
    assert len(verify_entries) == 1
    assert verify_entries[0]["kind"] == "verify"
    assert verify_entries[0]["data"]["passed"] is False
    assert verify_entries[0]["data"]["failures"]
    assert any("non_empty" in f for f in verify_entries[0]["data"]["failures"])
    assert verify_entries[0]["data"]["checks"][0]["check"] == "non_empty"
    assert verify_entries[0]["data"]["checks"][0]["passed"] is False
    assert verify_entries[0]["data"]["checks"][0]["skipped"] is False


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


def test_apply_script_custom_verify_falls_back_to_default_model(
    db: Database, workspace: Path
) -> None:
    row = create_custom_check(db, name="Has source", prompt="есть source")
    skill = SkillConfig(
        name="echo",
        description="echo",
        system_prompt="",
        allowed_tools=[],
        model="",
        verify_checks=[VerifyCheck(check=f"custom:{row.id}")],
        kind="script",
        code="result = document\n",
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = _JudgeProvider(["PASS"])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            persist=False,
            fallback_model="workspace/model",
        )
    )

    assert result.status == "ok"
    assert len(provider.requests) == 1
    assert provider.requests[0]["model"] == "workspace/model"


def test_apply_script_custom_verify_empty_model_without_fallback_fails(
    db: Database, workspace: Path
) -> None:
    row = create_custom_check(db, name="Has source", prompt="есть source")
    skill = SkillConfig(
        name="echo",
        description="echo",
        system_prompt="",
        allowed_tools=[],
        model="",
        verify_checks=[VerifyCheck(check=f"custom:{row.id}")],
        kind="script",
        code="result = document\n",
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = _JudgeProvider(["PASS"])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            persist=False,
        )
    )

    assert result.status == "failed"
    verify_entries = _verify_entries(result.trace)
    assert verify_entries
    assert any("missing model" in f for f in verify_entries[0].data["failures"])
    assert provider.requests == []


def test_apply_script_custom_verify_uses_pinned_provider(
    db: Database, workspace: Path
) -> None:
    row = create_custom_check(db, name="Has source", prompt="есть source")
    skill = SkillConfig(
        name="echo",
        description="echo",
        system_prompt="",
        allowed_tools=[],
        model="",
        provider="zai",
        verify_checks=[VerifyCheck(check=f"custom:{row.id}")],
        kind="script",
        code="result = document\n",
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    workspace_provider = _JudgeProvider(["SHOULD NOT RUN"])
    pinned = _JudgeProvider(["PASS"])

    result = asyncio.run(
        apply_skill_collect(
            provider=workspace_provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            persist=False,
            fallback_model="workspace/model",
            providers={"openrouter": workspace_provider, "zai": pinned},
        )
    )

    assert result.status == "ok"
    assert pinned.requests
    assert workspace_provider.requests == []


def test_apply_script_custom_verify_prefers_skill_model(
    db: Database, workspace: Path
) -> None:
    row = create_custom_check(db, name="Has source", prompt="есть source")
    skill = SkillConfig(
        name="echo",
        description="echo",
        system_prompt="",
        allowed_tools=[],
        model="skill/model",
        verify_checks=[VerifyCheck(check=f"custom:{row.id}")],
        kind="script",
        code="result = document\n",
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = _JudgeProvider(["PASS"])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            persist=False,
            fallback_model="workspace/model",
        )
    )

    assert result.status == "ok"
    assert provider.requests[0]["model"] == "skill/model"


def test_apply_agent_user_prompt_in_start_message(
    db: Database, workspace: Path
) -> None:
    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("# Summary\n\nWith clarification.")])
    clarification = "Сфокусируйся на рисках."

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            user_prompt=clarification,
        )
    )

    assert result.status == "ok"
    assert provider.seen_messages
    first = provider.seen_messages[0]
    assert first[0].role == "system"
    assert first[0].content == skill.system_prompt
    user_msgs = [m for m in first if m.role == "user"]
    assert user_msgs
    assert clarification in (user_msgs[0].content or "")
    assert "Уточнение к заданию" in (user_msgs[0].content or "")


def test_apply_script_ignores_user_prompt(db: Database, workspace: Path) -> None:
    skill = SkillConfig(
        name="uppercaser",
        description="uppercase the document",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        verify_checks=[VerifyCheck("non_empty")],
        kind="script",
        code="result = document.upper()\n",
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            user_prompt="this must be ignored for script skills",
        )
    )

    assert result.status == "ok"
    assert "SOURCE TEXT" in (result.result_text or "")
    assert provider.seen_tools == []
    assert provider.seen_messages == []


def test_apply_persist_false_skips_document_but_keeps_text(
    db: Database, workspace: Path
) -> None:
    """persist=False (CATALOG-18 "на экран") does not create a result_md doc.

    ``result_text`` is still filled in on the collected result and the run
    row, so the preview can be materialized later via ``POST /runs/{id}/save``.
    """
    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("# Summary\n\nOn-screen only.")])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            persist=False,
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is None
    assert result.result_text == "# Summary\n\nOn-screen only."

    # No result document written to disk.
    results_dir = workspace / "results"
    if results_dir.exists():
        assert not any(results_dir.iterdir())

    # skill_run row records the text without an output_doc_id.
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, output_doc_id, result_text, persist FROM skill_run "
            "WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "ok"
    assert row["output_doc_id"] is None
    assert row["result_text"] == "# Summary\n\nOn-screen only."
    assert row["persist"] == 0


def _ingest_named(db: Database, workspace: Path, filename: str, content: bytes) -> str:
    row = ingest_file(db, workspace, filename=filename, content=content)
    return row.id


def test_apply_multi_doc(db: Database, workspace: Path) -> None:
    """A skill applied to several documents loads them all and persists a result."""
    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    doc_a = _ingest_named(db, workspace, "a.md", b"first document")
    doc_b = _ingest_named(db, workspace, "b.md", b"second document")

    provider = ScriptProvider([_result("# Summary\n\nBoth documents.")])
    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[doc_a, doc_b],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert result.output_doc_id is not None
    # The start message listed both documents (provider saw the user message).
    assert provider.seen_tools is not None

    # skill_run row records both input ids.
    with db.connect() as conn:
        import json as _json

        row = conn.execute(
            "SELECT input_doc_ids FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert _json.loads(row["input_doc_ids"]) == [doc_a, doc_b]


def test_apply_arity_mismatch(db: Database, workspace: Path) -> None:
    """A skill declaring input_arity=2 rejects a single-document apply."""
    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill.input_arity = 2
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    doc_a = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("ok")])

    with pytest.raises(ValueError, match="expects 2 input"):
        asyncio.run(
            apply_skill_collect(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[doc_a],
                base_tools=build_document_tools(db, workspace),
            )
        )

    # No run should have been persisted (validated before create_run).
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row["n"] == 0


def test_skill_config_input_arity_roundtrip() -> None:
    """input_arity survives serialization; legacy configs default to None."""
    skill = SkillConfig(
        name="x",
        description="d",
        system_prompt="",
        allowed_tools=[],
        model="m",
        input_arity=2,
    )
    restored = SkillConfig.from_json(skill.to_json())
    assert restored.input_arity == 2

    legacy = SkillConfig.from_json(
        '{"name":"x","description":"d","system_prompt":"","allowed_tools":[],'
        '"model":"m","temperature":0,"max_iterations":1,"max_retries":0,'
        '"verify_checks":[],"output_kind":"md"}'
    )
    assert legacy.input_arity is None


def test_get_skill_returns_config(db: Database) -> None:
    """get_skill returns a record with deserialized config."""
    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill, status="committed"
    )

    record = get_skill(db, skill_id)
    assert record is not None
    assert record.id == skill_id
    assert record.name == skill.name
    assert record.status == "committed"
    assert record.config.model == skill.model
    assert record.config.system_prompt == skill.system_prompt
    assert len(record.config.verify_checks) == 1
    assert record.config.verify_checks[0].check == "non_empty"


def test_get_run_returns_row(db: Database, workspace: Path) -> None:
    skill = _make_skill()
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("ok")])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    # Find the run id.
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    run = get_run(db, row["id"])
    assert run is not None
    assert run["status"] == "ok"
    assert run["output_doc_id"] == result.output_doc_id
    assert run["trace_json"] is not None


def test_skill_config_json_roundtrip() -> None:
    skill = SkillConfig(
        name="test",
        description="desc",
        system_prompt="prompt",
        allowed_tools=["a", "b"],
        model="m",
        temperature=0.3,
        max_iterations=5,
        max_retries=1,
        verify_checks=[VerifyCheck("non_empty"), VerifyCheck("has_section", params={"heading": "X"})],
        output_kind="md",
    )
    s = skill.to_json()
    restored = SkillConfig.from_json(s)
    assert restored.name == skill.name
    assert restored.allowed_tools == skill.allowed_tools
    assert restored.temperature == skill.temperature
    assert restored.max_retries == skill.max_retries
    assert len(restored.verify_checks) == 2
    assert restored.verify_checks[1].params == {"heading": "X"}


def test_skill_config_kind_roundtrip() -> None:
    """kind/code survive serialization; legacy configs default to agent."""
    script_skill = SkillConfig(
        name="upper",
        description="d",
        system_prompt="",
        allowed_tools=[],
        model="m",
        kind="script",
        code="result = document.upper()\n",
    )
    restored = SkillConfig.from_json(script_skill.to_json())
    assert restored.kind == "script"
    assert restored.code == "result = document.upper()\n"

    # Legacy config without kind/code → defaults.
    legacy = SkillConfig.from_json(
        '{"name":"x","description":"d","system_prompt":"","allowed_tools":[],'
        '"model":"m","temperature":0,"max_iterations":1,"max_retries":0,'
        '"verify_checks":[],"output_kind":"md"}'
    )
    assert legacy.kind == "agent"
    assert legacy.code == ""
    assert legacy.steps == []


def _pipeline_skill() -> SkillConfig:
    return SkillConfig(
        name="pipe",
        description="linear pipeline",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        verify_checks=[VerifyCheck("non_empty")],
        kind="pipeline",
        steps=[
            PipelineStep(
                id="upper",
                type="script",
                input="documents",
                code="result = document.upper()\n",
            ),
            PipelineStep(
                id="note",
                type="llm",
                input="previous",
                system_prompt="Prefix the incoming text with Noted:",
                allowed_tools=["read_document"],
                model="test/model",
            ),
            PipelineStep(
                id="suffix",
                type="script",
                input="previous",
                code="result = document + '\\nEND'\n",
            ),
        ],
    )


def test_skill_config_pipeline_roundtrip() -> None:
    skill = _pipeline_skill()
    restored = SkillConfig.from_json(skill.to_json())
    assert restored.kind == "pipeline"
    assert [s.id for s in restored.steps] == ["upper", "note", "suffix"]
    assert restored.steps[1].type == "llm"
    assert restored.steps[1].system_prompt.startswith("Prefix")
    assert restored.steps[0].code == "result = document.upper()\n"


def test_pipeline_step_from_dict_keeps_unknown_input() -> None:
    step = pipeline_step_from_dict(
        {"id": "a", "type": "script", "input": "prevous"}, 0
    )
    assert step.input == "prevous"
    errors = validate_pipeline_steps([step], [])
    assert any("unknown input" in e for e in errors)


def test_pipeline_step_from_dict_defaults_missing_input() -> None:
    first = pipeline_step_from_dict({"id": "a", "type": "script"}, 0)
    later = pipeline_step_from_dict({"id": "b", "type": "script"}, 1)
    assert first.input == "documents"
    assert later.input == "previous"


def test_pipeline_step_legacy_roundtrip_omits_skill_fields() -> None:
    raw = {
        "id": "a",
        "type": "script",
        "input": "documents",
        "code": "result = document\n",
        "system_prompt": "",
        "allowed_tools": [],
        "model": "",
        "provider": "",
        "reasoning": "",
    }
    step = pipeline_step_from_dict(raw, 0)
    assert step.skill_id == ""
    assert step.config is None
    assert pipeline_step_to_dict(step) == raw


def test_pipeline_step_skill_roundtrip() -> None:
    nested = SkillConfig(
        name="Inner",
        description="d",
        system_prompt="",
        allowed_tools=[],
        model="m",
        kind="script",
        code="result = document.upper()\n",
    )
    step = PipelineStep(
        id="call",
        type="skill",
        input="previous",
        skill_id="abc",
        skill_name="Inner",
        config_hash="deadbeef",
        config=nested,
    )
    restored = pipeline_step_from_dict(pipeline_step_to_dict(step), 1)
    assert restored.type == "skill"
    assert restored.skill_id == "abc"
    assert restored.skill_name == "Inner"
    assert restored.config_hash == "deadbeef"
    assert restored.config is not None
    assert restored.config.name == "Inner"
    assert restored.config.code == nested.code


def test_validate_skill_step_draft_requires_skill_id() -> None:
    step = PipelineStep(id="call", type="skill")
    errors = validate_pipeline_steps([step], [], require_content=False)
    assert any("skill_id is empty" in e for e in errors)


def test_validate_skill_step_build_requires_snapshot() -> None:
    step = PipelineStep(id="call", type="skill", skill_id="abc")
    errors = validate_pipeline_steps([step], [], require_content=True)
    assert any("snapshot is missing" in e for e in errors)


def test_validate_skill_step_snapshot_skips_attach_check() -> None:
    nested = SkillConfig(
        name="Inner",
        description="d",
        system_prompt="",
        allowed_tools=[],
        model="m",
        kind="script",
        code="result = document\n",
    )
    step = PipelineStep(
        id="call",
        type="skill",
        skill_id="abc",
        config=nested,
    )
    errors = validate_pipeline_steps(
        [step],
        [],
        require_content=False,
        session_skills={},
    )
    assert errors == []


def test_resolve_keeps_snapshot_when_skill_not_attached(db: Database) -> None:
    session_id = create_session(db)
    nested = SkillConfig(
        name="Inner",
        description="d",
        system_prompt="",
        allowed_tools=[],
        model="m",
        kind="script",
        code="result = document.upper()\n",
    )
    step = PipelineStep(
        id="call",
        type="skill",
        skill_id="missing-child",
        skill_name="Inner",
        config_hash="deadbeef",
        config=nested,
    )
    filled, errors = resolve_pipeline_skill_steps([step], db, session_id)
    assert errors == []
    assert filled[0].config is not None
    assert filled[0].config.code == nested.code
    assert filled[0].config_hash == "deadbeef"


def test_apply_pipeline_script_llm_script(db: Database, workspace: Path) -> None:
    skill = _pipeline_skill()
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("NOTED: SOURCE TEXT")])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "ok"
    assert "NOTED: SOURCE TEXT" in (result.result_text or "")
    assert "END" in (result.result_text or "")
    assert provider.seen_messages
    user_msgs = [m for m in provider.seen_messages[0] if m.role == "user"]
    assert user_msgs
    assert "SOURCE TEXT" in (user_msgs[0].content or "")

    step_ids = {
        e.data.get("step_id")
        for e in result.trace.entries
        if e.data.get("step_id")
    }
    assert step_ids == {"upper", "note", "suffix"}

    verify_entries = _verify_entries(result.trace)
    assert len(verify_entries) == 1
    assert verify_entries[0].data["passed"] is True
    assert verify_entries[0].data["failures"] == []
    assert "checks" in verify_entries[0].data


def test_apply_pipeline_verify_failure_saved_in_trace(
    db: Database, workspace: Path
) -> None:
    skill = SkillConfig(
        name="pipe-verify-fail",
        description="script then failing verify",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        kind="pipeline",
        verify_checks=[VerifyCheck("has_section", params={"heading": "Missing"})],
        steps=[
            PipelineStep(
                id="upper",
                type="script",
                input="documents",
                code="result = document.upper()\n",
            ),
        ],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([])

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
        )
    )

    assert result.status == "failed"
    saved = _saved_trace(db, skill_id)
    verify_entries = _verify_entries(saved)
    assert len(verify_entries) == 1
    assert verify_entries[0]["kind"] == "verify"
    assert verify_entries[0]["data"]["passed"] is False
    assert verify_entries[0]["data"]["failures"]
    assert any("has_section" in f for f in verify_entries[0]["data"]["failures"])
    assert verify_entries[0]["data"]["checks"][0]["check"] == "has_section"
    assert verify_entries[0]["data"]["checks"][0]["passed"] is False


def test_apply_pipeline_user_prompt_in_llm_step(
    db: Database, workspace: Path
) -> None:
    skill = _pipeline_skill()
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("NOTED: SOURCE TEXT")])
    clarification = "Сфокусируйся на рисках."

    result = asyncio.run(
        apply_skill_collect(
            provider=provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            user_prompt=clarification,
        )
    )

    assert result.status == "ok"
    assert provider.seen_messages
    user_msgs = [m for m in provider.seen_messages[0] if m.role == "user"]
    assert user_msgs
    assert clarification in (user_msgs[0].content or "")
    assert "Уточнение к заданию" in (user_msgs[0].content or "")


def test_apply_pipeline_emits_step_id_on_events(
    db: Database, workspace: Path
) -> None:
    skill = _pipeline_skill()
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("NOTED: SOURCE TEXT")])

    events = asyncio.run(
        _collect_events(
            apply_skill(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
            )
        )
    )

    script_events = [e for e in events if isinstance(e, ScriptEvent)]
    assert {e.step_id for e in script_events} == {"upper", "suffix"}
    step_events = [e for e in events if isinstance(e, StepEvent)]
    assert step_events
    assert all(e.step_id == "note" for e in step_events)


def test_apply_pipeline_stops_on_middle_step_failure(
    db: Database, workspace: Path
) -> None:
    skill = SkillConfig(
        name="pipe-fail",
        description="middle step blows up",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        kind="pipeline",
        steps=[
            PipelineStep(
                id="upper",
                type="script",
                input="documents",
                code="result = document.upper()\n",
            ),
            PipelineStep(
                id="boom",
                type="llm",
                input="previous",
                system_prompt="do not succeed",
                allowed_tools=["read_document"],
            ),
            PipelineStep(
                id="suffix",
                type="script",
                input="previous",
                code="result = document + '\\nEND'\n",
            ),
        ],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)

    class BoomProvider(ScriptProvider):
        async def complete(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("llm step exploded")

    provider = BoomProvider([])

    with pytest.raises(RuntimeError, match="llm step exploded"):
        asyncio.run(
            apply_skill_collect(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
            )
        )

    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, trace_json FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "failed"
    import json as _json

    trace = _json.loads(row["trace_json"] or "[]")
    step_ids = {e.get("data", {}).get("step_id") for e in trace}
    assert "suffix" not in step_ids
    assert "upper" in step_ids


def test_apply_pipeline_previous_on_first_step_fails(
    db: Database, workspace: Path
) -> None:
    skill = SkillConfig(
        name="pipe-no-prev",
        description="first step asks for previous",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        kind="pipeline",
        steps=[
            PipelineStep(
                id="note",
                type="llm",
                input="previous",
                system_prompt="rewrite",
                allowed_tools=["read_document"],
            ),
        ],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("SHOULD NOT RUN")])

    with pytest.raises(ValueError, match="previous"):
        asyncio.run(
            apply_skill_collect(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
            )
        )

    assert provider.seen_messages == []
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "failed"


def _inner_script(
    *,
    name: str = "Inner",
    code: str = "result = document.upper()\n",
    verify_checks: list[VerifyCheck] | None = None,
) -> SkillConfig:
    return SkillConfig(
        name=name,
        description="inner script",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        kind="script",
        code=code,
        verify_checks=verify_checks if verify_checks is not None else [],
    )


def _pipeline_with_skill_step(
    inner: SkillConfig,
    *,
    skill_id: str = "inner-id",
    extra_steps: list[PipelineStep] | None = None,
    verify_checks: list[VerifyCheck] | None = None,
) -> SkillConfig:
    steps = [
        PipelineStep(
            id="call",
            type="skill",
            input="documents",
            skill_id=skill_id,
            skill_name=inner.name,
            config_hash="deadbeef",
            config=inner,
        ),
        *(extra_steps or []),
    ]
    return SkillConfig(
        name="pipe-skill",
        description="pipeline with skill step",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        kind="pipeline",
        verify_checks=verify_checks if verify_checks is not None else [],
        steps=steps,
    )


def test_apply_pipeline_skill_step_creates_nested_run(
    db: Database, workspace: Path
) -> None:
    inner = _inner_script()
    skill = _pipeline_with_skill_step(inner)
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    result = asyncio.run(
        apply_skill_collect(
            provider=ScriptProvider([]),
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            persist=False,
        )
    )
    assert result.status == "ok"
    assert result.result_text == "SOURCE TEXT"
    assert result.run_id
    nested = [
        e
        for e in result.trace.entries
        if e.kind == "tool_result" and e.data.get("step_id") == "call"
    ]
    assert nested
    assert nested[0].data["run_id"]
    assert nested[0].data["skill_name"] == "Inner"
    assert nested[0].data["config_hash"] == "deadbeef"
    assert nested[0].data["depth"] == 1
    child = get_run(db, nested[0].data["run_id"])
    assert child is not None
    assert child["parent_run_id"] == result.run_id
    assert child["persist"] is False
    assert child["result_text"] == "SOURCE TEXT"
    assert child["status"] == "ok"


def test_apply_pipeline_skill_step_feeds_next_step(
    db: Database, workspace: Path
) -> None:
    inner = _inner_script()
    skill = _pipeline_with_skill_step(
        inner,
        extra_steps=[
            PipelineStep(
                id="suffix",
                type="script",
                input="previous",
                code="result = document + '\\nEND'\n",
            ),
        ],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    result = asyncio.run(
        apply_skill_collect(
            provider=ScriptProvider([]),
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            persist=False,
        )
    )
    assert result.status == "ok"
    assert result.result_text == "SOURCE TEXT\nEND"
    step_ids = {
        e.data.get("step_id")
        for e in result.trace.entries
        if e.data.get("step_id")
    }
    assert "call" in step_ids
    assert "suffix" in step_ids


def test_apply_pipeline_skill_step_verify_fail_stops(
    db: Database, workspace: Path
) -> None:
    inner = _inner_script(
        verify_checks=[VerifyCheck("has_section", params={"heading": "Missing"})],
    )
    skill = _pipeline_with_skill_step(
        inner,
        extra_steps=[
            PipelineStep(
                id="suffix",
                type="script",
                input="previous",
                code="result = document + '\\nEND'\n",
            ),
        ],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    with pytest.raises(PipelineStepError, match="nested skill failed"):
        asyncio.run(
            apply_skill_collect(
                provider=ScriptProvider([]),
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
            )
        )
    saved = _saved_trace(db, skill_id)
    nested = [
        e
        for e in saved
        if e.get("kind") == "tool_result" and e.get("data", {}).get("step_id") == "call"
    ]
    assert nested
    assert nested[0]["data"]["ok"] is False
    assert nested[0]["data"]["failures"]
    assert any("has_section" in f for f in nested[0]["data"]["failures"])
    step_ids = {e.get("data", {}).get("step_id") for e in saved}
    assert "suffix" not in step_ids
    child = get_run(db, nested[0]["data"]["run_id"])
    assert child is not None
    assert child["status"] == "failed"
    assert child["parent_run_id"]


def test_apply_pipeline_skill_step_top_level_budget_none(
    db: Database, workspace: Path
) -> None:
    inner = _inner_script()
    skill = _pipeline_with_skill_step(inner)
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    result = asyncio.run(
        apply_skill_collect(
            provider=ScriptProvider([]),
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            budget=None,
            persist=False,
        )
    )
    assert result.status == "ok"
    assert result.result_text == "SOURCE TEXT"


def test_apply_pipeline_skill_step_budget_exhausted_in_trace(
    db: Database, workspace: Path
) -> None:
    inner = _inner_script()
    skill = _pipeline_with_skill_step(inner)
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    budget = SkillBudget(llm_calls_left=60, nested_runs_left=0)
    result = asyncio.run(
        apply_skill_collect(
            provider=ScriptProvider([]),
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            budget=budget,
        )
    )
    assert result.status == "failed"
    nodes = [e for e in result.trace.entries if e.kind == "budget"]
    assert nodes
    assert nodes[0].data["error"] == "budget exhausted"
    assert nodes[0].data["step_id"] == "call"
    assert budget.nested_runs_left == 0
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id FROM skill_run WHERE skill_id = ?",
            ("inner-id",),
        ).fetchall()
    assert rows == []


def test_apply_pipeline_skill_step_budget_released_on_failure(
    db: Database, workspace: Path
) -> None:
    inner = _inner_script(code="result = 1 / 0\n")
    skill = _pipeline_with_skill_step(inner)
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    budget = SkillBudget(llm_calls_left=60, nested_runs_left=20)
    with pytest.raises(Exception, match="division|script raised"):
        asyncio.run(
            apply_skill_collect(
                provider=ScriptProvider([]),
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
                budget=budget,
            )
        )
    assert budget.llm_calls_left == 60
    assert budget.nested_runs_left == 19


def test_apply_pipeline_skill_step_deadline_in_trace(
    db: Database, workspace: Path
) -> None:
    inner = _inner_script()
    skill = _pipeline_with_skill_step(inner)
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    budget = SkillBudget(
        llm_calls_left=60,
        nested_runs_left=20,
        deadline_monotonic=0.0,
    )
    result = asyncio.run(
        apply_skill_collect(
            provider=ScriptProvider([]),
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            budget=budget,
        )
    )
    assert result.status == "failed"
    nodes = [e for e in result.trace.entries if e.kind == "deadline"]
    assert nodes
    assert nodes[0].data["error"] == "deadline exceeded"
    assert nodes[0].data["step_id"] == "call"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id FROM skill_run WHERE skill_id = ?",
            ("inner-id",),
        ).fetchall()
    assert rows == []


def test_apply_pipeline_skill_step_max_depth_error(
    db: Database, workspace: Path
) -> None:
    inner = _inner_script()
    skill = _pipeline_with_skill_step(inner)
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    with pytest.raises(PipelineStepError, match="max skill depth exceeded"):
        asyncio.run(
            apply_skill_collect(
                provider=ScriptProvider([]),
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
                call_context=SkillCallContext(depth=2),
                max_skill_depth=2,
            )
        )
    saved = _saved_trace(db, skill_id)
    errors = [e for e in saved if e.get("kind") == "error"]
    assert errors
    assert "max skill depth" in errors[0]["data"]["error"]
    assert errors[0]["data"]["step_id"] == "call"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id FROM skill_run WHERE skill_id = ?",
            ("inner-id",),
        ).fetchall()
    assert rows == []


def test_apply_pipeline_finish_ignores_early_step_cap(
    db: Database, workspace: Path
) -> None:
    skill = SkillConfig(
        name="pipe-early-cap",
        description="early llm caps, later script finishes",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        max_iterations=1,
        kind="pipeline",
        verify_checks=[VerifyCheck("max_length", {"max": 1})],
        steps=[
            PipelineStep(
                id="note",
                type="llm",
                input="documents",
                system_prompt="rewrite",
                allowed_tools=["read_document"],
            ),
            PipelineStep(
                id="suffix",
                type="script",
                input="previous",
                code="result = (document or '') + '\\nEND'\n",
            ),
        ],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider(
        [
            CompletionResult(
                content="PARTIAL",
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="read_document",
                        arguments={"doc_id": input_doc_id},
                    )
                ],
                finish_reason="tool_calls",
            )
        ]
    )

    events = asyncio.run(
        _collect_events(
            apply_skill(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
            )
        )
    )

    finish_events = [e for e in events if isinstance(e, FinishEvent)]
    assert finish_events
    inner = finish_events[0]
    assert inner.capped is True
    final = finish_events[-1]
    assert final.finish_reason == "verify_failed"
    assert final.capped is False


def test_apply_pipeline_llm_step_uses_step_provider(
    db: Database, workspace: Path
) -> None:
    skill = SkillConfig(
        name="pipe-provider",
        description="llm step pins zai",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        provider="openrouter",
        kind="pipeline",
        steps=[
            PipelineStep(
                id="note",
                type="llm",
                input="documents",
                system_prompt="rewrite",
                allowed_tools=["read_document"],
                provider="zai",
            ),
        ],
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    run_provider = ScriptProvider([_result("SHOULD NOT RUN")])
    step_provider = ScriptProvider([_result("FROM ZAI")])

    result = asyncio.run(
        apply_skill_collect(
            provider=run_provider,
            db=db,
            workspace_dir=str(workspace),
            skill=skill,
            skill_id=skill_id,
            input_doc_ids=[input_doc_id],
            base_tools=build_document_tools(db, workspace),
            providers={"openrouter": run_provider, "zai": step_provider},
        )
    )

    assert result.status == "ok"
    assert "FROM ZAI" in (result.result_text or "")
    assert step_provider.seen_messages
    assert not run_provider.seen_messages


def test_tool_registry_filter() -> None:
    reg = ToolRegistry()
    reg.register(
        ToolSpec(name="a", description="da", parameters={}),
        _noop_tool,
    )
    reg.register(
        ToolSpec(name="b", description="db", parameters={}),
        _noop_tool,
    )
    reg.register(
        ToolSpec(name="c", description="dc", parameters={}),
        _noop_tool,
    )

    subset = reg.filter(["a", "c"])
    assert subset.names() == ["a", "c"]
    assert len(subset.specs()) == 2

    # Unknown name → ValueError.
    with pytest.raises(ValueError, match="unknown tool"):
        reg.filter(["a", "nope"])

    # Empty filter → empty registry.
    assert reg.filter([]).names() == []


# --------------------------------------------------------------------------- #
# Streaming apply_skill (async generator)
# --------------------------------------------------------------------------- #


async def _collect_events(gen: Any) -> list[Any]:
    return [ev async for ev in gen]


def test_apply_skill_streams_inner_events(db: Database, workspace: Path) -> None:
    """Streaming apply_skill forwards inner run_agent events + verify/finish.

    On a first-try success the stream must contain the agent-loop's own
    StepEvent/FinishEvent (inner events), the VerifyEvent, and the apply-level
    FinishEvent — not just the verify/finish bookends.
    """
    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("# Summary\n\nGreat document.")])

    events = asyncio.run(
        _collect_events(
            apply_skill(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
            )
        )
    )

    # Inner agent-loop events are forwarded (not swallowed by a collect call).
    step_events = [e for e in events if isinstance(e, StepEvent)]
    assert len(step_events) >= 1

    verify_events = [e for e in events if isinstance(e, VerifyEvent)]
    assert len(verify_events) == 1
    assert verify_events[0].iteration == 1
    assert verify_events[0].result.passed is True

    finish_events = [e for e in events if isinstance(e, FinishEvent)]
    # One inner (agent loop) finish + one apply-level finish.
    assert len(finish_events) == 2
    final = finish_events[-1]
    input_row = get_document(db, input_doc_id)
    assert input_row is not None
    input_stem = Path(input_row.path).stem
    assert "# Summary\n\nGreat document." in (final.text or "")
    assert f"[[{input_stem}]]" in (final.text or "")
    assert final.finish_reason == "stop"

    # Result document persisted + skill_run marked ok.
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, output_doc_id FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "ok"
    assert row["output_doc_id"] is not None
    out_doc = get_document(db, row["output_doc_id"])
    assert out_doc is not None
    out_path = workspace / out_doc.path
    assert out_path.exists()
    assert out_doc.path.startswith("results/")
    assert out_doc.path.endswith(".md")
    assert row["output_doc_id"][:8] not in out_doc.path


async def _noop_tool(**kwargs: Any) -> dict:
    return {}


# --------------------------------------------------------------------------- #
# Granular trace events (CATALOG-16): meta / script / reasoning
# --------------------------------------------------------------------------- #


def test_apply_emits_run_meta_first(db: Database, workspace: Path) -> None:
    """apply_skill opens the stream with a RunMetaEvent carrying run context.

    The meta frame is the very first event so the trace feed can render
    model/provider/kind/prompt up front. The provider name passed to
    apply_skill is forwarded verbatim (CATALOG-16).
    """
    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([_result("# Summary\n\nGreat document.")])

    events = asyncio.run(
        _collect_events(
            apply_skill(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
                provider_name="zai",
            )
        )
    )

    # The very first event on the wire is the run meta.
    meta_events = [e for e in events if isinstance(e, RunMetaEvent)]
    assert len(meta_events) == 1
    assert events[0] is meta_events[0]
    meta = meta_events[0]
    assert meta.model == skill.model
    assert meta.provider == "zai"
    assert meta.skill_kind == "agent"
    assert meta.system_prompt == skill.system_prompt
    assert meta.input_docs == [input_doc_id]


def test_apply_script_emits_script_events(db: Database, workspace: Path) -> None:
    """A kind=script skill surfaces start/done ScriptEvents in the stream."""
    skill = SkillConfig(
        name="uppercaser",
        description="uppercase the document",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        verify_checks=[VerifyCheck("non_empty")],
        kind="script",
        code="result = document.upper()\n",
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([])

    events = asyncio.run(
        _collect_events(
            apply_skill(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
            )
        )
    )

    script_events = [e for e in events if isinstance(e, ScriptEvent)]
    # start + done (no error path taken).
    assert [e.stage for e in script_events] == ["start", "done"]
    assert script_events[0].snippet == skill.code
    assert script_events[1].return_value == "SOURCE TEXT"
    assert script_events[1].duration is not None and script_events[1].duration >= 0.0

    # The meta frame still leads, and reports kind=script.
    meta_events = [e for e in events if isinstance(e, RunMetaEvent)]
    assert len(meta_events) == 1
    assert meta_events[0].skill_kind == "script"


def test_apply_script_emits_error_event_on_failure(db: Database, workspace: Path) -> None:
    """A failing script surfaces a ScriptEvent(stage=error) before re-raising."""
    skill = SkillConfig(
        name="boom",
        description="raises",
        system_prompt="",
        allowed_tools=[],
        model="test/model",
        verify_checks=[],
        kind="script",
        # NameError at runtime -> ScriptRuntimeError wrapping it.
        code="result = undefined_name\n",
    )
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = ScriptProvider([])

    with pytest.raises(Exception):
        asyncio.run(
            _collect_events(
                apply_skill(
                    provider=provider,
                    db=db,
                    workspace_dir=str(workspace),
                    skill=skill,
                    skill_id=skill_id,
                    input_doc_ids=[input_doc_id],
                    base_tools=build_document_tools(db, workspace),
                )
            )
        )

    # The generator was drained up to the failure; collect the events emitted
    # before the raise by re-running and capturing synchronously.
    events: list[Any] = []

    async def _drain_until_error() -> None:
        try:
            async for ev in apply_skill(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
            ):
                events.append(ev)
        except Exception:
            pass

    asyncio.run(_drain_until_error())
    script_events = [e for e in events if isinstance(e, ScriptEvent)]
    assert [e.stage for e in script_events] == ["start", "error"]
    assert script_events[1].error is not None
    assert script_events[1].duration is not None


def test_apply_reasoning_reaches_stream(db: Database, workspace: Path) -> None:
    """When the provider returns reasoning, a ReasoningEvent reaches the stream.

    Drives apply_skill with a provider whose completion carries ``reasoning``;
    the agent runner (CATALOG-24/16) must surface it as its own event in the
    apply stream, not just bury it in the trace.
    """

    class _ReasoningProvider(ScriptProvider):
        async def complete(
            self,
            model: str,
            messages: list[Message],
            tools: list[ToolSpec] | None = None,
            temperature: float = 0.0,
            tool_choice: str = "auto",
            reasoning: str = "",
        ) -> CompletionResult:
            self.seen_tools.append(list(tools) if tools else None)
            base = self.script.pop(0)
            base.reasoning = "Let me think about this document."
            return base

    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = _ReasoningProvider([_result("# Summary\n\nGreat document.")])

    events = asyncio.run(
        _collect_events(
            apply_skill(
                provider=provider,
                db=db,
                workspace_dir=str(workspace),
                skill=skill,
                skill_id=skill_id,
                input_doc_ids=[input_doc_id],
                base_tools=build_document_tools(db, workspace),
            )
        )
    )

    reasoning_events = [e for e in events if isinstance(e, ReasoningEvent)]
    assert len(reasoning_events) == 1
    assert "think about this document" in reasoning_events[0].text


# --------------------------------------------------------------------------- #
# Cancellation (CATALOG-11)
# --------------------------------------------------------------------------- #


class _BlockingApplyProvider(ScriptProvider):
    """Provider whose ``complete`` blocks forever until cancelled."""

    def __init__(self) -> None:
        super().__init__(script=[])
        self.was_cancelled = False

    async def complete(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
        reasoning: str = "",
    ) -> CompletionResult:
        self.seen_tools.append(list(tools) if tools else None)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise
        return _result("unreachable")


def test_apply_cancelled_marks_run_cancelled(db: Database, workspace: Path) -> None:
    """A cancelled apply marks the skill_run ``cancelled``, not ``failed`` (CATALOG-11).

    Cancelling the task running ``apply_skill`` propagates ``CancelledError``
    through the whole stack; ``_apply_core`` catches it and persists
    ``status='cancelled'`` so the run row never stays ``running`` and is
    distinguishable from a genuine failure.
    """
    skill = _make_skill(verify_checks=[VerifyCheck("non_empty")])
    skill_id = create_skill(
        db, name=skill.name, description=skill.description, config=skill
    )
    input_doc_id = _ingest_input(db, workspace)
    provider = _BlockingApplyProvider()

    async def _run_and_cancel() -> None:
        task = asyncio.ensure_future(
            _collect_events(
                apply_skill(
                    provider=provider,
                    db=db,
                    workspace_dir=str(workspace),
                    skill=skill,
                    skill_id=skill_id,
                    input_doc_ids=[input_doc_id],
                    base_tools=build_document_tools(db, workspace),
                )
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_run_and_cancel())

    # The provider observed the cancellation.
    assert provider.was_cancelled is True

    # The skill_run row is marked cancelled (not running/failed).
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, output_doc_id, trace_json FROM skill_run WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "cancelled"
    assert row["output_doc_id"] is None
    # Partial trace preserved.
    assert row["trace_json"] is not None
