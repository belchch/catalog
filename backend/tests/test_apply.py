from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.agent.events import (
    FinishEvent,
    ReasoningEvent,
    RunMetaEvent,
    ScriptEvent,
    StepEvent,
    VerifyEvent,
)
from app.agent.registry import ToolRegistry
from app.documents.ingest import build_doc_path, ingest_file
from app.documents.tools import build_document_tools
from app.storage.repo_document import get_document
from app.llm.base import (
    CompletionResult,
    LLMProvider,
    Message,
    ModelInfo,
    StreamDelta,
    ToolSpec,
)
from app.skills.apply import apply_skill, apply_skill_collect
from app.skills.config import SkillConfig, VerifyCheck
from app.skills.repo_run import get_run
from app.skills.repo_skill import create_skill, get_skill
from app.storage.db import Database


# --------------------------------------------------------------------------- #
# Test providers
# --------------------------------------------------------------------------- #


class ScriptProvider:
    """Provider that pops pre-scripted completions and records seen tools."""

    def __init__(self, script: list[CompletionResult]) -> None:
        self.script: list[CompletionResult] = list(script)
        self.seen_tools: list[list[ToolSpec] | None] = []

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
    assert result.result_text == "# Summary\n\nGreat document."

    out_doc = get_document(db, result.output_doc_id)
    assert out_doc is not None
    expected_path = build_doc_path(
        f"{skill.name} — input", result.output_doc_id, ".md", "results"
    )
    assert out_doc.path == expected_path
    assert out_doc.path != f"results/{result.output_doc_id}.md"
    out_path = workspace / out_doc.path
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8") == "# Summary\n\nGreat document."

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
    # Deterministic output: "source text" uppercased.
    assert result.result_text == "SOURCE TEXT"

    out_doc = get_document(db, result.output_doc_id)
    assert out_doc is not None
    assert out_doc.path == build_doc_path(
        f"{skill.name} — input", result.output_doc_id, ".md", "results"
    )
    out_path = workspace / out_doc.path
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8") == "SOURCE TEXT"

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
    assert final.text == "# Summary\n\nGreat document."
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
    assert out_doc.path.endswith(f"-{row['output_doc_id'][:8]}.md")


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
